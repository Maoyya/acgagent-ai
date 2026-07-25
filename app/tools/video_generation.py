"""图生视频工具 —— 把公网首帧图 + 描述提交为 dashscope 异步任务，返回 task_id。

复用 generation_service（与 REST API /api/v1/generations/videos 同源）。
execute() 只 submit，不轮询：约束同 image_generation。
注意：execute 用 asyncio.run 桥接 sync→async，若在已有 event loop 内调用会抛 RuntimeError；
当前 chat 流程不调 execute 故无影响，未来接入后端 async 执行回路时需改为直接 await。
"""
import asyncio

from app.models.common import Result
from app.models.generation import VideoGenerationRequest
from app.services.generation_service import generation_service
from app.tools.base import BaseAgentTool


class VideoGenerationTool(BaseAgentTool):
    def __init__(self):
        super().__init__(
            tool_id="video_generation",
            name="video_generation",
            description=(
                "根据一张公网可达的图片 URL 生成视频。必须传入 image_url（公网可达，"
                "dashscope 需能拉取）与 prompt，可选 duration（秒，默认 5）。"
                "提交后返回任务 task_id，需轮询取结果。"
            ),
        )

    def execute(self, prompt: str = "", image_url: str = "", duration: int = 5, **kwargs) -> str:
        """提交图生视频任务，返回 task_id + 轮询引导；缺参/失败返回中文提示。"""
        if not prompt:
            return "请提供图生视频提示词"
        if not image_url:
            return "请提供公网可达的首帧图 URL"
        req = VideoGenerationRequest(prompt=prompt, image_url=image_url, duration=duration)
        result: Result = asyncio.run(generation_service.submit_video(req, user_id=None))
        if result.code != 200:
            return f"图生视频提交失败：{result.message}"
        task_id = (result.data or {}).get("task_id")
        if not task_id:
            return "图生视频提交失败：服务返回缺少 task_id"
        return (
            f"已提交图生视频任务，task_id={task_id}。"
            f"用 GET /api/v1/generations/tasks/{task_id} 轮询获取结果。"
        )
