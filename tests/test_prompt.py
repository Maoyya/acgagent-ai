"""系统提示词生成功能测试。"""
import pytest


def test_prompt_mode_enum_values():
    """PromptMode 应只有 acg / compliant 两个值，且为 str 枚举（便于 JSON 序列化）。"""
    from app.models.prompt import PromptMode
    assert PromptMode("acg") is PromptMode.acg
    assert PromptMode("compliant") is PromptMode.compliant
    assert {m.value for m in PromptMode} == {"acg", "compliant"}


def test_moderation_verdict_defaults():
    """通过的裁决默认无违规/原因，confidence 默认 1.0，mode 必填。"""
    from app.models.prompt import ModerationVerdict, PromptMode
    v = ModerationVerdict(passed=True, mode=PromptMode.acg)
    assert v.violated_rules == []
    assert v.reasons == []
    assert v.confidence == 1.0
    assert v.mode is PromptMode.acg


def test_cost_estimate_defaults():
    """估算一期 est_completion_tokens 恒为 0；prompt_tokens 与 model 必填。"""
    from app.models.prompt import CostEstimate
    e = CostEstimate(prompt_tokens=42, model="deepseek-chat")
    assert e.est_completion_tokens == 0
    assert e.prompt_tokens == 42


def test_estimate_scales_with_prompt_length():
    """提示词越长，估算的 prompt_tokens 越大——验证估算是真实的，不是常数。"""
    from app.core.cost_estimator import CostEstimator
    est = CostEstimator(model="deepseek-chat")
    short = est.estimate("你好", [])
    long = est.estimate("你好" * 500, [])
    assert short.prompt_tokens > 0
    assert long.prompt_tokens > short.prompt_tokens


def test_estimate_includes_user_hints_and_zero_completion():
    """估算应把用户 hints 计入；一期 est_completion_tokens 恒为 0；model 回显。"""
    from app.core.cost_estimator import CostEstimator
    est = CostEstimator(model="deepseek-chat")
    without_hints = est.estimate("系统提示词正文", [])
    with_hints = est.estimate("系统提示词正文", ["要求一", "要求二"])
    assert with_hints.prompt_tokens > without_hints.prompt_tokens
    assert with_hints.est_completion_tokens == 0
    assert with_hints.model == "deepseek-chat"


@pytest.fixture(autouse=True)
def _init_chroma():
    """每个用例独立的 ChromaDB（与 tests/test_knowledge.py 一致：lifespan 在 ASGITransport 下不运行）。"""
    from app.db.chroma_client import init_chroma, close_chroma
    init_chroma()
    yield
    close_chroma()


def test_preference_record_and_list_by_user():
    """成功记录后，按 user_id 能查回——验证偏好写入真的落库。"""
    from app.db.preference_store import preference_store
    from app.models.prompt import PromptMode

    before = preference_store.list_by_user("u_record")
    preference_store.record(
        user_id="u_record",
        mode=PromptMode.acg,
        hints=["毒舌客服"],
        prompt="你是一名毒舌客服...",
    )
    after = preference_store.list_by_user("u_record")
    assert len(after) == len(before) + 1
    rec = after[-1]
    assert rec["prompt"] == "你是一名毒舌客服..."
    assert rec["user_id"] == "u_record"
    assert rec["mode"] == "acg"


def test_preference_isolated_by_user():
    """不同 user_id 的偏好互不串扰——验证按 user_id 索引正确。"""
    from app.db.preference_store import preference_store
    from app.models.prompt import PromptMode

    preference_store.record("u_a", PromptMode.acg, ["a"], "A 的偏好")
    preference_store.record("u_b", PromptMode.compliant, ["b"], "B 的偏好")
    a = preference_store.list_by_user("u_a")
    b = preference_store.list_by_user("u_b")
    assert all(r["user_id"] == "u_a" for r in a)
    assert all(r["user_id"] == "u_b" for r in b)
    assert any(r["prompt"] == "A 的偏好" for r in a)
    assert not any(r["prompt"] == "B 的偏好" for r in a)


def test_preference_anonymous_user_id():
    """user_id 为 None 时落库为 'anonymous'（Chroma metadata 不支持 None 值）。"""
    from app.db.preference_store import preference_store
    from app.models.prompt import PromptMode

    preference_store.record(None, PromptMode.acg, ["x"], "匿名偏好")
    recs = preference_store.list_by_user("anonymous")
    assert any(r["prompt"] == "匿名偏好" for r in recs)
