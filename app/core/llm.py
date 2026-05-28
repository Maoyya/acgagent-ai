"""
LLM 实例工厂。

通过 Agent 配置中的 LLMConfig 创建 ChatOpenAI 实例。
所有模型接入均走 OpenAI 兼容协议，支持豆包/通义/DeepSeek 等提供商。
默认开启 streaming 模式以支持 SSE 流式输出。
"""
from langchain_openai import ChatOpenAI
from app.models.agent import LLMConfig


def create_chat_model(config: LLMConfig) -> ChatOpenAI:
    """根据 Agent 的 LLM 配置创建聊天模型实例。"""
    return ChatOpenAI(
        model=config.model,
        base_url=config.base_url,
        api_key=config.api_key,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        streaming=True,
    )
