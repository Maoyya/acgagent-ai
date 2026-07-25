"""
LLM 工厂 api_key 解析测试（密钥集中到 .env，按 provider 分键）。

机制：对话 LLM 密钥是 Settings 字段（llm_key_<provider>），由 pydantic-settings 从 .env
原生读取；resolve_api_key(provider) 读 settings.llm_key_for。agent 配置不再携带 api_key——
密钥唯一来源为 .env（集中管理，轮换只改一处）。

覆盖的业务意图（测"为什么"，不只是"做什么"）：
- 按 provider 从 Settings 取对应 key → 密钥集中管理，轮换只改一处。
- 未配置抛清晰 ValueError → fail loud，给"该设哪个变量"的可操作提示。
- provider 大小写不敏感。
- Settings 原生从 .env 读 LLM key（根因：无需 load_dotenv 桥接 os.environ）。
- extra=forbid 恢复 fail-loud：未知 ACG_AI_* 启动即报错，防止拼写错误被静默忽略。
"""
import pytest

from app.config import Settings, settings
from app.core.llm import create_chat_model, resolve_api_key
from app.models.agent import LLMConfig


def test_resolves_provider_key_from_settings(monkeypatch):
    """按 provider 从 Settings 取对应 key（密钥集中管理，轮换只改一处）。"""
    monkeypatch.setattr(settings, "llm_key_zhipu", "sk-from-settings")
    assert resolve_api_key("zhipu") == "sk-from-settings"


def test_missing_key_raises_with_actionable_message(monkeypatch):
    """Settings 无对应 provider key 时，抛 ValueError 且消息含变量名。"""
    monkeypatch.setattr(settings, "llm_key_deepseek", "")
    with pytest.raises(ValueError) as exc:
        resolve_api_key("deepseek")
    assert "ACG_AI_LLM_KEY_DEEPSEEK" in str(exc.value)


def test_provider_name_case_insensitive(monkeypatch):
    """provider 大小写不影响解析（统一转小写匹配 Settings 字段）。"""
    monkeypatch.setattr(settings, "llm_key_qwen", "sk-qwen")
    assert resolve_api_key("Qwen") == "sk-qwen"
    assert resolve_api_key("qwen") == "sk-qwen"


def test_create_chat_model_raises_when_key_unresolvable(monkeypatch):
    """create_chat_model 接线正确：key 无法解析时，构造模型前就抛 ValueError。"""
    monkeypatch.setattr(settings, "llm_key_deepseek", "")
    config = LLMConfig(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
    )
    with pytest.raises(ValueError):
        create_chat_model(config)


def test_llm_key_for_reads_provider_key_from_env_file(tmp_path):
    """Settings 原生从 .env 读取 ACG_AI_LLM_KEY_<PROVIDER>（根因修复：无需 load_dotenv 桥接）。

    为什么重要：这是密钥集中化能工作的根基——key 写进 .env 即被 Settings 读到，
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


# ---------- ping_llm 连通性校验 ----------

import httpx
import openai
from unittest.mock import MagicMock

from app.core.llm import ping_llm


@pytest.fixture
def deepseek_key(monkeypatch):
    """注入 deepseek key，让 ping_llm 能过 resolve_api_key 走到 invoke（不依赖运行环境的 .env）。

    为什么需要：ping_llm 先解析 key 再构造（被 mock 的）ChatOpenAI；显式 api_key 已移除，
    必须从 settings 取到一个非空 key 才能触达待测的 invoke 异常翻译逻辑。
    """
    monkeypatch.setattr(settings, "llm_key_deepseek", "sk-real")


def _ping_config(model="deepseek-chat"):
    return LLMConfig(
        provider="deepseek", model=model,
        base_url="https://api.deepseek.com/v1",
    )


def _http_resp(status_code):
    """构造 openai 状态异常所需的 httpx.Response。"""
    return httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://api.test/v1"))


def _mock_chat_model(monkeypatch, *, invoke_return=None, invoke_side_effect=None):
    """把 app.core.llm.ChatOpenAI 替换为一个返回假实例的工厂，便于控制 invoke 行为。"""
    fake = MagicMock()
    fake.invoke.return_value = invoke_return
    fake.invoke.side_effect = invoke_side_effect
    monkeypatch.setattr("app.core.llm.ChatOpenAI", lambda **kw: fake)
    return fake


def test_ping_llm_success(monkeypatch, deepseek_key):
    """invoke 正常返回 → ping_llm 不抛（连通性 OK）。"""
    from langchain_core.messages import AIMessage
    fake = _mock_chat_model(monkeypatch, invoke_return=AIMessage(content="ok"))
    ping_llm(_ping_config())  # 不抛即通过
    fake.invoke.assert_called_once()


def test_ping_llm_translates_auth_error(monkeypatch, deepseek_key):
    """鉴权失败 → ValueError 含「鉴权失败」。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=openai.AuthenticationError(
        message="bad key", response=_http_resp(401), body=None))
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config())
    assert "鉴权失败" in str(exc.value)


def test_ping_llm_translates_model_not_found(monkeypatch, deepseek_key):
    """模型名错 → ValueError 含模型名与「模型」字样。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=openai.NotFoundError(
        message="no model", response=_http_resp(404), body=None))
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config(model="deepseek-chet"))
    assert "模型" in str(exc.value) and "deepseek-chet" in str(exc.value)


def test_ping_llm_translates_connection_error(monkeypatch, deepseek_key):
    """连接错误/超时 → ValueError 含「base_url」。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=openai.APIConnectionError(
        message="conn", request=_http_resp(500).request))
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config())
    assert "base_url" in str(exc.value)


def test_ping_llm_ratelimit_is_available(monkeypatch, deepseek_key):
    """限流视为可用（已证明可联通）→ 不抛。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=openai.RateLimitError(
        message="limit", response=_http_resp(429), body=None))
    ping_llm(_ping_config())  # 不抛


def test_ping_llm_wraps_unknown_error(monkeypatch, deepseek_key):
    """未预期异常 → 包装成 ValueError（Fail Loud，不静默放行）。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=RuntimeError("boom"))
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config())
    assert "LLM 校验失败" in str(exc.value)


def test_ping_llm_propagates_missing_key(monkeypatch):
    """key 不可解析 → resolve_api_key 的 ValueError 原样传播（不被吞成通用错误）。"""
    monkeypatch.setattr(settings, "llm_key_deepseek", "")
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config())
    assert "ACG_AI_LLM_KEY_DEEPSEEK" in str(exc.value)
