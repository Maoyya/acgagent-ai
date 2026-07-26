"""创作工坊 API（挂 /api/v1 前缀、需 X-API-Key、user_id 由 Java 经 X-User-Id 透传）。

端点：
- POST /workshop/plot       剧情流式生成(SSE: content/done/error)，不落库
- POST /workshop/storyboard 分镜结构化(同步 JSON)，不落库
- POST /workshop/characters 角色结构化(同步 JSON)，不落库
"""
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from app.models.common import Result
from app.models.workshop import PlotRequest
from app.services.workshop_service import workshop_service

router = APIRouter(tags=["workshop"])


@router.post("/workshop/plot")
async def plot(
    body: PlotRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """剧情流式生成（SSE）。"""
    return StreamingResponse(
        workshop_service.plot_stream(body, user_id=x_user_id),
        media_type="text/event-stream",
    )


@router.post("/workshop/storyboard")
async def storyboard(body: dict):
    """分镜结构化。body: {plot: str}。"""
    plot = (body or {}).get("plot", "")
    return workshop_service.storyboard(plot)


@router.post("/workshop/characters")
async def characters(body: dict):
    """角色结构化。body: {plot: str}。"""
    plot = (body or {}).get("plot", "")
    return workshop_service.characters(plot)
