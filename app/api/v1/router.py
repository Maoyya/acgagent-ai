from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router
from app.api.v1.agent import router as agent_router
from app.api.v1.knowledge_base import router as kb_router
from app.api.v1.document import router as doc_router
from app.api.v1.tool import router as tool_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
router.include_router(agent_router)
router.include_router(kb_router)
router.include_router(doc_router)
router.include_router(tool_router)
