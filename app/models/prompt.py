"""
系统提示词生成相关数据模型。

PromptMode：双模式开关（acg / compliant），决定 moderation 规则集。
所有请求/响应模型走 Pydantic v2，沿用项目统一 Result<T> 信封（见 app/models/common.py）。
"""
from enum import Enum
from pydantic import BaseModel, Field


class PromptMode(str, Enum):
    """提示词生成模式。

    - acg：拥抱二次元/动漫风格，只挡暴力违法/超能力。
    - compliant：中性专业，额外限制二次元风格。
    """
    acg = "acg"
    compliant = "compliant"


class ModerationVerdict(BaseModel):
    """单裁判的结构化裁决结果。confidence 为二期'是否升级多裁判投票'预留。"""
    passed: bool
    violated_rules: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # mode 由 moderator 按入参回填，不依赖 LLM 回显——
    # 各 provider 结构化输出稳定性不一（qwen 会漏回显 mode），入参才是事实来源。
    mode: PromptMode = PromptMode.acg


class CostEstimate(BaseModel):
    """消耗估算。一期 est_completion_tokens 恒为 0（将来对话输出不可预知）。"""
    prompt_tokens: int
    est_completion_tokens: int = 0
    model: str


class PromptGenerateRequest(BaseModel):
    """生成请求：用户零散要求 + 模式 + 可选能力边界。"""
    user_hints: list[str] = Field(description="用户零散要求")
    mode: PromptMode = PromptMode.acg
    target_capabilities: list[str] = Field(
        default_factory=list,
        description="可选；Agent 能力标签，用于'不超能力'约束",
    )


class PromptGenerateResponse(BaseModel):
    """生成响应：提示词正文 + 裁决 + 估算。"""
    system_prompt: str
    mode: PromptMode
    moderation: ModerationVerdict
    estimate: CostEstimate


class ModerateRequest(BaseModel):
    """独立校验请求：Java 校验用户已保存的模板时调用。"""
    system_prompt: str
    mode: PromptMode
    target_capabilities: list[str] = Field(default_factory=list)


class EstimateRequest(BaseModel):
    """独立消耗估算请求。"""
    system_prompt: str
    user_hints: list[str] = Field(default_factory=list)


class PromptBeautifyRequest(BaseModel):
    """润色请求：用传入的 agent llm_config 对草稿做二次润色（不校验、不落库）。

    llm_config 为 dict（Java 传所选 Agent 的 provider/model/base_url/api_key/...），
    service 端解析为 LLMConfig 复用 agent 集成的 key 解析与 base_url 处理。
    """
    system_prompt: str = Field(description="待润色的草稿 system_prompt（通常来自 generate）")
    llm_config: dict = Field(
        description="润色所用 LLM 配置（Java 传所选 Agent 的 provider/model/base_url/api_key/...）"
    )
    mode: PromptMode = PromptMode.acg


class PromptBeautifyResponse(BaseModel):
    """润色响应：仅润色后的 system_prompt。"""
    system_prompt: str
