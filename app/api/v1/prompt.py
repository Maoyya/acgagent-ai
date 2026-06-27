"""
系统提示词生成 API。

三个端点（均挂 /api/v1 前缀、需 X-API-Key、user_id 由 Java 经 X-User-Id 透传）：
- POST /prompts/generate  组装→校验→估算→写偏好，一次返回
- POST /prompts/moderate  独立校验（Java 校验用户已保存模板）
- POST /prompts/estimate  独立消耗估算
读取 X-User-Id 的方式与 chat.py 一致（Header 直取，不走 Depends）。
"""
from fastapi import APIRouter, Header

from app.models.common import Result
from app.models.prompt import EstimateRequest, ModerateRequest, PromptGenerateRequest
from app.services.prompt_service import prompt_service

router = APIRouter(tags=["prompt"])


@router.post("/prompts/generate")
async def generate(
    body: PromptGenerateRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> Result:
    """生成系统提示词。校验不通过时返回 code=403。"""
    return await prompt_service.generate(body, user_id=x_user_id)


@router.post("/prompts/moderate")
async def moderate(body: ModerateRequest) -> Result:
    """独立合规校验，正常返回裁决（code=200，读 data.passed）；LLM 失败时 code=500。"""
    return await prompt_service.moderate(body)


@router.post("/prompts/estimate")
async def estimate(body: EstimateRequest) -> Result:
    """独立消耗估算，纯计算。"""
    return prompt_service.estimate(body.system_prompt, body.user_hints)
