# app/services/generation_service.py
"""
媒体生成服务 —— 编排 dashscope 提交/查询 + 任务持久化 + 资产下载。

- submit_image / submit_video：提交 dashscope 异步任务，落任务表（pending），返回 task_id。
- get_task：无状态即时轮询——查 dashscope；SUCCEEDED 立即下载资产到本地，FAILED 记原因。
"""
import logging
import uuid
from datetime import datetime

import httpx

from app.config import settings
from app.core.dashscope_client import DashScopeClient
from app.db.generation_store import generation_store
from app.models.common import Result
from app.models.generation import (
    GenerationStatus,
    GenerationTask,
    GenerationType,
)

logger = logging.getLogger("acgagent-ai")


def _build_client() -> DashScopeClient:
    """用 settings 构造 dashscope 客户端（测试 seam：monkeypatch 此函数）。"""
    return DashScopeClient(
        api_key=settings.generation_api_key,
        base_url=settings.generation_base_url,
        image_model=settings.generation_image_model,
        video_model=settings.generation_video_model,
    )


class GenerationService:
    async def submit_image(self, req, user_id) -> Result:
        """文生图：提交 dashscope 任务，落 pending 任务表，返回 task_id。"""
        if not settings.generation_api_key:
            return Result.error(500, "generation api key not configured")
        try:
            provider_task_id = await _build_client().submit_text_to_image(
                req.prompt, req.size, req.n
            )
        except Exception as e:
            logger.error("submit image failed: %s", e)
            return Result.error(500, f"submit failed: {e}")
        now = datetime.now()
        task = GenerationTask(
            id=uuid.uuid4().hex[:12],
            type=GenerationType.text_to_image,
            status=GenerationStatus.pending,
            prompt=req.prompt,
            provider_task_id=provider_task_id,
            created_at=now,
            updated_at=now,
        )
        generation_store.create(task)
        return Result.success({"task_id": task.id})

    async def submit_video(self, req, user_id) -> Result:
        """图生视频：需公网 image_url；提交后落 pending 任务表，返回 task_id。"""
        if not settings.generation_api_key:
            return Result.error(500, "generation api key not configured")
        try:
            provider_task_id = await _build_client().submit_image_to_video(
                req.prompt, req.image_url, req.duration
            )
        except Exception as e:
            logger.error("submit video failed: %s", e)
            return Result.error(500, f"submit failed: {e}")
        now = datetime.now()
        task = GenerationTask(
            id=uuid.uuid4().hex[:12],
            type=GenerationType.image_to_video,
            status=GenerationStatus.pending,
            prompt=req.prompt,
            input_image_url=req.image_url,
            provider_task_id=provider_task_id,
            created_at=now,
            updated_at=now,
        )
        generation_store.create(task)
        return Result.success({"task_id": task.id})


generation_service = GenerationService()
