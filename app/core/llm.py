"""
LLM 实例工厂。

通过 Agent 配置中的 LLMConfig 创建 ChatOpenAI 实例。
所有模型接入均走 OpenAI 兼容协议，支持豆包/通义/DeepSeek 等提供商。
默认开启 streaming 模式以支持 SSE 流式输出。

api_key 解析（方案 B）：agent 配置里的 api_key 非空时优先使用（向后兼容）；
为空时按 provider 从环境变量 ACG_AI_LLM_KEY_<PROVIDER> 取；两处皆空抛 ValueError。
"""
import os

from langchain_openai import ChatOpenAI
from app.models.agent import LLMConfig


def resolve_api_key(provider: str, explicit: str | None = None) -> str:
    """解析 agent LLM 的 api_key（方案 B）。

    优先级：explicit（agent 配置里的 api_key）非空 → 用它；
    否则取环境变量 ACG_AI_LLM_KEY_<PROVIDER>（provider 转大写）；
    两处皆空 → 抛 ValueError（fail loud，给出可操作提示）。
    """
    if explicit:
        return explicit
    env_name = f"ACG_AI_LLM_KEY_{provider.upper()}"
    key = os.getenv(env_name)
    if not key:
        raise ValueError(
            f"no api_key for provider '{provider}': "
            f"set {env_name} in environment, or agent llm_config.api_key"
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
