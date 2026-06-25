"""
Kaizen AI - FastAPI Application Entry Point
=============================================
Run from the project root:
    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

The application:
  • Serves the frontend SPA from /static and / (index.html)
  • Exposes REST + SSE APIs under /api/
  • Initializes the RAG service and data directories on startup
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

from backend.app.config import settings
from backend.app.routers import chat, voice
from backend.app.services.rag_service import rag_service

# ──────────────────────────────────────────────
# Logging configuration
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-28s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("yazaki.main")


# ──────────────────────────────────────────────
# Application lifespan (startup / shutdown)
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup and once on shutdown.
    - Creates required directories
    - Detects and relocates the Yazaki Finance Policy PDF
    - Cleans up old Kaizen files and wipes ChromaDB on change
    - Initializes the RAG service (ChromaDB + embeddings)
    """
    # --- Startup ---
    logger.info("🚀 Starting Yazaki Finance Policy Assistant …")

    import shutil
    import hashlib

    # Ensure directories exist
    knowledge_dir = Path(settings.KNOWLEDGE_DIR)
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    
    chromadb_dir = Path(settings.CHROMADB_DIR)
    
    # 1. Clear any Kaizen files if they exist (to fulfill Requirement 1 & 5)
    for parent_dir in [Path("backend"), Path("backend/knowledge"), Path("data/uploads")]:
        if parent_dir.exists():
            for f in parent_dir.glob("*kaizen*"):
                if f.is_file():
                    logger.info(f"Removing old Kaizen file: {f}")
                    f.unlink(missing_ok=True)

    # 2. Relocate the dynamically detected new PDF to backend/knowledge if it is not already there
    detected_path = Path(settings.COMPANY_PDF_PATH)
    if detected_path.exists() and detected_path.parent != knowledge_dir:
        dest_path = knowledge_dir / detected_path.name
        logger.info(f"Relocating company PDF from {detected_path} to {dest_path}")
        shutil.move(str(detected_path), str(dest_path))
        settings.COMPANY_PDF_PATH = str(dest_path)
        detected_path = dest_path

    # 3. Wipe the vector DB if the hash is different or database does not match the new PDF
    if detected_path.exists():
        current_hash = hashlib.sha256(detected_path.read_bytes()).hexdigest()
        
        hash_file = chromadb_dir / "pdf_hash.txt"
        saved_hash = ""
        if hash_file.exists():
            saved_hash = hash_file.read_text().strip()
            
        if current_hash != saved_hash:
            logger.info("Wiping old vector database directory to ensure complete cleanup and rebuild...")
            if chromadb_dir.exists():
                shutil.rmtree(chromadb_dir)
            
    chromadb_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Data directories ready: %s, %s", settings.KNOWLEDGE_DIR, settings.CHROMADB_DIR)

    # Initialize the RAG pipeline (loads ChromaDB, creates embeddings model)
    try:
        rag_service.initialize()
        logger.info("RAG service initialized successfully.")
    except Exception as exc:
        logger.error("Failed to initialize RAG service: %s", exc, exc_info=True)

    yield  # ← application is running

    # --- Shutdown ---
    logger.info("👋 Shutting down Yazaki Finance Policy Assistant.")


# ──────────────────────────────────────────────
# FastAPI application instance
# ──────────────────────────────────────────────

app = FastAPI(
    title="Yazaki Finance Policy Assistant",
    description=(
        "Intelligent Yazaki Finance Policy Assistant powered by RAG. "
        "Ask questions and get accurate answers grounded in policy documents "
        "— with voice support."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────
# CORS middleware (permissive for development)
# ──────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Static files & templates
# ──────────────────────────────────────────────
# Paths are relative to the project root (where uvicorn is invoked).
# The frontend directory sits at:  <project_root>/frontend/

app.mount("/static", StaticFiles(directory="frontend"), name="static")
templates = Jinja2Templates(directory="frontend")


# ──────────────────────────────────────────────
# Include API routers
# ──────────────────────────────────────────────

app.include_router(chat.router)
app.include_router(voice.router)


# ──────────────────────────────────────────────
# Root route — serve the SPA
# ──────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root(request: Request):
    """Serve the frontend index.html page."""
    return templates.TemplateResponse(request, "index.html")


# ──────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health_check():
    """
    Lightweight health check endpoint.
    Returns service status and knowledge base stats.
    """
    try:
        stats = rag_service.get_stats()
    except Exception:
        stats = {"has_documents": False, "total_documents": 0, "total_chunks": 0}

    return {
        "status": "healthy",
        "service": "Yazaki Finance Policy Assistant",
        "version": "1.0.0",
        "knowledge_base": stats,
    }


# ──────────────────────────────────────────────
# Global exception handler
# ──────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all handler for unhandled exceptions.
    Returns a clean JSON error instead of an HTML traceback.
    """
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later.",
        },
    )
