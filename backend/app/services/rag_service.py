"""
Kaizen AI - RAG Pipeline Service
==================================
Retrieval-Augmented Generation using LangChain + ChromaDB + OpenAI.

Provides:
  • Vector store management (add / rebuild / stats)
  • Context-aware answer generation (single-shot & streaming)
  • Conversation history support for multi-turn chats
"""

import logging
from pathlib import Path
from typing import AsyncGenerator

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from backend.app.config import settings

logger = logging.getLogger("yazaki.rag_service")

# ──────────────────────────────────────────────────────────────────────
# System prompt — instructs the LLM to stay grounded in the company PDF
# ──────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Yazaki Finance Policy Assistant, an intelligent and professional assistant specializing in the Yazaki Finance Policy. You are friendly, helpful, clear, knowledgeable, and concise.

IMPORTANT RULES:
1. Answer questions ONLY based on the provided context from the official Yazaki Finance Policy PDF.
2. If the requested information is not available in the context, respond EXACTLY with: "I'm sorry, I couldn't find that information in the Yazaki Finance Policy."
3. Never make up, hallucinate, or generate information outside the provided company documentation.
4. Maintain a professional, friendly, and policy-focused tone.
5. Provide clear, well-structured, and concise answers.
6. Never mention page numbers, source filenames, document names, or any citation/reference markers in your answer. Do not say things like "on page X" or "according to the document". Just give the direct answer as plain information.
7. The chatbot must always respond in English. Even if the user asks questions in Hindi or any other language, translate/understand the query but generate the answer in English only.

