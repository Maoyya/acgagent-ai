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


class _FakeAIMessage:
    """模拟 LangChain AIMessage，仅暴露 .content。"""
    def __init__(self, content):
        self.content = content


class FakeLLM:
    """测试用 ChatOpenAI 替身。

    - ainvoke：返回 content（供 PromptBuilder）
    - with_structured_output：返回带 ainvoke 的 runner，返回预设的结构化对象（供 Moderator）
    - last_messages：记录最近一次入参，供断言'注入的规则是否符合 mode'
    """
    def __init__(self, *, content="", structured=None):
        self._content = content
        self._structured = structured
        self.last_messages = None

    async def ainvoke(self, messages, **kwargs):
        self.last_messages = messages
        return _FakeAIMessage(self._content)

    def with_structured_output(self, schema, **kwargs):
        llm = self

        class _Runner:
            async def ainvoke(self, messages, **kwargs):
                llm.last_messages = messages
                assert llm._structured is not None, (
                    "FakeLLM 经 with_structured_output 调用但未设置 structured="
                )
                return llm._structured

        return _Runner()


def _joined(messages):
    return "\n".join(getattr(m, "content", "") for m in messages)


@pytest.mark.asyncio
async def test_moderator_returns_structured_verdict():
    """Moderator 应调用 with_structured_output 并原样返回 LLM 给的裁决。"""
    from app.core.moderator import Moderator
    from app.models.prompt import ModerationVerdict, PromptMode

    verdict = ModerationVerdict(passed=True, mode=PromptMode.acg)
    fake = FakeLLM(structured=verdict)
    result = await Moderator().moderate(fake, "你是一名助手", PromptMode.acg, [])
    assert result is verdict


@pytest.mark.asyncio
async def test_moderator_anime_blocked_only_in_compliant():
    """二次元禁令只在 compliant 模式注入——验证 mode 参数化真的改变规则集。"""
    from app.core.moderator import Moderator
    from app.models.prompt import ModerationVerdict, PromptMode

    acg_fake = FakeLLM(structured=ModerationVerdict(passed=True, mode=PromptMode.acg))
    comp_fake = FakeLLM(structured=ModerationVerdict(passed=True, mode=PromptMode.compliant))
    await Moderator().moderate(acg_fake, "动漫风格助手", PromptMode.acg, [])
    await Moderator().moderate(comp_fake, "动漫风格助手", PromptMode.compliant, [])

    assert "二次元" not in _joined(acg_fake.last_messages), "acg 模式不应禁止二次元"
    assert "二次元" in _joined(comp_fake.last_messages), "compliant 模式应禁止二次元"


@pytest.mark.asyncio
async def test_moderator_violence_rule_in_both_modes():
    """暴力违法是底线规则，两个 mode 都要注入——验证底线与 mode 无关。"""
    from app.core.moderator import Moderator
    from app.models.prompt import ModerationVerdict, PromptMode

    for mode in (PromptMode.acg, PromptMode.compliant):
        fake = FakeLLM(structured=ModerationVerdict(passed=True, mode=mode))
        await Moderator().moderate(fake, "含暴力内容", mode, [])
        assert "暴力" in _joined(fake.last_messages), f"{mode} 模式应含暴力禁令"


@pytest.mark.asyncio
async def test_moderator_capability_rule_injected_when_caps_given():
    """提供 target_capabilities 时，应注入'不超能力'规则并列出能力边界。"""
    from app.core.moderator import Moderator
    from app.models.prompt import ModerationVerdict, PromptMode

    fake = FakeLLM(structured=ModerationVerdict(passed=True, mode=PromptMode.acg))
    await Moderator().moderate(fake, "你什么都能做", PromptMode.acg, ["chat", "rag"])
    joined = _joined(fake.last_messages)
    assert "chat" in joined and "rag" in joined, "应列出能力边界"
    assert "能力" in joined, "应注入不超能力约束"


@pytest.mark.asyncio
async def test_builder_returns_llm_content():
    """Builder 应把 LLM 返回的正文作为 system_prompt。"""
    from app.core.prompt_builder import PromptBuilder
    from app.models.prompt import PromptMode

    fake = FakeLLM(content="你是一名专业的客服助手。")
    result = await PromptBuilder().build(fake, ["专业客服"], PromptMode.compliant, [])
    assert result == "你是一名专业的客服助手。"


@pytest.mark.asyncio
async def test_builder_passes_hints_and_mode_to_llm():
    """Builder 应把用户 hints 与 mode 风格约束注入元提示词。"""
    from app.core.prompt_builder import PromptBuilder
    from app.models.prompt import PromptMode

    fake = FakeLLM(content="x")
    await PromptBuilder().build(fake, ["毒舌客服", "回答简洁"], PromptMode.acg, ["chat"])
    joined = _joined(fake.last_messages)
    assert "毒舌客服" in joined and "回答简洁" in joined, "应包含用户 hints"
    assert "二次元" in joined, "acg 模式应给出二次元风格指引"
