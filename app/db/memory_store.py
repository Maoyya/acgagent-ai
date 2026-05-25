import logging
from datetime import datetime

from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")


class MemoryStore:
    def _collection_name(self, conversation_id: str) -> str:
        return f"memory_conv_{conversation_id}"

    def _get_or_create_collection(self, conversation_id: str):
        return get_chroma().get_or_create_collection(
            name=self._collection_name(conversation_id),
            metadata={"hnsw:space": "cosine"},
        )

    def save_message(self, conversation_id: str, role: str, content: str, token_count: int = 0):
        if not conversation_id:
            return
        col = self._get_or_create_collection(conversation_id)
        msg_id = f"{role}_{col.count()}"
        timestamp = datetime.now().isoformat()
        col.add(
            ids=[msg_id],
            documents=[content],
            metadatas=[{"role": role, "timestamp": timestamp, "token_count": token_count}],
        )

    def load_history(self, conversation_id: str, limit: int = 100) -> list[dict]:
        if not conversation_id:
            return []
        try:
            col = get_chroma().get_collection(name=self._collection_name(conversation_id))
        except Exception:
            return []

        count = col.count()
        if count == 0:
            return []

        result = col.get(
            include=["documents", "metadatas"],
            limit=min(limit, count),
        )

        messages = []
        for doc, meta in zip(result["documents"], result["metadatas"]):
            messages.append({
                "role": meta.get("role", "user"),
                "content": doc,
                "token_count": meta.get("token_count", 0),
            })
        return messages

    def delete_conversation(self, conversation_id: str):
        if not conversation_id:
            return
        try:
            get_chroma().delete_collection(name=self._collection_name(conversation_id))
        except Exception:
            pass


memory_store = MemoryStore()
