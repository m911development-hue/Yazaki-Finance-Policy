"""
Yazaki Finance Policy Assistant - Pydantic Request / Response Schemas
======================================================================
Defines all data models used in API request validation
and response serialization.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ──────────────────────────────────────────────
# Chat Schemas
# ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""
    message: str = Field(..., min_length=1, description="User's chat message")
    conversation_history: list[dict] = Field(
        default=[],
        description="Previous messages for multi-turn context: [{'role': 'user'|'assistant', 'content': '...'}]",
    )


class ChatResponse(BaseModel):
    """Structured chat response returned to the frontend."""
    response: str = Field(..., description="AI-generated answer")
    sources: list[str] = Field(default=[], description="Source document filenames used")
    timestamp: str = Field(..., description="ISO-8601 timestamp of the response")


# ──────────────────────────────────────────────
# Document Schemas
# ──────────────────────────────────────────────

class DocumentInfo(BaseModel):
    """Metadata for a single uploaded document."""
    filename: str
    file_size: int          # Size in bytes
    pages: int              # Number of pages extracted
    chunks: int             # Number of text chunks created
    uploaded_at: str        # ISO-8601 timestamp


class DocumentUploadResponse(BaseModel):
    """Response after uploading one or more documents."""
    documents: list[DocumentInfo]
    status: str = "success"


class DocumentListResponse(BaseModel):
    """Response for listing all uploaded documents."""
    documents: list[DocumentInfo]
    total: int


class DocumentStatusResponse(BaseModel):
    """Quick status check — does the knowledge base have documents?"""
    has_documents: bool
    total_documents: int
    total_chunks: int


# ──────────────────────────────────────────────
# Voice Schemas
# ──────────────────────────────────────────────

class VoiceTranscribeResponse(BaseModel):
    """Response after transcribing an audio file."""
    text: str = Field(..., description="Transcribed text from audio")


class VoiceChatRequest(BaseModel):
    """Request body for text-to-speech synthesis."""
    text: str = Field(..., min_length=1, description="Text to synthesize into speech")


class VoiceChatResponse(BaseModel):
    """Response for the full voice-chat pipeline."""
    transcription: str = Field(..., description="What the user said (STT output)")
    text: str = Field(..., description="AI-generated text response")
    audio_base64: str = Field(..., description="Base64-encoded MP3 audio of the AI response")
    sources: list[str] = Field(default=[], description="Source documents used")


# ──────────────────────────────────────────────
# Error Schema
# ──────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standardized error response."""
    error: str = Field(..., description="Short error label")
    detail: str = Field(..., description="Human-readable error description")
