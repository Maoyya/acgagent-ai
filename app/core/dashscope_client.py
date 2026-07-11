"""
dashscope（通义万相）异步任务 HTTP 客户端。

文生图 / 图生视频 均为异步任务：提交（X-DashScope-Async: enable）拿 task_id →
轮询 GET /tasks/{id}。不依赖 dashscope SDK，直接 httpx 调 REST（OpenAI 兼容之外）。
端点/字段以官方文档为准：
- 文生图 https://help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference
- 图生视频 https://help.aliyun.com/zh/model-studio/legacy-image-to-video-api-reference/
"""
from typing import Optional

import httpx
from pydantic import BaseModel


class QueryResult(BaseModel):
    """dashscope 任务查询结果（归一化后供 service 消费）。"""

    status: str  # PENDING / RUNNING / SUCCEEDED / FAILED（dashscope 原文）
    asset_url: Optional[str] = None  # SUCCEEDED 时的产物 URL（图 results[0].url 或视频 video_url）
    error: Optional[str] = None  # FAILED 时的原因


class DashScopeError(Exception):
    """dashscope 调用异常（网络/非 2xx/解析失败），由 service 捕获转 code=500。"""


class DashScopeClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        image_model: str,
        video_model: str,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self._base = base_url.rstrip("/")
        self._image_model = image_model
        self._video_model = video_model
        self._transport = transport
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _client(self):
        # 每次调用新建短命 client，由 async with 负责 aclose——不泄漏连接池
        return httpx.AsyncClient(
            transport=self._transport,
            headers=self._headers,
            timeout=httpx.Timeout(60.0),
        )

    async def _submit(
        self, path: str, model: str, data_input: dict, parameters: dict
    ) -> str:
        """提交异步任务，返回 provider task_id。"""
        async with self._client() as c:
            resp = await c.post(
                f"{self._base}{path}",
                json={"model": model, "input": data_input, "parameters": parameters},
                headers={"X-DashScope-Async": "enable"},
            )
        if resp.status_code != 200:
            raise DashScopeError(f"submit failed: {resp.status_code} {resp.text}")
        task_id = (resp.json().get("output") or {}).get("task_id")
        if not task_id:
            raise DashScopeError(f"submit returned no task_id: {resp.text}")
        return task_id

    async def submit_text_to_image(self, prompt: str, size: str, n: int) -> str:
        return await self._submit(
            "/services/aigc/text2image/image-synthesis",
            self._image_model,
            {"prompt": prompt},
            {"size": size, "n": n},
        )

    async def submit_image_to_video(
        self, prompt: str, image_url: str, duration: int
    ) -> str:
        return await self._submit(
            "/services/aigc/multimedia-generation/video-synthesis",
            self._video_model,
            {"prompt": prompt, "img_url": image_url},
            {"duration": duration},
        )

    async def query_task(self, provider_task_id: str) -> QueryResult:
        async with self._client() as c:
            resp = await c.get(f"{self._base}/tasks/{provider_task_id}")
        if resp.status_code != 200:
            raise DashScopeError(f"query failed: {resp.status_code} {resp.text}")
        out = resp.json().get("output") or {}
        status = out.get("task_status", "PENDING")
        if status == "SUCCEEDED":
            results = out.get("results") or []
            asset_url = (results[0].get("url") if results else None) or out.get(
                "video_url"
            )
            return QueryResult(status=status, asset_url=asset_url)
        if status == "FAILED":
            return QueryResult(status=status, error=out.get("message") or str(out))
        return QueryResult(status=status)  # PENDING / RUNNING
