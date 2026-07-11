# app/services/generation_service.py
"""
媒体生成服务 —— 编排 dashscope 提交/查询 + 任务持久化 + 资产下载。

- submit_image / submit_video：提交 dashscope 异步任务，落任务表（pending），返回 task_id。
- get_task：无状态即时轮询——查 dashscope；SUCCEEDED 立即下载资产到本地，FAILED 记原因。
"""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

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

    async def get_task(self, task_id: str) -> Result:
        """轮询任务：pending/running 查 dashscope；终态直接返回（幂等）。

        不存在 → code=404；查询异常 → code=500；否则返回最新任务态。
        """
        task = generation_store.get(task_id)
        if task is None:
            return Result.error(404, f"task not found: {task_id}")
        if task.status in (GenerationStatus.pending, GenerationStatus.running):
            try:
                await self._refresh(task)
            except Exception as e:
                logger.error("query task %s failed: %s", task_id, e)
                return Result.error(500, f"query failed: {e}")
        return Result.success(generation_store.get(task_id))

    async def _refresh(self, task: GenerationTask) -> None:
        """查 dashscope 并按结果更新任务（无状态即时轮询）。

        查询异常上抛，交 get_task 转 500；下载失败就地置 failed（Fail Loud）。
        """
        r = await _build_client().query_task(task.provider_task_id)
        if r.status == "SUCCEEDED":
            try:
                local_url = await self._download_asset(r.asset_url, task)
            except Exception as e:
                logger.error("download asset for %s failed: %s", task.id, e)
                generation_store.update(
                    task.id, status=GenerationStatus.failed, error=f"资产下载失败: {e}"
                )
                return
            generation_store.update(
                task.id, status=GenerationStatus.succeeded, output_url=local_url
            )
        elif r.status == "FAILED":
            generation_store.update(
                task.id, status=GenerationStatus.failed,
                error=r.error or "generation failed",
            )
        else:  # PENDING / RUNNING
            generation_store.update(task.id, status=GenerationStatus.running)

    async def _download_asset(self, remote_url: str, task: GenerationTask) -> str:
        """下载 dashscope 产物到 storage_root_dir，返回 storage_base_url 形式的持久 URL。

        dashscope 产物 URL 临时（约 24h），必须落本地；资产 HTTP 服务由 Java 侧提供。
        """
        ext = self._ext_of(remote_url) or (
            ".png" if task.type == GenerationType.text_to_image else ".mp4"
        )
        rel = f"generations/{task.type.value}/{task.id}{ext}"
        root = Path(settings.storage_root_dir)
        (root / f"generations/{task.type.value}").mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as dl:
            resp = await dl.get(remote_url)
            resp.raise_for_status()
            (root / rel).write_bytes(resp.content)
        return f"{settings.storage_base_url.rstrip('/')}/{rel}"

    @staticmethod
    def _ext_of(url: str) -> str:
        path = urlparse(url).path
        return Path(path).suffix.lower()


generation_service = GenerationService()
