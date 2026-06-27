"""
提示词生成编排服务。

generate(): 元提示词生成 → 单裁判校验 → 消耗估算 → 偏好写入。
- 校验不通过 → Result(code=403, message=blocked, data=裁决)
- meta-LLM 未配置 → Result(code=500)
- 偏好写入失败 → 仅 warning，不阻断主流程

meta-LLM 由 settings 配置，派生两个实例（生成 temp=0.7、校验 temp=0.0），
非流式（streaming=False），不复用 create_chat_model（其强制 streaming=True）。
"""
import logging

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.cost_estimator import CostEstimator
from app.core.moderator import Moderator
from app.core.prompt_builder import PromptBuilder
from app.db.preference_store import preference_store
from app.models.common import Result
from app.models.prompt import (
    ModerateRequest,
    PromptGenerateRequest,
    PromptGenerateResponse,
    PromptMode,
)

logger = logging.getLogger("acgagent-ai")


class MetaLLMNotConfigured(RuntimeError):
    """meta-LLM 缺少 api_key 时抛出。"""


class PromptService:
    def __init__(self):
        self._gen_llm = None
        self._mod_llm = None
        self.builder = PromptBuilder()
        self.moderator = Moderator()
        self.estimator = CostEstimator(settings.meta_llm_model)
        self.prefs = preference_store

    # -- meta-LLM 构造（可被测试 monkeypatch）--
    def _require_meta_config(self):
        if not settings.meta_llm_api_key:
            raise MetaLLMNotConfigured("meta llm not configured (set ACG_AI_META_LLM_API_KEY)")

    def _build_gen_llm(self):
        self._require_meta_config()
        return ChatOpenAI(
            model=settings.meta_llm_model,
            base_url=settings.meta_llm_base_url,
            api_key=settings.meta_llm_api_key,
            temperature=0.7,
            streaming=False,
        )

    def _build_mod_llm(self):
        self._require_meta_config()
        return ChatOpenAI(
            model=settings.meta_llm_model,
            base_url=settings.meta_llm_base_url,
            api_key=settings.meta_llm_api_key,
            temperature=0.0,
            streaming=False,
        )

    def _get_gen_llm(self):
        if self._gen_llm is None:
            self._gen_llm = self._build_gen_llm()
        return self._gen_llm

    def _get_mod_llm(self):
        if self._mod_llm is None:
            self._mod_llm = self._build_mod_llm()
        return self._mod_llm

    # -- 主入口 --
    async def generate(self, req: PromptGenerateRequest, user_id: str | None) -> Result:
        try:
            gen_llm = self._get_gen_llm()
            mod_llm = self._get_mod_llm()
        except MetaLLMNotConfigured as e:
            return Result.error(code=500, message=str(e))

        try:
            candidate = await self.builder.build(
                gen_llm, req.user_hints, req.mode, req.target_capabilities
            )
            verdict = await self.moderator.moderate(
                mod_llm, candidate, req.mode, req.target_capabilities
            )
        except Exception:
            # LLM 调用/结构化解析失败：受控 500 信封，不抛裸异常（spec §8 Fail Loud）
            logger.exception("prompt generation failed")
            return Result.error(code=500, message="generation failed")
        if not verdict.passed:
            return Result(code=403, message="blocked", data=verdict)

        estimate = self.estimator.estimate(candidate, req.user_hints)
        try:
            self.prefs.record(user_id, req.mode, req.user_hints, candidate)
        except Exception as e:
            logger.warning("preference record failed (best-effort, ignored): %s", e)

        return Result.success(PromptGenerateResponse(
            system_prompt=candidate,
            mode=req.mode,
            moderation=verdict,
            estimate=estimate,
        ))

    async def moderate(self, req: ModerateRequest) -> Result:
        """独立校验：正常返回裁决（code=200，读 passed）；LLM 调用失败时 code=500。"""
        try:
            mod_llm = self._get_mod_llm()
        except MetaLLMNotConfigured as e:
            return Result.error(code=500, message=str(e))
        try:
            verdict = await self.moderator.moderate(
                mod_llm, req.system_prompt, req.mode, req.target_capabilities
            )
        except Exception:
            # 结构化解析失败：受控 500 信封，不抛裸异常（spec §8 Fail Loud）
            logger.exception("prompt moderation failed")
            return Result.error(code=500, message="moderation failed")
        return Result.success(data=verdict)

    def estimate(self, system_prompt: str, user_hints: list[str]) -> Result:
        """独立消耗估算：纯计算，无需 LLM。"""
        return Result.success(data=self.estimator.estimate(system_prompt, user_hints))


prompt_service = PromptService()
