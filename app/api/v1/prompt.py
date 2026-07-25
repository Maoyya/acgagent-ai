"""
系统提示词生成 API。

四个端点（均挂 /api/v1 前缀、需 X-API-Key、user_id 由 Java 经 X-User-Id 透传）：
- POST /prompts/generate  流式生成(SSE)：逐 token content 事件 + done 事件带 estimate（不校验/不落库）
- POST /prompts/beautify  用传入 agent llm_config 润色草稿（不校验/不落库）
- POST /prompts/moderate  独立校验（Java 校验用户已保存模板 / 保存闸门）
- POST /prompts/estimate  独立消耗估算
读取 X-User-Id 的方式与 chat.py 一致（Header 直取，不走 Depends）。
"""
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from app.models.common import Result
from app.models.prompt import (
    EstimateRequest,
    ModerateRequest,
    PromptBeautifyRequest,
    PromptGenerateRequest,
)
from app.services.prompt_service import prompt_service

router = APIRouter(tags=["prompt"])


@router.post("/prompts/generate")
async def generate(
    body: PromptGenerateRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """流式生成系统提示词（SSE）：content 事件逐 token；done 事件带 estimate；不校验/不落库。"""
    return StreamingResponse(
        prompt_service.generate_stream(body, user_id=x_user_id),
        media_type="text/event-stream",
    )


@router.post("/prompts/moderate")
async def moderate(body: ModerateRequest) -> Result:
    """独立合规校验，正常返回裁决（code=200，读 data.passed）；LLM 失败时 code=500。"""
    return await prompt_service.moderate(body)


@router.post("/prompts/estimate")
async def estimate(body: EstimateRequest) -> Result:
    """独立消耗估算，纯计算。"""
    return prompt_service.estimate(body.system_prompt, body.user_hints)


@router.post("/prompts/beautify")
async def beautify(
    body: PromptBeautifyRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> Result:
    """用传入 agent llm_config 润色草稿（不校验、不落库；LLM 失败 code=500）。"""
    return await prompt_service.beautify(body, user_id=x_user_id)
