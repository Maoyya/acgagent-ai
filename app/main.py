"""
acgagent-ai 应用入口。

FastAPI 应用，通过 lifespan 管理启动/关闭生命周期。
启动时初始化数据目录和 ChromaDB，关闭时释放 ChromaDB 连接。
所有 API 路由挂载在 /api/v1 前缀下，需携带 X-API-Key 认证。
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.middleware import LoggingMiddleware
from app.api.v1.router import router as v1_router

logger = logging.getLogger("acgagent-ai")


def _warn_default_api_key() -> None:
    """api_key 仍为默认值时打印告警（生产应通过 ACG_AI_API_KEY 覆盖）。"""
    if settings.api_key == "dev-api-key":
        logger.warning(
            "Using default API key 'dev-api-key'; set ACG_AI_API_KEY in production."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。

    启动时：
    - 配置日志级别
    - 创建数据子目录（如不存在）
    - 初始化 ChromaDB 持久化客户端

    关闭时：
    - 释放 ChromaDB 客户端
    """
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    _warn_default_api_key()

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
    """健康检查端点。无需 API Key 认证。检测 ChromaDB 连接状态。"""
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
