"""
API v1 路由汇总。

所有子路由挂载在 /api/v1 前缀下，统一经过 API Key 认证。
"""
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router
from app.api.v1.agent import router as agent_router
from app.api.v1.knowledge_base import router as kb_router
from app.api.v1.document import router as doc_router
from app.api.v1.tool import router as tool_router
from app.api.v1.prompt import router as prompt_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
router.include_router(agent_router)
router.include_router(kb_router)
router.include_router(doc_router)
router.include_router(tool_router)
router.include_router(prompt_router)
