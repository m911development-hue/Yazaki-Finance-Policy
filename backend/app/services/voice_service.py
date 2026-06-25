"""
Yazaki Finance Policy Assistant - Voice Service
=================================================
Speech-to-Text (Whisper) and Text-to-Speech (TTS-1-HD)
using the OpenAI Python client directly (not LangChain).
"""

import os
import tempfile
import logging
from pathlib import Path

from openai import AsyncOpenAI
from fastapi import UploadFile, HTTPException

from backend.app.config import settings

logger = logging.getLogger("yazaki.voice_service")


import edge_tts

# Singleton instance will be created at the end

class VoiceService:
    """Handles audio transcription (Whisper) and speech synthesis (Edge TTS)."""

    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
        )
        self.stt_model = settings.STT_MODEL      # whisper-1
        self.tts_voice = settings.TTS_VOICE      # en-IN-PrabhatNeural

    # ------------------------------------------------------------------ #
    #  Speech-to-Text                                                     #
    # ------------------------------------------------------------------ #

    async def speech_to_text(self, audio_file: UploadFile) -> str:
        """
        Transcribe an uploaded audio file using OpenAI Whisper.
        """
        # Read the raw audio bytes
        audio_bytes = await audio_file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio file is empty.")

        suffix = Path(audio_file.filename or "audio.webm").suffix or ".webm"
        tmp_path: str | None = None

        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix
            ) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            with open(tmp_path, "rb") as f:
                transcript = await self.client.audio.transcriptions.create(
                    model=self.stt_model,
                    file=f,
                    response_format="text",
                )

            logger.info("Transcribed audio (%d bytes) → %d chars", len(audio_bytes), len(transcript))
            return transcript.strip() if isinstance(transcript, str) else transcript.text.strip()

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Speech-to-text failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Speech-to-text failed: {exc}") from exc
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ------------------------------------------------------------------ #
    #  Text-to-Speech (Edge TTS)                                          #
    # ------------------------------------------------------------------ #

    async def text_to_speech(self, text: str) -> bytes:
        """
        Convert text to natural-sounding speech using Microsoft Edge TTS.

        Args:
            text: The text to synthesize.

        Returns:
            Raw MP3 audio bytes.
        """
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="Text for synthesis cannot be empty.")

        try:
            # The user requested to increase the voice speed by 0.2 (20%)
            communicate = edge_tts.Communicate(text, self.tts_voice, rate="+20%")
            
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
                    
            logger.info("Synthesized %d chars → %d bytes of audio via Edge TTS", len(text), len(audio_data))
            return bytes(audio_data)

        except Exception as exc:
            logger.error("Text-to-speech failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Text-to-speech failed: {exc}",
            ) from exc

# Singleton instance
voice_service = VoiceService()
