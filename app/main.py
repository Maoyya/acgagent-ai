import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.middleware import LoggingMiddleware
from app.api.v1.router import router as v1_router

logger = logging.getLogger("acgagent-ai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    for subdir in ["agents", "knowledge_bases", "documents", "tools", "chroma", "uploads"]:
        (settings.data_dir / subdir).mkdir(parents=True, exist_ok=True)

    from app.db.chroma_client import init_chroma, close_chroma
    init_chroma()

    logger.info("acgagent-ai started on port %d", settings.port)
    yield
    close_chroma()
    logger.info("acgagent-ai shutting down")


app = FastAPI(
    title="acgagent-ai",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

app.include_router(v1_router)


@app.get("/api/v1/health", tags=["system"])
async def health_check():
    chroma_status = "not_initialized"
    try:
        from app.db.chroma_client import get_chroma
        get_chroma().heartbeat()
        chroma_status = "connected"
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": settings.app_version,
        "chroma": chroma_status,
        "llm": "configured_via_agent",
    }
