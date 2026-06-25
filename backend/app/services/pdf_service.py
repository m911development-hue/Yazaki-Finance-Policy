"""
Yazaki Finance Policy Assistant - PDF Processing Service
==========================================================
Handles PDF upload, text extraction (via pdfplumber),
chunking (via LangChain RecursiveCharacterTextSplitter),
and document management (list / delete).
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from fastapi import UploadFile, HTTPException

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from backend.app.config import settings
from backend.app.models.schemas import DocumentInfo

logger = logging.getLogger("yazaki.pdf_service")


class PDFService:
    """Manages the full lifecycle of uploaded PDF documents."""

    def __init__(self) -> None:
        self.upload_dir = Path(settings.KNOWLEDGE_DIR)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    async def process_pdf(self, file: UploadFile) -> tuple[DocumentInfo, list[Document]]:
        """
        Save an uploaded PDF, extract text, chunk it, and return
        metadata + LangChain Document chunks.

        Returns:
            (DocumentInfo, list[Document])  — metadata and indexable chunks.
        """
        # --- Validate file type ---
        if file.content_type not in ("application/pdf",):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {file.content_type}. Only PDF files are accepted.",
            )

        # --- Read file bytes & validate size ---
        content = await file.read()
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large ({len(content)} bytes). Maximum allowed: {settings.MAX_FILE_SIZE} bytes.",
            )

        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        # --- Save to disk ---
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.upload_dir / file.filename
        filepath.write_bytes(content)
        logger.info("Saved PDF: %s (%d bytes)", file.filename, len(content))

        # --- Extract text page-by-page ---
        raw_docs = self._extract_text(str(filepath), file.filename)
        if not raw_docs:
            # Clean up the saved file if no text could be extracted
            filepath.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail="Could not extract any text from the PDF. It may be image-only or corrupted.",
            )

        num_pages = len(raw_docs)

        # --- Chunk the extracted text ---
        chunks = self.text_splitter.split_documents(raw_docs)
        logger.info("Chunked %s → %d chunks from %d pages", file.filename, len(chunks), num_pages)

        # --- Build metadata ---
        now = datetime.now(timezone.utc).isoformat()
        doc_info = DocumentInfo(
            filename=file.filename,
            file_size=len(content),
            pages=num_pages,
            chunks=len(chunks),
            uploaded_at=now,
        )

        # Persist metadata alongside the PDF for later retrieval
        meta_path = self.upload_dir / f"{file.filename}.meta.json"
        meta_path.write_text(doc_info.model_dump_json(indent=2), encoding="utf-8")

        return doc_info, chunks

    def list_documents(self) -> list[DocumentInfo]:
        """Return metadata for every PDF currently in the upload directory."""
        documents: list[DocumentInfo] = []
        if not self.upload_dir.exists():
            return documents

        for pdf_file in sorted(self.upload_dir.glob("*.pdf")):
            meta_path = self.upload_dir / f"{pdf_file.name}.meta.json"
            if meta_path.exists():
                # Load previously saved metadata
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                documents.append(DocumentInfo(**data))
            else:
                # Fallback: construct minimal metadata from the file itself
                stat = pdf_file.stat()
                documents.append(
                    DocumentInfo(
                        filename=pdf_file.name,
                        file_size=stat.st_size,
                        pages=0,
                        chunks=0,
                        uploaded_at=datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    )
                )

        return documents

    def delete_document(self, filename: str) -> bool:
        """Delete a PDF and its metadata file. Returns True on success."""
        filepath = self.upload_dir / filename
        if not filepath.exists():
            return False

        filepath.unlink()
        logger.info("Deleted PDF: %s", filename)

        # Also remove the metadata sidecar
        meta_path = self.upload_dir / f"{filename}.meta.json"
        meta_path.unlink(missing_ok=True)
        return True

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _extract_text(self, filepath: str, source_filename: str) -> list[Document]:
        """
        Extract text from a PDF page-by-page using pdfplumber.

        Returns a list of LangChain Document objects, one per page,
        with metadata including the source filename and page number.
        """
        documents: list[Document] = []

        try:
            with pdfplumber.open(filepath) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text and text.strip():
                        documents.append(
                            Document(
                                page_content=text.strip(),
                                metadata={
                                    "source": source_filename,
                                    "page": page_num,
                                },
                            )
                        )
        except Exception as exc:
            logger.error("Failed to extract text from %s: %s", filepath, exc)
            raise HTTPException(
                status_code=400,
                detail=f"Error reading PDF '{source_filename}': {exc}",
            ) from exc

        return documents


# Singleton instance used by routers via dependency injection
pdf_service = PDFService()
