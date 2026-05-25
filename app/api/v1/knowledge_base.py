from fastapi import APIRouter

from app.models.knowledge_base import KnowledgeBaseCreateRequest, KnowledgeBaseUpdateRequest
from app.models.common import Result
from app.services.knowledge_service import knowledge_service

router = APIRouter(tags=["knowledge-base"])


@router.get("/knowledge-bases")
async def list_knowledge_bases():
    return Result.success(data=knowledge_service.list_all())


@router.get("/knowledge-bases/{kb_id}")
async def get_knowledge_base(kb_id: str):
    kb = knowledge_service.get(kb_id)
    if kb is None:
        return Result.error(code=404, message=f"Knowledge base not found: {kb_id}")
    return Result.success(data=kb)


@router.post("/knowledge-bases")
async def create_knowledge_base(body: KnowledgeBaseCreateRequest):
    kb = knowledge_service.create(body)
    return Result.success(data=kb)


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(kb_id: str, body: KnowledgeBaseUpdateRequest):
    kb = knowledge_service.update(kb_id, body)
    if kb is None:
        return Result.error(code=404, message=f"Knowledge base not found: {kb_id}")
    return Result.success(data=kb)


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    ok = knowledge_service.delete(kb_id)
    if not ok:
        return Result.error(code=404, message=f"Knowledge base not found: {kb_id}")
    return Result.success()
