"""
提示词生成编排服务。

generate(): 元提示词生成 → 单裁判校验 → 消耗估算 → 偏好写入。
- 校验不通过 → Result(code=403, message=blocked, data=裁决)
- meta-LLM 未配置 → Result(code=500)
- 偏好写入失败 → 仅 warning，不阻断主流程

meta-LLM 由 settings 配置，派生两个实例（生成 temp=0.7、校验 temp=0.0），
非流式（streaming=False），不复用 create_chat_model（其强制 streaming=True）。
"""
import json
import logging

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.cost_estimator import CostEstimator
from app.core.llm import resolve_api_key
from app.core.moderator import Moderator
from app.core.prompt_builder import PromptBuilder
from app.db.preference_store import preference_store
from app.models.agent import LLMConfig
from app.models.common import Result
from app.models.prompt import (
    ModerateRequest,
    PromptBeautifyRequest,
    PromptBeautifyResponse,
    PromptGenerateRequest,
    PromptMode,
)

logger = logging.getLogger("acgagent-ai")


def _sse(obj: dict) -> str:
    """把 dict 序列化成一行 SSE data 帧。"""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


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
            # 关思考等 vendor 选项：deepseek-v4-pro 等 thinking 模型与 function_calling
            # 的 tool_choice=required 冲突，需在此关 thinking（值由 settings 配置，按 provider 定）。
            extra_body=settings.meta_llm_mod_extra_body or None,
        )

    def _get_gen_llm(self):
        if self._gen_llm is None:
            self._gen_llm = self._build_gen_llm()
        return self._gen_llm

    def _get_mod_llm(self):
        if self._mod_llm is None:
            self._mod_llm = self._build_mod_llm()
        return self._mod_llm

    # -- 主入口（流式）--
    async def generate_stream(self, req: PromptGenerateRequest, user_id: str | None):
        """流式生成 system_prompt（SSE）：逐 token content 事件；末尾 done 事件带 estimate。

        v1.2：generate 内不再做 moderation（合规校验统一由保存闸门 create/update 负责），
        故 generate 恒为「成功流式」——除非 meta-LLM 未配置或调用失败（发 error 事件）。
        偏好写入仍 best-effort。SSE 帧格式见 _sse。
        """
        try:
            gen_llm = self._get_gen_llm()
        except MetaLLMNotConfigured as e:
            yield _sse({"type": "error", "message": str(e)})
            return
        try:
            parts: list[str] = []
            async for chunk in gen_llm.astream(
                self.builder.build_messages(req.user_hints, req.mode, req.target_capabilities)
            ):
                text = chunk.content or ""
                if text:
                    parts.append(text)
                    yield _sse({"type": "content", "content": text})
            candidate = "".join(parts).strip()
            estimate = self.estimator.estimate(candidate, req.user_hints)
            try:
                self.prefs.record(user_id, req.mode, req.user_hints, candidate)
            except Exception as e:
                logger.warning("preference record failed (best-effort, ignored): %s", e)
            yield _sse({"type": "done", "estimate": estimate.model_dump()})
        except Exception:
            logger.exception("prompt generate stream failed")
            yield _sse({"type": "error", "message": "generation failed"})

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

    async def beautify(self, req: PromptBeautifyRequest, user_id: str | None) -> Result:
        """润色：用传入的 agent llm_config 构造 LLM 对草稿做二次润色。不校验、不落库。

        llm_config 解析为 LLMConfig，复用 agent 集成的 resolve_api_key（支持
        ACG_AI_LLM_KEY_<PROVIDER> 兜底）与 base_url 处理；非流式、temperature=0.7。
        LLM 调用失败 → code=500（Fail Loud）；不触发 moderation。
        """
        try:
            cfg = LLMConfig(**(req.llm_config or {}))
        except Exception as e:
            return Result.error(code=500, message=f"beautify llm_config invalid: {e}")
        try:
            api_key = resolve_api_key(cfg.provider, cfg.api_key)
        except ValueError as e:
            return Result.error(code=500, message=str(e))
        try:
            refine_llm = ChatOpenAI(
                model=cfg.model,
                base_url=cfg.base_url,
                api_key=api_key,
                temperature=0.7,
                streaming=False,
            )
            refined = await self.builder.refine(refine_llm, req.system_prompt, req.mode)
        except Exception:
            logger.exception("prompt beautify failed")
            return Result.error(code=500, message="beautify failed")
        return Result.success(data=PromptBeautifyResponse(system_prompt=refined))


prompt_service = PromptService()
