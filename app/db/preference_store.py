"""
用户偏好存储。

复用 ChromaDB（与 memory_store 一致），collection 名 user_preferences，cosine 距离。
把'生成的 system_prompt 文本'作为 document 向量化，供二期相似度推荐。
metadata 只支持原始类型，故 hints 合并为字符串、user_id 缺失时落 'anonymous'。
"""
import logging
from datetime import datetime

from app.db.chroma_client import get_chroma
from app.models.prompt import PromptMode

logger = logging.getLogger("acgagent-ai")

_COLLECTION = "user_preferences"


class PreferenceStore:
    def _collection(self):
        return get_chroma().get_or_create_collection(
            name=_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def record(self, user_id: str | None, mode: PromptMode, hints: list[str], prompt: str) -> None:
        """记录一次成功生成。best-effort：异常由调用方决定是否吞掉。"""
        col = self._collection()
        uid = user_id or "anonymous"
        rec_id = f"pref_{col.count()}"
        col.add(
            ids=[rec_id],
            documents=[prompt],
            metadatas=[{
                "user_id": uid,
                "mode": mode.value,
                "hint_tags": ";".join(hints),
                "created_at": datetime.now().isoformat(),
            }],
        )

    def list_by_user(self, user_id: str) -> list[dict]:
        """读取某用户全部偏好记录（一期用于校验/排错；二期 recommend 复用）。"""
        col = self._collection()
        try:
            res = col.get(where={"user_id": user_id}, include=["documents", "metadatas"])
        except Exception:
            return []
        out = []
        for doc, meta in zip(res["documents"], res["metadatas"]):
            out.append({
                "prompt": doc,
                "user_id": meta.get("user_id"),
                "mode": meta.get("mode"),
                "hint_tags": meta.get("hint_tags", ""),
                "created_at": meta.get("created_at"),
            })
        return out


preference_store = PreferenceStore()
