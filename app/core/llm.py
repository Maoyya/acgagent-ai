"""
LLM 实例工厂。

通过 Agent 配置中的 LLMConfig 创建 ChatOpenAI 实例。
所有模型接入均走 OpenAI 兼容协议，支持豆包/通义/DeepSeek/智谱等提供商。
默认开启 streaming 模式以支持 SSE 流式输出。

api_key 解析：统一按 provider 从 Settings 取（ACG_AI_LLM_KEY_<PROVIDER>，pydantic-settings 原生读 .env）；
agent 配置不再携带 api_key（key 唯一来源为 .env）。未配置抛 ValueError（fail loud，给出可操作提示）。
"""
import openai
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models.agent import LLMConfig


def resolve_api_key(provider: str) -> str:
    """解析 agent LLM 的 api_key：按 provider 从 Settings 取（ACG_AI_LLM_KEY_<PROVIDER>）。

    agent 配置不再携带 api_key；密钥唯一来源为 .env。未配置 → 抛 ValueError（fail loud，给出可操作提示）。
    """
    key = settings.llm_key_for(provider)
    if not key:
        raise ValueError(
            f"no api_key for provider '{provider}': "
            f"set ACG_AI_LLM_KEY_{provider.upper()} in .env "
            f"(requires a declared llm_key_{provider.lower()} Settings field)"
        )
    return key


def create_chat_model(config: LLMConfig) -> ChatOpenAI:
    """根据 Agent 的 LLM 配置创建聊天模型实例。"""
    return ChatOpenAI(
        model=config.model,
        base_url=config.base_url,
        api_key=resolve_api_key(config.provider),
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        streaming=True,
    )


def ping_llm(config: LLMConfig, timeout: float = 15.0) -> None:
    """发起一次最小 completion 验证 LLM 连通性。成功 return；失败 raise ValueError(中文原因)。

    独立构造一个非流式、max_tokens=1 的 ChatOpenAI（不复用 create_chat_model，
    后者为对话用、streaming=True 且无超时）。key 解析复用 resolve_api_key。
    RateLimitError 视为可用（已成功触达 provider 并通过到限流判定）。
    """
    api_key = resolve_api_key(config.provider)  # 缺失抛 ValueError（原样传播）
    model = ChatOpenAI(
        model=config.model,
        base_url=config.base_url,
        api_key=api_key,
        max_tokens=1,
        temperature=0,
        streaming=False,
        timeout=timeout,
    )
    try:
        model.invoke([HumanMessage(content="ping")])
    except openai.AuthenticationError:
        raise ValueError(
            f"Agent LLM 不可用: API Key 鉴权失败，"
            f"请检查 ACG_AI_LLM_KEY_{config.provider.upper()}"
        )
    except openai.NotFoundError:
        raise ValueError(
            f"Agent LLM 不可用: 模型 '{config.model}' 不存在，请检查 llm_config.model"
        )
    except openai.RateLimitError:
        return  # 视为可用
    except openai.APIConnectionError:  # 含 APITimeoutError（其子类）
        raise ValueError(
            f"Agent LLM 不可用: 无法连接 base_url（或超时 {timeout}s），请检查 llm_config.base_url"
        )
    except Exception as e:
        raise ValueError(f"Agent LLM 不可用: LLM 校验失败: {e}")
