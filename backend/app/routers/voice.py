"""
Yazaki Finance Policy Assistant - Voice Router
================================================
POST /api/voice/transcribe  — audio → text (Whisper)
POST /api/voice/synthesize  — text  → audio (TTS-1-HD)
POST /api/voice/chat        — audio → text → RAG → audio (full pipeline)
"""

import base64
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response

from backend.app.models.schemas import (
    VoiceTranscribeResponse,
    VoiceChatRequest,
    VoiceChatResponse,
    ErrorResponse,
)
from backend.app.services.voice_service import voice_service
from backend.app.services.rag_service import rag_service

logger = logging.getLogger("yazaki.router.voice")

router = APIRouter(prefix="/api/voice", tags=["Voice"])


# ──────────────────────────────────────────────
# POST /api/voice/transcribe
# ──────────────────────────────────────────────

@router.post(
    "/transcribe",
    response_model=VoiceTranscribeResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Transcribe an audio file to text",
)
async def transcribe_audio(audio: UploadFile = File(...)):
    """
    Upload an audio recording and get back the transcribed text.
    Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg.
    """
    try:
        text = await voice_service.speech_to_text(audio)
        return VoiceTranscribeResponse(text=text)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Transcription error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc


# ──────────────────────────────────────────────
# POST /api/voice/synthesize
# ──────────────────────────────────────────────

@router.post(
    "/synthesize",
    summary="Synthesize text into speech audio using Edge TTS",
    responses={400: {"model": ErrorResponse}},
)
async def synthesize_speech(request: VoiceChatRequest):
    """
    Convert a text string into natural-sounding speech via Microsoft Edge TTS.
    Returns raw MP3 audio bytes.
    """
    try:
        audio_bytes = await voice_service.text_to_speech(request.text)
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=yazaki_speech.mp3"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Synthesis error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {exc}") from exc


# ──────────────────────────────────────────────
# POST /api/voice/chat — Full voice pipeline
# ──────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=VoiceChatResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Full voice chat: audio in → AI text + audio out",
)
async def voice_chat(audio: UploadFile = File(...)):
    """
    Complete voice-to-voice pipeline:
      1. Transcribe the user's audio (STT)
      2. Generate an AI response via RAG
      3. Synthesize the response into speech (TTS)
      4. Return transcription + AI text + base64-encoded audio

    The frontend can play the audio directly from the base64 data.
    """
    # Check that documents are available
    stats = rag_service.get_stats()
    if not stats["has_documents"]:
        raise HTTPException(
            status_code=400,
            detail="No documents in the knowledge base. Please upload PDF files first.",
        )

    try:
        # Step 1 — Transcribe
        transcription = await voice_service.speech_to_text(audio)
        if not transcription.strip():
            raise HTTPException(status_code=400, detail="Could not detect any speech in the audio.")

        logger.info("Voice chat — transcribed: '%s'", transcription[:100])

        # Step 2 — Generate RAG response
        result = await rag_service.generate_response(
            query=transcription,
            conversation_history=[],
        )
        ai_text = result["response"]
        sources = result["sources"]

        # Clean markdown from text for TTS so it doesn't read out symbols
        import re
        clean_text = re.sub(r'[*#`_]', '', ai_text).strip()

        # Step 3 — Synthesize AI response to audio
        audio_bytes = await voice_service.text_to_speech(clean_text)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        logger.info("Voice chat — response generated (%d chars, %d bytes audio)", len(ai_text), len(audio_bytes))

        return VoiceChatResponse(
            transcription=transcription,
            text=ai_text,
            audio_base64=audio_b64,
            sources=sources,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Voice chat error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Voice chat failed: {exc}") from exc
