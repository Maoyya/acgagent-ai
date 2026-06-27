"""
LLM 工厂 api_key 解析测试（方案 B：密钥集中到 .env，按 provider 分键）。

机制（C 重构后）：对话 LLM 密钥是 Settings 字段（llm_key_<provider>），由
pydantic-settings 从 .env 原生读取；resolve_api_key 改读 settings.llm_key_for，
不再用 os.getenv（消除 ".env 不进 os.environ" 的根因）。

覆盖的业务意图（测"为什么"，不只是"做什么"）：
- agent 自带 api_key（去空白后非空）优先 → 现有 agent 行为不变，集中化是 opt-in。
- agent api_key 为空/空白时按 provider 回退到 Settings → 密钥集中管理，轮换只改一处。
- 两处皆空抛清晰 ValueError → fail loud，给"该设哪个变量"的可操作提示。
- provider 大小写不敏感。
- Settings 原生从 .env 读 LLM key（根因：无需 load_dotenv 桥接 os.environ）。
- extra=forbid 恢复 fail-loud：未知 ACG_AI_* 启动即报错，防止拼写错误被静默忽略。
"""
import pytest

from app.config import Settings, settings
from app.core.llm import create_chat_model, resolve_api_key
from app.models.agent import LLMConfig


def test_explicit_api_key_overrides_settings(monkeypatch):
    """agent 自带 api_key 时，即使 Settings 也配了同名 provider 的 key，仍用自带的。"""
    monkeypatch.setattr(settings, "llm_key_zhipu", "sk-from-settings")
    assert resolve_api_key("zhipu", "sk-explicit") == "sk-explicit"


def test_falls_back_to_settings_by_provider(monkeypatch):
    """agent api_key 为空时，按 provider 从 Settings 取对应 key。"""
    monkeypatch.setattr(settings, "llm_key_zhipu", "sk-from-settings")
    assert resolve_api_key("zhipu", "") == "sk-from-settings"


def test_whitespace_explicit_falls_back_to_settings(monkeypatch):
    """agent api_key 仅空白时视为空，回退到 Settings（避免空白 key 被当真值导致 401）。"""
    monkeypatch.setattr(settings, "llm_key_zhipu", "sk-from-settings")
    assert resolve_api_key("zhipu", "   ") == "sk-from-settings"


def test_missing_key_raises_with_actionable_message(monkeypatch):
    """agent 无 key 且 Settings 也无对应 provider key 时，抛 ValueError 且消息含变量名。"""
    monkeypatch.setattr(settings, "llm_key_deepseek", "")
    with pytest.raises(ValueError) as exc:
        resolve_api_key("deepseek", "")
    assert "ACG_AI_LLM_KEY_DEEPSEEK" in str(exc.value)


def test_provider_name_case_insensitive(monkeypatch):
    """provider 大小写不影响解析（统一转小写匹配 Settings 字段）。"""
    monkeypatch.setattr(settings, "llm_key_qwen", "sk-qwen")
    assert resolve_api_key("Qwen", "") == "sk-qwen"
    assert resolve_api_key("qwen", "") == "sk-qwen"


def test_create_chat_model_raises_when_key_unresolvable(monkeypatch):
    """create_chat_model 接线正确：key 无法解析时，构造模型前就抛 ValueError。"""
    monkeypatch.setattr(settings, "llm_key_deepseek", "")
    config = LLMConfig(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key="",
    )
    with pytest.raises(ValueError):
        create_chat_model(config)


def test_llm_key_for_reads_provider_key_from_env_file(tmp_path):
    """Settings 原生从 .env 读取 ACG_AI_LLM_KEY_<PROVIDER>（根因修复：无需 load_dotenv 桥接）。

    为什么重要：这是方案 B 能工作的根基——key 写进 .env 即被 Settings 读到，
    resolve_api_key 经 settings.llm_key_for 取用，不再依赖 .env 进 os.environ。
    """
    env_file = tmp_path / ".env"
    env_file.write_text("ACG_AI_LLM_KEY_ZHIPU=sk-from-file\n", encoding="utf-8")
    s = Settings(_env_file=str(env_file))
    assert s.llm_key_for("zhipu") == "sk-from-file"


def test_settings_rejects_unknown_acg_ai_var(tmp_path):
    """extra=forbid：未知 ACG_AI_* 变量启动即 ValidationError（恢复 fail-loud）。

    为什么重要：防止 ACG_AI_* 拼写错误（如 ACG_AI_APIKEY 误写）被静默忽略，
    违反 Rule 12 fail-loud。
    """
    env_file = tmp_path / ".env"
    env_file.write_text("ACG_AI_TOTALLY_UNKNOWN=oops\n", encoding="utf-8")
    with pytest.raises(Exception):
        Settings(_env_file=str(env_file))


def test_llm_key_for_does_not_collide_with_method_name():
    """provider 名碰巧等于 Settings 上已存在属性的后缀（如方法 llm_key_for 的 'for'）时，
    llm_key_for 必须返回 "" 而非那个属性/方法（A1）。

    为什么重要：getattr 默认会把 'llm_key_for' 这个方法对象（truthy）返回，
    导致 resolve_api_key 把 bound method 当成 api_key 传给 ChatOpenAI，
    绕过 fail-loud——本该抛 ValueError 的"未配置"被静默吞掉。
    """
    assert settings.llm_key_for("for") == ""
