"""
ChromaDB 客户端管理。

使用 PersistentClient 模式，数据持久化到 data/chroma/ 目录。
服务启动时初始化（init_chroma），关闭时释放（close_chroma）。
延迟初始化：首次调用 get_chroma() 时自动创建客户端。
"""
import chromadb
import logging
from pathlib import Path
from typing import Optional, Union

from app.config import settings

logger = logging.getLogger("acgagent-ai")

_client: Optional[Union[chromadb.HttpClient, chromadb.PersistentClient]] = None


def init_chroma():
    """初始化 ChromaDB 持久化客户端。在 FastAPI lifespan 启动时调用。"""
    global _client
    chroma_dir = settings.data_dir / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(chroma_dir))
    logger.info("Chroma initialized at %s", chroma_dir)


def get_chroma() -> chromadb.ClientAPI:
    """获取 ChromaDB 客户端实例。如未初始化则自动初始化（延迟初始化模式）。"""
    if _client is None:
        init_chroma()
    return _client


def close_chroma():
    """关闭 ChromaDB 客户端。在 FastAPI lifespan 关闭时调用。"""
    global _client
    _client = None
    logger.info("Chroma client closed")
