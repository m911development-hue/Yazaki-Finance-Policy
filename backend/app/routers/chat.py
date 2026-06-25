"""
Yazaki Finance Policy Assistant - Chat Router
===============================================
POST /api/chat         — single-shot RAG response
POST /api/chat/stream  — SSE streaming RAG response
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.models.schemas import ChatRequest, ChatResponse, ErrorResponse
from backend.app.services.rag_service import rag_service

logger = logging.getLogger("yazaki.router.chat")

router = APIRouter(prefix="/api/chat", tags=["Chat"])


# ──────────────────────────────────────────────
# POST /api/chat — Non-streaming response
# ──────────────────────────────────────────────

@router.post(
    "",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Send a chat message and receive a complete response",
)
async def chat(request: ChatRequest):
    """
    Accept a user message (with optional conversation history),
    run the full RAG pipeline, and return a structured response.
    """
    # Validate non-empty message
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Check that documents exist in the knowledge base
    stats = rag_service.get_stats()
    if not stats["has_documents"]:
        raise HTTPException(
            status_code=400,
            detail="No documents in the knowledge base yet. Please upload PDF files first.",
        )

    try:
        result = await rag_service.generate_response(
            query=request.message,
            conversation_history=request.conversation_history,
        )

        return ChatResponse(
            response=result["response"],
            sources=result["sources"],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as exc:
        logger.error("Chat error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred: {exc}") from exc


# ──────────────────────────────────────────────
# POST /api/chat/stream — SSE streaming response
# ──────────────────────────────────────────────

@router.post(
    "/stream",
    summary="Send a chat message and receive a streaming SSE response",
)
async def chat_stream(request: ChatRequest):
    """
    Accept a user message and stream the response token-by-token
    as Server-Sent Events (SSE).

    SSE event format:
      data: {"token": "partial text"}       — for each token
      data: {"sources": ["file.pdf", ...]}  — after all tokens
      data: {"done": true}                  — signals completion
      data: {"error": "message"}            — on failure
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    stats = rag_service.get_stats()
    if not stats["has_documents"]:
        raise HTTPException(
            status_code=400,
            detail="No documents in the knowledge base yet. Please upload PDF files first.",
        )

    async def event_generator():
        """Yields SSE-formatted events."""
        try:
            async for token in rag_service.generate_response_stream(
                query=request.message,
                conversation_history=request.conversation_history,
            ):
                # The RAG service appends a special __SOURCES__ marker
                # after all real tokens have been yielded.
                if token.startswith("__SOURCES__"):
                    sources_json = token[len("__SOURCES__"):]
                    yield f"data: {json.dumps({'sources': json.loads(sources_json)})}\n\n"
                else:
                    yield f"data: {json.dumps({'token': token})}\n\n"

            # Signal completion
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        },
    )
