"""
媒体生成 API。

三个端点（均挂 /api/v1 前缀、需 X-API-Key、user_id 由 Java 经 X-User-Id 透传）：
- POST /generations/images   文生图，提交任务，返回 task_id
- POST /generations/videos   图生视频，提交任务，返回 task_id
- GET  /generations/tasks/{task_id}  轮询任务
读取 X-User-Id 的方式与 chat.py / prompt.py 一致（Header 直取，不走 Depends）。
"""
from fastapi import APIRouter, Header

from app.models.common import Result
from app.models.generation import ImageGenerationRequest, VideoGenerationRequest
from app.services.generation_service import generation_service

router = APIRouter(tags=["generation"])


@router.post("/generations/images")
async def create_image(
    body: ImageGenerationRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> Result:
    """文生图：提交 dashscope 异步任务，返回 task_id。"""
    return await generation_service.submit_image(body, user_id=x_user_id)


@router.post("/generations/videos")
async def create_video(
    body: VideoGenerationRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> Result:
    """图生视频：需公网可达 image_url；提交后返回 task_id。"""
    return await generation_service.submit_video(body, user_id=x_user_id)


@router.get("/generations/tasks/{task_id}")
async def get_task(task_id: str) -> Result:
    """轮询任务：pending/running 查 dashscope；succeeded 返回本地资产 URL。"""
    return await generation_service.get_task(task_id)
