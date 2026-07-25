"""
提示词生成器。

构造一段'元提示词'交给 meta-LLM（非流式 ainvoke），让它根据用户零散要求
组装成一段可用的 system_prompt 正文。temperature≈0.7（在 prompt_service 构造 LLM 时设定）。
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.prompt import PromptMode

_META_SYSTEM = "你是一名资深提示词工程师，擅长把用户的零散要求组装成一段清晰、可用的 Agent 系统提示词。"

_STYLE = {
    PromptMode.acg: "风格：可使用二次元/动漫人设语气，但仍保持专业。",
    PromptMode.compliant: "风格：中性专业，避免二次元/动漫风格与夸张人设。",
}

_REFINE_SYSTEM = (
    "你是一名资深提示词工程师，擅长在保留原意与风格约束的前提下，"
    "让系统提示词的表达更流畅、专业。"
)


class PromptBuilder:
    async def build(
        self,
        llm,
        user_hints: list[str],
        mode: PromptMode,
        target_capabilities: list[str],
    ) -> str:
        """根据用户要求生成 system_prompt 正文。"""
        hints_text = "\n".join(f"- {h}" for h in user_hints) or "-（用户未提供具体要求）"
        cap_text = ""
        if target_capabilities:
            cap_text = f"\n能力边界：该 Agent 仅具备 {('、'.join(target_capabilities))}；提示词不得承诺这些能力之外的功能。"

        payload = (
            f"{_STYLE[mode]}\n"
            f"用户要求：\n{hints_text}{cap_text}\n"
            f"输出：只输出系统提示词正文，不要解释、不要前缀、不要 Markdown 代码块。"
        )

        resp = await llm.ainvoke([
            SystemMessage(content=_META_SYSTEM),
            HumanMessage(content=payload),
        ])
        return (resp.content or "").strip()

    async def refine(self, llm, system_prompt: str, mode: PromptMode) -> str:
        """对草稿 system_prompt 做二次润色（保留原意、不增删能力承诺，贴合 mode 风格）。

        供 beautify 使用：llm 由调用方用所选 Agent 的 llm_config 构造（非 meta-LLM）。
        """
        payload = (
            f"{_STYLE[mode]}\n"
            f"下面是一段 Agent 系统提示词草稿，请在**保留原意、不增删能力承诺**的前提下，"
            f"使表达更流畅、专业。\n"
            f"---\n{system_prompt}\n---\n"
            f"输出：只输出润色后的系统提示词正文，不要解释、不要前缀、不要 Markdown 代码块。"
        )
        resp = await llm.ainvoke([
            SystemMessage(content=_REFINE_SYSTEM),
            HumanMessage(content=payload),
        ])
        return (resp.content or "").strip()
