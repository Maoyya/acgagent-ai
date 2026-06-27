"""
LLM 实例工厂。

通过 Agent 配置中的 LLMConfig 创建 ChatOpenAI 实例。
所有模型接入均走 OpenAI 兼容协议，支持豆包/通义/DeepSeek/智谱等提供商。
默认开启 streaming 模式以支持 SSE 流式输出。

api_key 解析（方案 B）：agent 配置里的 api_key 去空白后非空则优先使用（向后兼容）；
否则按 provider 从 Settings 取（ACG_AI_LLM_KEY_<PROVIDER>，pydantic-settings 原生读 .env）；
两处皆空抛 ValueError（fail loud，给出可操作提示）。
"""
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models.agent import LLMConfig


def resolve_api_key(provider: str, explicit: str | None = None) -> str:
    """解析 agent LLM 的 api_key（方案 B）。

    优先级：explicit（agent 配置里的 api_key）去空白后非空 → 用它；
    否则取 settings.llm_key_for(provider)（来自 ACG_AI_LLM_KEY_<PROVIDER>）；
    两处皆空 → 抛 ValueError（fail loud，给出可操作提示）。
    """
    if explicit and explicit.strip():
        return explicit.strip()
    key = settings.llm_key_for(provider)
    if not key:
        raise ValueError(
            f"no api_key for provider '{provider}': "
            f"set llm_config.api_key on the agent, "
            f"or set ACG_AI_LLM_KEY_{provider.upper()} in .env "
            f"(requires a declared llm_key_{provider.lower()} Settings field)"
        )
    return key


def create_chat_model(config: LLMConfig) -> ChatOpenAI:
    """根据 Agent 的 LLM 配置创建聊天模型实例。"""
    return ChatOpenAI(
        model=config.model,
        base_url=config.base_url,
        api_key=resolve_api_key(config.provider, config.api_key),
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        streaming=True,
    )
