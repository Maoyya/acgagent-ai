"""文生图工具 —— 把文字描述提交为 dashscope 异步任务，返回 task_id。

复用 generation_service（与 REST API /api/v1/generations/images 同源）。
execute() 只 submit，不轮询：当前 chat 流程不调 execute（工具回路由前端编排），
此处作为工具能力实现 + 可独立测试 + 备未来后端直连。
注意：execute 用 asyncio.run 桥接 sync→async，若在已有 event loop 内调用会抛 RuntimeError；
当前 chat 流程不调 execute 故无影响，未来接入后端 async 执行回路时需改为直接 await。
"""
import asyncio

from app.models.common import Result
from app.models.generation import ImageGenerationRequest
from app.services.generation_service import generation_service
from app.tools.base import BaseAgentTool


class ImageGenerationTool(BaseAgentTool):
    def __init__(self):
        super().__init__(
            tool_id="image_generation",
            name="image_generation",
            description=(
                "根据文字描述生成图片。传入 prompt（必填），可选 size（如 1024*1024）、"
                "n（生成数量）。提交后返回任务 task_id，需轮询取结果。"
            ),
        )

    def execute(self, prompt: str = "", size: str = "1024*1024", n: int = 1, **kwargs) -> str:
        """提交文生图任务，返回 task_id + 轮询引导；缺参/失败返回中文提示。"""
        if not prompt:
            return "请提供文生图提示词"
        req = ImageGenerationRequest(prompt=prompt, size=size, n=n)
        result: Result = asyncio.run(generation_service.submit_image(req, user_id=None))
        if result.code != 200:
            return f"文生图提交失败：{result.message}"
        task_id = (result.data or {}).get("task_id")
        if not task_id:
            return "文生图提交失败：服务返回缺少 task_id"
        return (
            f"已提交文生图任务，task_id={task_id}。"
            f"用 GET /api/v1/generations/tasks/{task_id} 轮询获取结果。"
        )
