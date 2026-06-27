"""
单裁判 moderation。

按 PromptMode 取用规则集（RULES），把候选 system_prompt 与规则交给 meta-LLM，
用 with_structured_output 强制返回 ModerationVerdict。temperature=0（在 prompt_service
构造 LLM 时设定），保证裁决稳定可复现。

二期升级路径：当 verdict.confidence 低于阈值时，改走 3 裁判投票（本任务不实现）。
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.prompt import ModerationVerdict, PromptMode

_MOD_SYSTEM = (
    "你是内容合规裁判。逐条判断给定的系统提示词是否违反下列规则，"
    "只返回结构化结果。不得自行放宽或增加规则。"
)

# 按 mode 参数化的规则集。底线规则（暴力/违法/色情）两模式共有。
RULES: dict[PromptMode, list[str]] = {
    PromptMode.acg: [
        "禁止暴力 / 违法犯罪 / 自残 / 色情内容",
        # 二次元风格：acg 模式允许（故此处不列禁令）
    ],
    PromptMode.compliant: [
        "禁止暴力 / 违法犯罪 / 自残 / 色情内容",
        "禁止二次元 / 动漫风格、夸张人设",
    ],
}


class Moderator:
    async def moderate(
        self,
        llm,
        system_prompt: str,
        mode: PromptMode,
        target_capabilities: list[str],
    ) -> ModerationVerdict:
        """对生成产物做单裁判合规校验，返回结构化裁决。"""
        # 拷贝规则列表，避免下方 append 污染全局 RULES
        rules = list(RULES[mode])
        if target_capabilities:
            caps = "、".join(target_capabilities)
            rules.append(f"该 Agent 仅具备以下能力：{caps}；提示词不得承诺这些能力之外的任何功能")

        payload = (
            f"待校验的系统提示词：\n{system_prompt}\n\n"
            f"适用规则（逐条判断）：\n" + "\n".join(f"{i + 1}. {r}" for i, r in enumerate(rules))
            + "\n\n若违反任一规则，passed=false 并在 violated_rules/reasons 说明；否则 passed=true。"
        )

        structured = llm.with_structured_output(ModerationVerdict)
        verdict = await structured.ainvoke([
            SystemMessage(content=_MOD_SYSTEM),
            HumanMessage(content=payload),
        ])
        return verdict