Context from Yazaki Finance Policy:
{context}"""


class RAGService:
    """
    Singleton RAG service.

    Call `initialize()` once at application startup; after that
    all other methods are safe to use.
    """

    _instance = None

    def __new__(cls) -> "RAGService":
        """Enforce singleton — only one RAGService ever exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    # ------------------------------------------------------------------ #
    #  Initialization                                                     #
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        """
        Create or load the ChromaDB persistent vector store and
        instantiate the OpenAI LLM + embeddings. Detects and indexes
        the company PDF knowledge base automatically if changed or missing.
        """
        if self._initialized:
            logger.info("RAG service already initialized — skipping.")
            return

        logger.info("Initializing RAG service …")

        from pathlib import Path
        import hashlib

        pdf_path = Path(settings.COMPANY_PDF_PATH)
        chroma_dir = Path(settings.CHROMADB_DIR)
        need_rebuild = False
        current_hash = ""

        # 1. Detect if the PDF exists
        if not pdf_path.exists():
            logger.error(f"Company PDF not found at {settings.COMPANY_PDF_PATH}!")
        else:
            # Calculate current hash of the PDF
            pdf_bytes = pdf_path.read_bytes()
            current_hash = hashlib.sha256(pdf_bytes).hexdigest()
            
            # Check saved hash
            hash_file = chroma_dir / "pdf_hash.txt"
            saved_hash = ""
            if hash_file.exists():
                saved_hash = hash_file.read_text().strip()
                
            # Check if Chroma database files exist in chroma_dir
            has_db_files = chroma_dir.exists() and any(chroma_dir.iterdir())
            
            if not has_db_files or current_hash != saved_hash:
                logger.info("Vector database is missing or company PDF has changed. (Re)building index...")
                need_rebuild = True

        # --- Embeddings model ---
        self.embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
            openai_api_base=settings.OPENAI_API_BASE,
        )

        # --- Persistent ChromaDB vector store ---
        self.vectorstore = Chroma(
            collection_name="yazaki_knowledge_base",
            embedding_function=self.embeddings,
            persist_directory=settings.CHROMADB_DIR,
        )

        # --- Chat LLM ---
        self.llm = ChatOpenAI(
            model=settings.CHAT_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
            openai_api_base=settings.OPENAI_API_BASE,
            temperature=0.3,        # Low temperature for factual answers
            streaming=True,         # Enable streaming by default
            max_tokens=512,         # Limit max tokens to prevent credit limit errors on OpenRouter
        )

        # --- Prompt template (system + history + user) ---
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ])

        # Automatically rebuild if required
        if need_rebuild and pdf_path.exists():
            try:
                self.rebuild_company_index(pdf_path, current_hash)
            except Exception as exc:
                logger.error(f"Failed to auto-rebuild company index: {exc}", exc_info=True)

        self._initialized = True
        logger.info("RAG service initialized successfully.")

    def _extract_text_from_pdf(self, pdf_path: Path) -> list[Document]:
        """
        Extract text from a PDF. If pdfplumber yields no text (scanned PDF),
        fallback to pypdfium2 + OpenAI Vision OCR.
        """
        import pdfplumber
        raw_docs = []
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text and text.strip():
                        raw_docs.append(
                            Document(
                                page_content=text.strip(),
                                metadata={"source": pdf_path.name, "page": page_num},
                            )
                        )
        except Exception as exc:
            logger.error("pdfplumber failed for %s: %s", pdf_path.name, exc)

        if not raw_docs:
            logger.info("No text extracted via pdfplumber for %s. Attempting OCR fallback via OpenAI GPT-4o-mini...", pdf_path.name)
            try:
                import pypdfium2 as pdfium
                import io
                import base64
                from openai import OpenAI
                
                client = OpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    base_url=settings.OPENAI_API_BASE
                )
                
                doc = pdfium.PdfDocument(str(pdf_path))
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    bitmap = page.render(scale=2)
                    pil_img = bitmap.to_pil()
                    
                    buffer = io.BytesIO()
                    pil_img.save(buffer, format="JPEG")
                    img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    
                    logger.info(f"Performing OCR on {pdf_path.name} page {page_num + 1}/{len(doc)}...")
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Extract all readable text from this document page image. Maintain the layout structure where possible. Output ONLY the extracted text. Do not add any introduction, explanations, page number labels, or metadata. If the page is blank, respond with empty output."},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{img_str}"
                                        }
                                    }
                                ]
                            }
                        ],
                        max_tokens=2048,
                        temperature=0.0
                    )
                    
                    extracted_text = response.choices[0].message.content.strip()
                    if extracted_text:
                        raw_docs.append(
                            Document(
                                page_content=extracted_text,
                                metadata={"source": pdf_path.name, "page": page_num + 1},
                            )
                        )
                logger.info(f"OCR complete. Extracted text from {len(raw_docs)} pages.")
            except Exception as ocr_exc:
                logger.error(f"OCR fallback failed for {pdf_path.name}: {ocr_exc}", exc_info=True)
                
        return raw_docs

    def rebuild_company_index(self, pdf_path: Path, current_hash: str) -> None:
        """
        Extract text from the company PDF, chunk it, embed it,
        and store it in ChromaDB. Save the PDF hash.
        """
        logger.info(f"Rebuilding vector store index for company PDF: {pdf_path.name}")
        
        # Clear existing vectors
        self.vectorstore.delete_collection()
        self.vectorstore = Chroma(
            collection_name="yazaki_knowledge_base",
            embedding_function=self.embeddings,
            persist_directory=settings.CHROMADB_DIR,
        )

        raw_docs = self._extract_text_from_pdf(pdf_path)

        if not raw_docs:
            logger.warning("No text extracted from PDF — database index will be empty.")
            return

        # Strategy: Store EACH FULL PAGE as its own chunk so every page
        # is directly searchable. Additionally split long pages into
        # smaller sub-chunks for fine-grained matching.
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        all_chunks = []

        for doc in raw_docs:
            # Always add the full page as one chunk
            all_chunks.append(doc)

            # If the page is longer than chunk_size, also add sub-chunks
            if len(doc.page_content) > settings.CHUNK_SIZE:
                sub_chunks = splitter.split_documents([doc])
                all_chunks.extend(sub_chunks)

        self.vectorstore.add_documents(all_chunks)
        logger.info(f"Successfully indexed company PDF -> {len(all_chunks)} chunks ({len(raw_docs)} full pages + sub-chunks).")
        
        # Save hash
        chroma_dir = Path(settings.CHROMADB_DIR)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        hash_file = chroma_dir / "pdf_hash.txt"
        hash_file.write_text(current_hash)

    # ------------------------------------------------------------------ #
    #  Vector Store Operations                                            #
    # ------------------------------------------------------------------ #

    async def add_documents(self, chunks: list[Document]) -> None:
        """Add document chunks to the ChromaDB vector store."""
        if not chunks:
            logger.warning("add_documents called with empty chunk list — nothing to do.")
            return

        self.vectorstore.add_documents(chunks)
        logger.info("Added %d chunks to the vector store.", len(chunks))

    async def retrieve(self, query: str, k: int = 20) -> list[Document]:
        """
        Perform similarity search against the vector store.

        Args:
            query: User's natural-language question.
            k:     Number of top results to return.

        Returns:
            List of the most relevant Document chunks.
        """
        results = self.vectorstore.similarity_search(query, k=k)
        logger.debug("Retrieved %d chunks for query: '%s'", len(results), query[:80])
        return results

    async def rebuild_index(self) -> None:
        """
        Clear the existing vector store and re-index every PDF
        currently in the upload directory.
        """
        from backend.app.services.pdf_service import pdf_service  # avoid circular import

        logger.info("Rebuilding vector store index …")

        # Delete all existing vectors
        self.vectorstore.delete_collection()

        # Re-create the collection (Chroma needs this after deletion)
        self.vectorstore = Chroma(
            collection_name="yazaki_knowledge_base",
            embedding_function=self.embeddings,
            persist_directory=settings.CHROMADB_DIR,
        )

        # Re-process every PDF on disk
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        import pdfplumber
        from pathlib import Path

        upload_dir = Path(settings.KNOWLEDGE_DIR)
        if not upload_dir.exists():
            logger.info("Upload directory does not exist — nothing to re-index.")
            return

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        total_chunks = 0
        for pdf_path in upload_dir.glob("*.pdf"):
            raw_docs = self._extract_text_from_pdf(pdf_path)

            if raw_docs:
                chunks = splitter.split_documents(raw_docs)
                self.vectorstore.add_documents(chunks)
                total_chunks += len(chunks)
                logger.info("Re-indexed %s → %d chunks", pdf_path.name, len(chunks))

        logger.info("Rebuild complete — %d total chunks indexed.", total_chunks)

    def get_stats(self) -> dict:
        """Return document and chunk count statistics."""
        try:
            collection = self.vectorstore._collection
            count = collection.count()
        except Exception:
            count = 0

        # Count unique source documents
        from backend.app.services.pdf_service import pdf_service
        documents = pdf_service.list_documents()

        return {
            "total_documents": len(documents),
            "total_chunks": count,
            "has_documents": len(documents) > 0,
        }

    # ------------------------------------------------------------------ #
    #  Response Generation                                                #
    # ------------------------------------------------------------------ #

    def _build_history(self, conversation_history: list[dict]) -> list:
        """
        Convert the raw conversation_history dicts into typed
        LangChain message objects.
        """
        messages = []
        for msg in conversation_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        return messages

    def _format_context(self, docs: list[Document]) -> str:
        """
        Merge retrieved documents into a single context string
        with source attribution.
        """
        if not docs:
            return "No relevant context found in the knowledge base."

        parts: list[str] = []
        for doc in docs:
            parts.append(doc.page_content)
        return "\n\n---\n\n".join(parts)

    def _extract_sources(self, docs: list[Document]) -> list[str]:
        """Return a deduplicated list of source filenames."""
        seen: set[str] = set()
        sources: list[str] = []
        for doc in docs:
            name = doc.metadata.get("source", "Unknown")
            if name not in seen:
                seen.add(name)
                sources.append(name)
        return sources

    async def generate_response(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """
        Full RAG pipeline (non-streaming):
          1. Retrieve relevant chunks
          2. Build the prompt with context + history
          3. Call the LLM
          4. Return response text + source list

        Returns:
            {"response": str, "sources": list[str]}
        """
        conversation_history = conversation_history or []

        # Step 1 — Retrieve
        docs = await self.retrieve(query, k=20)
        context = self._format_context(docs)
        sources = self._extract_sources(docs)

        # Step 2 — Build prompt messages
        history = self._build_history(conversation_history)
        chain = self.prompt | self.llm

        # Step 3 — Invoke
        result = await chain.ainvoke({
            "context": context,
            "history": history,
            "question": query,
        })

        return {
            "response": result.content,
            "sources": sources,
        }

    async def generate_response_stream(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming RAG pipeline — yields individual tokens as they
        arrive from the LLM.

        Yields:
            str tokens (partial response text).
        """
        conversation_history = conversation_history or []

        # Retrieve context
        docs = await self.retrieve(query, k=20)
        context = self._format_context(docs)
        sources = self._extract_sources(docs)

        # Build prompt chain
        history = self._build_history(conversation_history)
        chain = self.prompt | self.llm

        # Stream tokens
        async for chunk in chain.astream({
            "context": context,
            "history": history,
            "question": query,
        }):
            if chunk.content:
                yield chunk.content

        # After all tokens, yield a special sources marker so the
        # router can include source attribution in the SSE stream.
        # Format: __SOURCES__:["file1.pdf","file2.pdf"]
        import json as _json
        yield f"__SOURCES__{_json.dumps(sources)}"


# Singleton instance
rag_service = RAGService()