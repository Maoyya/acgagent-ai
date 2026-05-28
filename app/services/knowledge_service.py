"""
知识库管理服务。

知识库是 RAG 检索的基础，包含 Embedding 配置和分块策略。
每个知识库在 ChromaDB 中对应一个 collection（kb_{id}_chunks）。
删除知识库时会同步清理 ChromaDB 中的向量数据。
"""
import uuid
from datetime import datetime
from typing import Optional

from app.db.knowledge_store import knowledge_store
from app.models.knowledge_base import KnowledgeBase, KnowledgeBaseCreateRequest, KnowledgeBaseUpdateRequest


class KnowledgeService:
    def list_all(self) -> list[KnowledgeBase]:
        return knowledge_store.list_all()

    def get(self, kb_id: str) -> Optional[KnowledgeBase]:
        return knowledge_store.get(kb_id)

    def create(self, req: KnowledgeBaseCreateRequest) -> KnowledgeBase:
        kb = KnowledgeBase(
            id=uuid.uuid4().hex[:12],
            name=req.name,
            description=req.description,
            embedding_config=req.embedding_config,
            chunk_config=req.chunk_config,
            document_count=0,
            chunk_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return knowledge_store.save(kb)

    def update(self, kb_id: str, req: KnowledgeBaseUpdateRequest) -> Optional[KnowledgeBase]:
        kb = knowledge_store.get(kb_id)
        if kb is None:
            return None
        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(kb, field, value)
        kb.updated_at = datetime.now()
        return knowledge_store.save(kb)

    def delete(self, kb_id: str) -> bool:
        """删除知识库。同时清理 ChromaDB 中对应的 collection 和所有向量数据。"""
        from app.db.chroma_client import get_chroma
        try:
            get_chroma().delete_collection(name=f"kb_{kb_id}_chunks")
        except Exception:
            pass
        return knowledge_store.delete(kb_id)


knowledge_service = KnowledgeService()
