"""
LLM 工厂 api_key 解析测试（方案 B：密钥集中到 .env，按 provider 分键）。

覆盖的业务意图（测"为什么"，不只是"做什么"）：
- agent 自带 api_key 时优先用自带 → 保证现有 agent（如 data/agents 里 api_key="sk-test"）
  行为不变，密钥集中化是 opt-in（显式置空才走 env）。
- agent api_key 为空时按 provider 从 env 回退 → 密钥集中管理的核心收益：轮换只改一处。
- 两处皆空时抛清晰 ValueError → fail loud，给"该设哪个变量"的可操作提示，
  而不是让调用链走到 provider 才报晦涩的 401。
- provider 名大小写不敏感 → 配置容错。
"""
import pytest

from app.core.llm import create_chat_model, resolve_api_key
from app.models.agent import LLMConfig


def test_explicit_api_key_overrides_env(monkeypatch):
    """agent 自带 api_key 时，即使 env 也配了同名 provider 的 key，仍用自带的。"""
    monkeypatch.setenv("ACG_AI_LLM_KEY_ZHIPU", "sk-from-env")
    assert resolve_api_key("zhipu", "sk-explicit") == "sk-explicit"


def test_falls_back_to_env_by_provider(monkeypatch):
    """agent api_key 为空时，按 provider 名取对应 env 变量。"""
    monkeypatch.setenv("ACG_AI_LLM_KEY_ZHIPU", "sk-from-env")
    assert resolve_api_key("zhipu", "") == "sk-from-env"


def test_missing_key_raises_with_actionable_message(monkeypatch):
    """agent 无 key 且 env 也无对应 provider key 时，抛 ValueError 且消息含 env 变量名。"""
    monkeypatch.delenv("ACG_AI_LLM_KEY_DEEPSEEK", raising=False)
    with pytest.raises(ValueError) as exc:
        resolve_api_key("deepseek", "")
    assert "ACG_AI_LLM_KEY_DEEPSEEK" in str(exc.value)


def test_provider_name_is_case_insensitive(monkeypatch):
    """provider 大小写不影响 env 变量名解析（统一转大写）。"""
    monkeypatch.setenv("ACG_AI_LLM_KEY_QWEN", "sk-qwen")
    assert resolve_api_key("Qwen", "") == "sk-qwen"
    assert resolve_api_key("qwen", "") == "sk-qwen"


def test_create_chat_model_raises_when_key_unresolvable(monkeypatch):
    """create_chat_model 接线正确：key 无法解析时，在构造模型前就抛 ValueError。"""
    monkeypatch.delenv("ACG_AI_LLM_KEY_DEEPSEEK", raising=False)
    config = LLMConfig(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key="",
    )
    with pytest.raises(ValueError):
        create_chat_model(config)
