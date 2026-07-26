"""
创作工坊编排服务。

三条入口：
- plot_stream：剧情流式（astream → SSE content/done/error），镜像 prompt_service.generate_stream
- storyboard：分镜结构化（with_structured_output(StoryboardResult) + 同步 invoke），镜像 moderator
- characters：角色结构化（with_structured_output(CharactersResult) + 同步 invoke）

meta-LLM 由 settings 配置，非流式（streaming=False，astream 自带流式）。
缺 api_key 时 plot_stream 发 error 帧、storyboard/characters 返回 Result(code=500)。
"""
import json
import logging

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.workshop_builder import WorkshopBuilder
from app.models.common import Result
from app.models.workshop import (
    CharactersResult,
    PlotRequest,
    StoryboardResult,
)

logger = logging.getLogger("acgagent-ai")


def _sse(obj: dict) -> str:
    """把 dict 序列化成一行 SSE data 帧。"""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


class MetaLLMNotConfigured(RuntimeError):
    """meta-LLM 缺少 api_key 时抛出。"""


class WorkshopService:
    """创作工坊编排：剧情流式 + 分镜/角色结构化。"""

    def __init__(self):
        self._gen_llm = None
        self.builder = WorkshopBuilder()

    def _get_gen_llm(self):
        """懒构造 meta-LLM（非流式 ChatOpenAI）。缺 api_key 抛 MetaLLMNotConfigured。

        镜像 prompt_service._build_gen_llm/_get_gen_llm；可被测试 monkeypatch 替换。
        """
        # 镜像 prompt_service._build_gen_llm/_get_gen_llm：缺 api_key 抛 MetaLLMNotConfigured
        if self._gen_llm is None:
            if not settings.meta_llm_api_key:
                raise MetaLLMNotConfigured("meta llm not configured (set ACG_AI_META_LLM_API_KEY)")
            self._gen_llm = ChatOpenAI(
                model=settings.meta_llm_model,
                base_url=settings.meta_llm_base_url,
                api_key=settings.meta_llm_api_key,
                temperature=0.8,
                streaming=False,  # astream 自带流式
            )
        return self._gen_llm

    async def plot_stream(self, req: PlotRequest):
        """剧情流式：astream → 每个 chunk 一帧 content；末尾 done。镜像 prompt_service.generate_stream。

        SSE 帧格式见 _sse：content 帧带 token 文本，done 帧无载荷，error 帧带 message。
        """
        try:
            llm = self._get_gen_llm()
        except MetaLLMNotConfigured as e:
            yield _sse({"type": "error", "message": str(e)})
            return
        try:
            async for chunk in llm.astream(self.builder.plot_messages(req.story)):
                text = chunk.content or ""
                if text:
                    yield _sse({"type": "content", "content": text})
            yield _sse({"type": "done"})
        except Exception:
            logger.exception("workshop plot stream failed")
            yield _sse({"type": "error", "message": "plot generation failed"})

    def storyboard(self, plot: str) -> Result:
        """分镜结构化：with_structured_output(StoryboardResult, function_calling) → 同步 invoke。

        镜像 moderator.moderate 的结构化模式，但用同步 invoke（meta-LLM 非流式）。
        返回 Result.success(list[Shot])；LLM 调用失败返回 Result(code=500)。
        """
        try:
            llm = self._get_gen_llm()
            structured = llm.with_structured_output(StoryboardResult, method="function_calling")
            result = structured.invoke(self.builder.storyboard_messages(plot))
            return Result.success(data=result.shots)
        except Exception:
            logger.exception("workshop storyboard failed")
            return Result.error(code=500, message="storyboard generation failed")

    def characters(self, plot: str) -> Result:
        """角色结构化：with_structured_output(CharactersResult, function_calling) → 同步 invoke。

        返回 Result.success(list[Character])；LLM 调用失败返回 Result(code=500)。
        """
        try:
            llm = self._get_gen_llm()
            structured = llm.with_structured_output(CharactersResult, method="function_calling")
            result = structured.invoke(self.builder.characters_messages(plot))
            return Result.success(data=result.characters)
        except Exception:
            logger.exception("workshop characters failed")
            return Result.error(code=500, message="characters generation failed")


workshop_service = WorkshopService()
