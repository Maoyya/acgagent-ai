"""
Embedding 实例工厂（与 app/core/llm.py 对称）。

按知识库的 EmbeddingConfig 创建 OpenAIEmbeddings 实例。所有 embedding 接入均走 OpenAI 兼容协议
（智谱 embedding-3 / 豆包 / 通义 qwen 等）。

api_key：与 chat 共用同一 provider key，复用 app/core/llm.py 的 resolve_api_key
（同 provider 同 key，来源 ACG_AI_LLM_KEY_<PROVIDER>）。未配置抛 ValueError（fail loud）。
base_url：EmbeddingConfig.base_url 为空时按 provider 取默认 OpenAI 兼容端点，便于开箱即用。
"""
from langchain_openai import OpenAIEmbeddings

from app.core.llm import resolve_api_key
from app.models.knowledge_base import EmbeddingConfig

# provider → 默认 OpenAI 兼容 base_url（EmbeddingConfig.base_url 为空时回退）。
# provider 名与 Settings 声明的 llm_key_<provider> 字段对齐（zhipu / qwen / doubao）；
# qwen 即阿里通义，走 dashscope 兼容端点，复用 ACG_AI_LLM_KEY_QWEN。
# 智谱文档强调 base_url 须以 / 结尾，否则可能静默调用失败。
_EMBEDDING_BASE_URL_DEFAULTS: dict[str, str] = {
    "zhipu": "https://open.bigmodel.cn/api/paas/v4/",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
}


def resolve_embedding_key(provider: str) -> str:
    """解析 embedding 的 api_key：与 chat 共用同一 provider key，复用 resolve_api_key。

    未配置 → 抛 ValueError（fail loud，可操作提示由 resolve_api_key 给出）。
    """
    return resolve_api_key(provider)


def build_embeddings(embedding_config: EmbeddingConfig) -> OpenAIEmbeddings:
    """按知识库的 EmbeddingConfig 构造 OpenAIEmbeddings。

    base_url 为空时按 provider 取默认端点；api_key 按 provider 从 .env 取（与 chat 共用）。
    """
    provider = embedding_config.provider
    base_url = embedding_config.base_url or _EMBEDDING_BASE_URL_DEFAULTS.get(provider, "")
    return OpenAIEmbeddings(
        model=embedding_config.model,
        base_url=base_url,
        api_key=resolve_embedding_key(provider),
    )
