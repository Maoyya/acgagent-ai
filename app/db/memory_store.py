"""
对话记忆存储。

使用 ChromaDB 存储对话历史，每个 conversation_id 对应一个 collection。
消息按追加顺序存储，每条消息带有 role、timestamp、token_count 元数据。
注意：ChromaDB 的 get() 不保证时序，依赖元数据中的 timestamp 排序需在业务层处理。
"""
import logging
from datetime import datetime

from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")


class MemoryStore:
    def _collection_name(self, conversation_id: str) -> str:
        """每个会话对应一个独立的 ChromaDB collection。"""
        return f"memory_conv_{conversation_id}"

    def _get_or_create_collection(self, conversation_id: str):
        return get_chroma().get_or_create_collection(
            name=self._collection_name(conversation_id),
            metadata={"hnsw:space": "cosine"},
        )

    def save_message(self, conversation_id: str, role: str, content: str, token_count: int = 0):
        """追加一条消息到会话。ID 格式为 {role}_{序号}，保证唯一性。"""
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
        """加载会话历史消息。collection 不存在时返回空列表。"""
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
        """删除整个会话及其所有消息（删除 collection）。"""
        if not conversation_id:
            return
        try:
            get_chroma().delete_collection(name=self._collection_name(conversation_id))
        except Exception:
            pass


memory_store = MemoryStore()
