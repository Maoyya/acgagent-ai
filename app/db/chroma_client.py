import chromadb
import logging
from pathlib import Path
from typing import Optional, Union

from app.config import settings

logger = logging.getLogger("acgagent-ai")

_client: Optional[Union[chromadb.HttpClient, chromadb.PersistentClient]] = None


def init_chroma():
    global _client
    chroma_dir = settings.data_dir / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(chroma_dir))
    logger.info("Chroma initialized at %s", chroma_dir)


def get_chroma() -> chromadb.ClientAPI:
    if _client is None:
        init_chroma()
    return _client


def close_chroma():
    global _client
    _client = None
    logger.info("Chroma client closed")
