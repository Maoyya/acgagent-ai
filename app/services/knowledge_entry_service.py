"""
结构化知识条目管理服务。

CRUD + ChromaDB 同步：create/update → upsert 向量；delete → 移除向量。
collection = kb_structured_entries（cosine），embedding 文本 = name+summary+tags。
private 条目必须有 user_id，否则 raise ValueError（路由转 400）。
ChromaDB 同步失败 best-effort（log warning，不阻断 CRUD）。
"""
import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from app.db.knowledge_entry_store import knowledge_entry_store
from app.db.chroma_client import get_chroma
from app.models.knowledge_entry import (
    KnowledgeEntry, KnowledgeEntryCreateRequest, KnowledgeEntryUpdateRequest,
    EntryScope,
)

logger = logging.getLogger("acgagent-ai")

_COLLECTION = "kb_structured_entries"


class KnowledgeEntryService:
    def _collection(self):
        return get_chroma().get_or_create_collection(
            name=_COLLECTION, metadata={"hnsw:space": "cosine"},
        )

    def _embed_text(self, entry: KnowledgeEntry) -> str:
        return f"{entry.name}\n{entry.summary}\n" + ",".join(entry.tags)

    def _meta(self, entry: KnowledgeEntry) -> dict:
        return {
            "entry_id": entry.id,
            "type": entry.type.value,
            "scope": entry.scope.value,
            "user_id": entry.user_id or "",
        }

    def _sync_upsert(self, entry: KnowledgeEntry) -> None:
        try:
            self._collection().upsert(
                ids=[entry.id],
                documents=[self._embed_text(entry)],
                metadatas=[self._meta(entry)],
            )
        except Exception as e:
            logger.warning("KB entry vector upsert failed for %s: %s", entry.id, e)

    def _sync_delete(self, entry_id: str) -> None:
        try:
            self._collection().delete(ids=[entry_id])
        except Exception as e:
            logger.warning("KB entry vector delete failed for %s: %s", entry_id, e)

    def _ensure_private_user_id(self, scope: EntryScope, user_id: Optional[str]) -> None:
        if scope == EntryScope.private and not user_id:
            raise ValueError("private 条目必须提供 user_id")

    def _validate_entry_id(self, entry_id: str) -> None:
        # entry_id 由服务端生成 = uuid4().hex[:12] = 12 位小写 hex。
        # 严格匹配，防 path traversal / 越权查询；不匹配 → ValueError（路由转 400）。
        if not re.fullmatch(r"[0-9a-f]{12}", entry_id):
            raise ValueError(f"非法 entry_id: {entry_id!r}")

    def list(self, type: Optional[str] = None, scope: Optional[str] = None,
             user_id: Optional[str] = None, q: Optional[str] = None) -> list[KnowledgeEntry]:
        result = []
        for e in knowledge_entry_store.list_all():
            if type and e.type.value != type:
                continue
            if scope and e.scope.value != scope:
                continue
            if user_id and e.user_id != user_id:
                continue
            if q and q.lower() not in (e.name + e.summary).lower():
                continue
            result.append(e)
        return result

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        self._validate_entry_id(entry_id)
        return knowledge_entry_store.get(entry_id)

    def create(self, req: KnowledgeEntryCreateRequest) -> KnowledgeEntry:
        self._ensure_private_user_id(req.scope, req.user_id)
        entry = KnowledgeEntry(
            id=uuid.uuid4().hex[:12],
            type=req.type, scope=req.scope, user_id=req.user_id,
            name=req.name, summary=req.summary, tags=req.tags, details=req.details,
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        saved = knowledge_entry_store.save(entry)
        self._sync_upsert(saved)
        return saved

    def update(self, entry_id: str, req: KnowledgeEntryUpdateRequest) -> Optional[KnowledgeEntry]:
        self._validate_entry_id(entry_id)
        entry = knowledge_entry_store.get(entry_id)
        if entry is None:
            return None
        # exclude_none：传 tags/details=null 视为"不修改"，避免 setattr(None) 越过 pydantic
        # 校验、持久化 null 后下次 get 抛 ValidationError 而损坏条目（opus final review F1）。
        for field, value in req.model_dump(exclude_unset=True, exclude_none=True).items():
            setattr(entry, field, value)
        self._ensure_private_user_id(entry.scope, entry.user_id)  # 合并后校验
        entry.updated_at = datetime.now()
        saved = knowledge_entry_store.save(entry)
        self._sync_upsert(saved)
        return saved

    def delete(self, entry_id: str) -> bool:
        self._validate_entry_id(entry_id)
        ok = knowledge_entry_store.delete(entry_id)
        if ok:
            self._sync_delete(entry_id)
        return ok


knowledge_entry_service = KnowledgeEntryService()
