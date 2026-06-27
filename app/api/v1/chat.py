"""
对话 API 端点。

根据 stream 参数决定响应模式：
- stream=true（默认）：返回 SSE 流式响应（text/event-stream）
- stream=false：返回完整 JSON 响应
"""
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from app.core.llm import resolve_api_key
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
    """对话接口。先校验 Agent 存在且启用，再根据 stream 参数分流。"""
    agent_config = agent_service.get(agent_id)
    if agent_config is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    if agent_config.status != 1:
        return Result.error(code=400, message=f"Agent is disabled: {agent_id}")

    # 预检 LLM key 可解析性：缺失则在分流前返回受控 500 信封，避免 ValueError
    # 在 sync 路径裸奔成无信封 500、或在 stream 的 async gen 中途崩溃（C1/C2）。
    try:
        resolve_api_key(agent_config.llm_config.provider, agent_config.llm_config.api_key)
    except ValueError as e:
        return Result.error(code=500, message=str(e))

    if body.stream:
        # SSE 流式响应：禁用缓冲确保实时推送
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
