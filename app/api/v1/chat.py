from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest
from app.models.common import Result
from app.services.chat_service import chat_service
from app.services.agent_service import agent_service

router = APIRouter(tags=["chat"])


@router.post("/chat/{agent_id}/completions")
async def chat_completions(
    agent_id: str,
    body: ChatRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    agent_config = agent_service.get(agent_id)
    if agent_config is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    if agent_config.status != 1:
        return Result.error(code=400, message=f"Agent is disabled: {agent_id}")

    if body.stream:
        return StreamingResponse(
            chat_service.stream_chat(
                agent_config=agent_config,
                message=body.message,
                conversation_id=body.conversation_id,
                user_id=x_user_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await chat_service.sync_chat(
            agent_config=agent_config,
            message=body.message,
            conversation_id=body.conversation_id,
            user_id=x_user_id,
        )
        return Result.success(data=result)
