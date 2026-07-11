"""结构化知识条目 REST API。"""
from typing import Optional
from fastapi import APIRouter

from app.models.common import Result
from app.models.knowledge_entry import (
    KnowledgeEntryCreateRequest, KnowledgeEntryUpdateRequest,
)
from app.services.knowledge_entry_service import knowledge_entry_service

router = APIRouter(tags=["knowledge-entry"])


@router.get("/knowledge-entries")
async def list_knowledge_entries(
    type: Optional[str] = None, scope: Optional[str] = None,
    user_id: Optional[str] = None, q: Optional[str] = None,
):
    return Result.success(data=knowledge_entry_service.list(type, scope, user_id, q))


@router.get("/knowledge-entries/{entry_id}")
async def get_knowledge_entry(entry_id: str):
    try:
        entry = knowledge_entry_service.get(entry_id)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    if entry is None:
        return Result.error(code=404, message=f"Knowledge entry not found: {entry_id}")
    return Result.success(data=entry)


@router.post("/knowledge-entries")
async def create_knowledge_entry(body: KnowledgeEntryCreateRequest):
    try:
        entry = knowledge_entry_service.create(body)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    return Result.success(data=entry)


@router.put("/knowledge-entries/{entry_id}")
async def update_knowledge_entry(entry_id: str, body: KnowledgeEntryUpdateRequest):
    try:
        entry = knowledge_entry_service.update(entry_id, body)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    if entry is None:
        return Result.error(code=404, message=f"Knowledge entry not found: {entry_id}")
    return Result.success(data=entry)


@router.delete("/knowledge-entries/{entry_id}")
async def delete_knowledge_entry(entry_id: str):
    try:
        ok = knowledge_entry_service.delete(entry_id)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    if not ok:
        return Result.error(code=404, message=f"Knowledge entry not found: {entry_id}")
    return Result.success()
