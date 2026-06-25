"""
Yazaki Finance Policy Assistant - Application Configuration
============================================================
Loads all settings from the .env file using Pydantic BaseSettings.
Environment variables override .env values automatically.
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.
    
    All settings can be overridden by setting the corresponding
    environment variable (case-insensitive).
    """

    # --- OpenAI API ---
    OPENAI_API_KEY: str  # Required — must be set in .env
    OPENAI_API_BASE: str = "https://api.openai.com/v1"  # Base URL for API requests (OpenAI/OpenRouter/etc)

    # --- File Storage Paths ---
    KNOWLEDGE_DIR: str = "backend/knowledge"                # Directory for company PDF
    COMPANY_PDF_PATH: str = "backend/knowledge/Yazaki Finance Policy.pdf"  # Dynamic fallback path to company PDF
    CHROMADB_DIR: str = "data/chromadb"                      # Directory for ChromaDB persistent storage

    # --- Model Configuration ---
    CHAT_MODEL: str = "gpt-4o-mini"                    # LLM for chat responses
    EMBEDDING_MODEL: str = "text-embedding-3-small"    # Embedding model for RAG
    TTS_MODEL: str = "edge-tts"                        # Switched to Microsoft Edge TTS
    TTS_VOICE: str = "en-IN-PrabhatNeural"              # Premium English India voice for Edge TTS
    STT_MODEL: str = "whisper-1"                       # Speech-to-text (Whisper) model

    # --- Document Chunking ---
    CHUNK_SIZE: int = 1000       # Characters per chunk for text splitting
    CHUNK_OVERLAP: int = 200     # Overlap between adjacent chunks

    # --- Upload Limits ---
    MAX_FILE_SIZE: int = 52428800  # 50 MB maximum file size

    def __init__(self, **values):
        super().__init__(**values)
        self.detect_pdf()

    def detect_pdf(self):
        # Search directories for any PDF that is not Kaizen.pdf
        search_dirs = [Path("backend"), Path("backend/knowledge"), Path("data/uploads")]
        found_pdf = None
        for sdir in search_dirs:
            if sdir.exists():
                for p in sdir.glob("*.pdf"):
                    if p.name.lower() != "kaizen.pdf":
                        found_pdf = p
                        break
            if found_pdf:
                break
                
        if found_pdf:
            self.COMPANY_PDF_PATH = str(found_pdf)

    model_config = {
        # The .env file lives at the project root (two levels up from this file)
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton settings instance — import this across the app
settings = Settings()

