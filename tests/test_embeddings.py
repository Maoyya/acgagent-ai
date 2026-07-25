"""
Embedding 工厂测试（密钥与 chat 共用，按 provider 从 .env 取；base_url 按 provider 默认回退）。

锁定意图（Rule 9）：
- embedding 复用 chat 的同一 provider key（ACG_AI_LLM_KEY_<PROVIDER>），不另配 embedding key。
- 未配置 provider key → 抛 ValueError（fail loud，消息含变量名）。
- EmbeddingConfig.base_url 为空时按 provider 回退默认 OpenAI 兼容端点（开箱即用）；
  显式 base_url 优先；未知 provider 回退空串。
- 默认 EmbeddingConfig 走智谱 embedding-3（用户选定的 provider）且不再含 api_key 字段。
"""
import pytest

from app.config import settings
from app.core.embeddings import build_embeddings, resolve_embedding_key
from app.models.knowledge_base import EmbeddingConfig


# ---------- resolve_embedding_key：与 chat 共用 provider key ----------

def test_resolve_embedding_key_returns_provider_key(monkeypatch):
    """embedding 取的是 chat 同款 provider key（ACG_AI_LLM_KEY_ZHIPU）——同 provider 同 key。"""
    monkeypatch.setattr(settings, "llm_key_zhipu", "sk-zhipu")
    assert resolve_embedding_key("zhipu") == "sk-zhipu"


def test_resolve_embedding_key_raises_when_missing(monkeypatch):
    """未配置 provider key → ValueError 且消息含变量名（fail loud，给可操作提示）。"""
    monkeypatch.setattr(settings, "llm_key_zhipu", "")
    with pytest.raises(ValueError) as exc:
        resolve_embedding_key("zhipu")
    assert "ACG_AI_LLM_KEY_ZHIPU" in str(exc.value)


def test_resolve_embedding_key_case_insensitive(monkeypatch):
    """provider 大小写不影响解析（与 resolve_api_key 一致）。"""
    monkeypatch.setattr(settings, "llm_key_qwen", "sk-qwen")
    assert resolve_embedding_key("Qwen") == "sk-qwen"


# ---------- build_embeddings：base_url 按 provider 默认回退 ----------

def _capture_openai_embeddings(monkeypatch):
    """把 OpenAIEmbeddings 换成只记录入参的假类，便于断言 model/base_url/api_key（不打网络）。"""
    captured = {}

    class _Fake:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr("app.core.embeddings.OpenAIEmbeddings", _Fake)
    return captured


def test_build_embeddings_uses_provider_default_base_url(monkeypatch):
    """base_url 为空 → 按 provider 取默认 OpenAI 兼容端点（智谱，末尾 /）。"""
    captured = _capture_openai_embeddings(monkeypatch)
    monkeypatch.setattr(settings, "llm_key_zhipu", "sk-zhipu")
    build_embeddings(EmbeddingConfig(provider="zhipu", model="embedding-3"))  # base_url=None
    assert captured["model"] == "embedding-3"
    assert captured["base_url"] == "https://open.bigmodel.cn/api/paas/v4/"
    assert captured["api_key"] == "sk-zhipu"


def test_build_embeddings_respects_explicit_base_url(monkeypatch):
    """显式 base_url 优先于 provider 默认值（per-KB 可覆盖）。"""
    captured = _capture_openai_embeddings(monkeypatch)
    monkeypatch.setattr(settings, "llm_key_zhipu", "sk-zhipu")
    build_embeddings(EmbeddingConfig(provider="zhipu", model="embedding-3", base_url="https://custom.example/v1"))
    assert captured["base_url"] == "https://custom.example/v1"


def test_build_embeddings_qwen_uses_dashscope_endpoint(monkeypatch):
    """qwen（阿里通义）embedding 走 dashscope 兼容端点，复用 ACG_AI_LLM_KEY_QWEN。

    为什么重要：provider 名用 qwen（与 chat provider、llm_key_qwen 字段一致），而非平台名 dashscope——
    若误用 dashscope 会因无 llm_key_dashscope 字段而 fail-loud。锁定这一命名对齐。
    """
    captured = _capture_openai_embeddings(monkeypatch)
    monkeypatch.setattr(settings, "llm_key_qwen", "sk-qwen")
    build_embeddings(EmbeddingConfig(provider="qwen", model="text-embedding-v3"))
    assert captured["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert captured["api_key"] == "sk-qwen"


def test_build_embeddings_unknown_provider_falls_back_to_empty_base_url(monkeypatch):
    """provider 有 key 但无默认 base_url 映射 → base_url 回退空串（交由 SDK 默认，调用方自负）。

    deepseek 是已声明的 key provider，但不在 embedding 默认端点表里（DeepSeek 无 embedding 服务），
    用它来覆盖"有 key、无默认 base_url"的回退分支。
    """
    captured = _capture_openai_embeddings(monkeypatch)
    monkeypatch.setattr(settings, "llm_key_deepseek", "sk-ds")
    build_embeddings(EmbeddingConfig(provider="deepseek", model="x"))
    assert captured["base_url"] == ""


def test_build_embeddings_raises_when_key_missing(monkeypatch):
    """provider key 未配置 → 构造前就抛 ValueError（不静默构造出一个注定 401 的客户端）。"""
    _capture_openai_embeddings(monkeypatch)
    monkeypatch.setattr(settings, "llm_key_zhipu", "")
    with pytest.raises(ValueError):
        build_embeddings(EmbeddingConfig(provider="zhipu", model="embedding-3"))


# ---------- 默认配置：锁定智谱 embedding-3 + 无 api_key 字段 ----------

def test_embedding_config_defaults_to_zhipu_embedding3():
    """新 KB 默认用智谱 embedding-3（用户选定的 provider），开箱即用。"""
    cfg = EmbeddingConfig()
    assert cfg.provider == "zhipu"
    assert cfg.model == "embedding-3"


def test_embedding_config_has_no_api_key_field():
    """api_key 已从 EmbeddingConfig 移除（key 统一从 .env 取，不再散落在 per-KB 配置）。"""
    cfg = EmbeddingConfig()
    assert not hasattr(cfg, "api_key")
