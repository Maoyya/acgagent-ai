# Prompt Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a phase-1 "system prompt generation" capability to acgagent-ai: assemble a `system_prompt` from user hints via a meta-LLM, mode-aware single-judge moderation (403 on block), tiktoken cost estimate, and ChromaDB preference storage.

**Architecture:** New `prompt` slice (models → core → service → api) layered exactly like the existing agent/knowledge slices. Generation and moderation share a settings-level meta-LLM (two instances, temperatures 0.7 and 0.0). Python owns no MySQL; template persistence is Java's concern. Moderation block returns `Result(code=403, data=verdict)`.

**Tech Stack:** FastAPI, Pydantic v2, LangChain 0.3 (`ChatOpenAI` + `with_structured_output`), ChromaDB, tiktoken, pytest.

**Spec:** `docs/superpowers/specs/2026-06-21-prompt-generation-design.md` (all decisions in §1.1).

---

## File Structure Map

| File | Responsibility | Action |
|---|---|---|
| `app/models/prompt.py` | `PromptMode` enum + request/response Pydantic models + `ModerationVerdict` | Create |
| `app/core/cost_estimator.py` | `CostEstimator.estimate()` — tiktoken, no LLM | Create |
| `app/db/preference_store.py` | `PreferenceStore.record()` / `.list_by_user()` — ChromaDB | Create |
| `app/core/moderator.py` | `RULES` + `Moderator.moderate()` — structured-output single judge | Create |
| `app/core/prompt_builder.py` | `PromptBuilder.build()` — meta-prompt → system_prompt | Create |
| `app/services/prompt_service.py` | `PromptService` — orchestrates build→moderate→estimate→record; owns meta-LLM; returns `Result` | Create |
| `app/api/v1/prompt.py` | `/prompts/generate`, `/prompts/moderate`, `/prompts/estimate` | Create |
| `tests/test_prompt.py` | All tests + `FakeLLM` test double | Create |
| `app/config.py` | Add `meta_llm_*` settings fields | Modify |
| `app/api/v1/router.py` | Mount `prompt_router` | Modify |

**Decomposition rationale:** Each core component (builder, moderator, estimator, store) is stateless/injectable and unit-tested in isolation with a `FakeLLM`. The service wires them together and owns the only stateful thing (the meta-LLM instances). The API is a thin `Result` wrapper. This mirrors how `chat_service` orchestrates `core/` + `db/`.

**Testability design:** `PromptBuilder` and `Moderator` take the LLM as a **method argument** (not stored state), so tests pass a `FakeLLM`. `PromptService` builds its meta-LLMs via overridable `_build_gen_llm()`/`_build_mod_llm()` methods (tests monkeypatch these) and caches results in resettable `_gen_llm`/`_mod_llm` attributes.

---

## Task 1: Prompt Models

**Files:**
- Create: `app/models/prompt.py`
- Test: `tests/test_prompt.py`

- [ ] **Step 1: Create the test file with a failing test for model construction & enum**

Create `tests/test_prompt.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.prompt'`

- [ ] **Step 3: Write the models**

Create `app/models/prompt.py`:

```python
"""
系统提示词生成相关数据模型。

PromptMode：双模式开关（acg / compliant），决定 moderation 规则集。
所有请求/响应模型走 Pydantic v2，沿用项目统一 Result<T> 信封（见 app/models/common.py）。
"""
from enum import Enum
from pydantic import BaseModel, Field


class PromptMode(str, Enum):
    """提示词生成模式。

    - acg：拥抱二次元/动漫风格，只挡暴力违法/超能力。
    - compliant：中性专业，额外限制二次元风格。
    """
    acg = "acg"
    compliant = "compliant"


class ModerationVerdict(BaseModel):
    """单裁判的结构化裁决结果。confidence 为二期'是否升级多裁判投票'预留。"""
    passed: bool
    violated_rules: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    mode: PromptMode


class CostEstimate(BaseModel):
    """消耗估算。一期 est_completion_tokens 恒为 0（将来对话输出不可预知）。"""
    prompt_tokens: int
    est_completion_tokens: int = 0
    model: str


class PromptGenerateRequest(BaseModel):
    """生成请求：用户零散要求 + 模式 + 可选能力边界。"""
    user_hints: list[str] = Field(description="用户零散要求")
    mode: PromptMode = PromptMode.acg
    target_capabilities: list[str] = Field(
        default_factory=list,
        description="可选；Agent 能力标签，用于'不超能力'约束",
    )


class PromptGenerateResponse(BaseModel):
    """生成响应：提示词正文 + 裁决 + 估算。"""
    system_prompt: str
    mode: PromptMode
    moderation: ModerationVerdict
    estimate: CostEstimate


class ModerateRequest(BaseModel):
    """独立校验请求：Java 校验用户已保存的模板时调用。"""
    system_prompt: str
    mode: PromptMode
    target_capabilities: list[str] = Field(default_factory=list)


class EstimateRequest(BaseModel):
    """独立消耗估算请求。"""
    system_prompt: str
    user_hints: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_prompt.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/models/prompt.py tests/test_prompt.py
git commit -m "feat(prompt): add prompt generation data models and PromptMode"
```

---

## Task 2: Cost Estimator (pure, no LLM)

**Files:**
- Create: `app/core/cost_estimator.py`
- Test: `tests/test_prompt.py` (append)

- [ ] **Step 1: Append the failing test**

Append to `tests/test_prompt.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_prompt.py::test_estimate_scales_with_prompt_length -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.cost_estimator'`

- [ ] **Step 3: Write the estimator**

Create `app/core/cost_estimator.py`:

```python
"""
消耗估算。

一期口径：估算'生成的 system_prompt 将来每次对话会多吃多少 prompt token'，
即模板自身大小 + 用户 hints。复用 app/core/memory.count_tokens（tiktoken）。
纯计算，无 LLM 调用。est_completion_tokens 一期恒为 0（二期接 LLM 真实 usage）。
"""
from app.core.memory import count_tokens
from app.models.prompt import CostEstimate


class CostEstimator:
    def __init__(self, model: str):
        self.model = model

    def estimate(self, system_prompt: str, user_hints: list[str]) -> CostEstimate:
        """估算模板的 prompt 侧 token 开销。"""
        prompt_tokens = count_tokens(system_prompt)
        prompt_tokens += sum(count_tokens(h) for h in user_hints)
        return CostEstimate(
            prompt_tokens=prompt_tokens,
            est_completion_tokens=0,
            model=self.model,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_prompt.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/cost_estimator.py tests/test_prompt.py
git commit -m "feat(prompt): add tiktoken-based cost estimator"
```

---

## Task 3: Preference Store (ChromaDB)

**Files:**
- Create: `app/db/preference_store.py`
- Test: `tests/test_prompt.py` (append)

- [ ] **Step 1: Append the failing test (with chroma autouse fixture)**

Append to `tests/test_prompt.py`:

```python
import pytest


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_prompt.py::test_preference_record_and_list_by_user -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db.preference_store'`

- [ ] **Step 3: Write the store**

Create `app/db/preference_store.py`:

```python
"""
用户偏好存储。

复用 ChromaDB（与 memory_store 一致），collection 名 user_preferences，cosine 距离。
把'生成的 system_prompt 文本'作为 document 向量化，供二期相似度推荐。
metadata 只支持原始类型，故 hints 合并为字符串、user_id 缺失时落 'anonymous'。
"""
import logging
from datetime import datetime

from app.db.chroma_client import get_chroma
from app.models.prompt import PromptMode

logger = logging.getLogger("acgagent-ai")

_COLLECTION = "user_preferences"


class PreferenceStore:
    def _collection(self):
        return get_chroma().get_or_create_collection(
            name=_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def record(self, user_id: str | None, mode: PromptMode, hints: list[str], prompt: str) -> None:
        """记录一次成功生成。best-effort：异常由调用方决定是否吞掉。"""
        col = self._collection()
        uid = user_id or "anonymous"
        rec_id = f"pref_{col.count()}"
        col.add(
            ids=[rec_id],
            documents=[prompt],
            metadatas=[{
                "user_id": uid,
                "mode": mode.value,
                "hint_tags": ";".join(hints),
                "created_at": datetime.now().isoformat(),
            }],
        )

    def list_by_user(self, user_id: str) -> list[dict]:
        """读取某用户全部偏好记录（一期用于校验/排错；二期 recommend 复用）。"""
        col = self._collection()
        try:
            res = col.get(where={"user_id": user_id}, include=["documents", "metadatas"])
        except Exception:
            return []
        out = []
        for doc, meta in zip(res["documents"], res["metadatas"]):
            out.append({
                "prompt": doc,
                "user_id": meta.get("user_id"),
                "mode": meta.get("mode"),
                "hint_tags": meta.get("hint_tags", ""),
                "created_at": meta.get("created_at"),
            })
        return out


preference_store = PreferenceStore()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_prompt.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add app/db/preference_store.py tests/test_prompt.py
git commit -m "feat(prompt): add ChromaDB-backed preference store"
```

---

## Task 4: Moderator (single judge, structured output)

This task introduces the `FakeLLM` test double used by Tasks 4–7.

**Files:**
- Create: `app/core/moderator.py`
- Test: `tests/test_prompt.py` (append `FakeLLM` + tests)

- [ ] **Step 1: Append the FakeLLM double + failing tests**

Append to `tests/test_prompt.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_prompt.py::test_moderator_returns_structured_verdict -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.moderator'`

- [ ] **Step 3: Write the moderator**

Create `app/core/moderator.py`:

```python
"""
单裁判 moderation。

按 PromptMode 取用规则集（RULES），把候选 system_prompt 与规则交给 meta-LLM，
用 with_structured_output 强制返回 ModerationVerdict。temperature=0（在 prompt_service
构造 LLM 时设定），保证裁决稳定可复现。

二期升级路径：当 verdict.confidence 低于阈值时，改走 3 裁判投票（本任务不实现）。
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.prompt import ModerationVerdict, PromptMode

_MOD_SYSTEM = (
    "你是内容合规裁判。逐条判断给定的系统提示词是否违反下列规则，"
    "只返回结构化结果。不得自行放宽或增加规则。"
)

# 按 mode 参数化的规则集。底线规则（暴力/违法/色情）两模式共有。
RULES: dict[PromptMode, list[str]] = {
    PromptMode.acg: [
        "禁止暴力 / 违法犯罪 / 自残 / 色情内容",
        # 二次元风格：acg 模式允许（故此处不列禁令）
    ],
    PromptMode.compliant: [
        "禁止暴力 / 违法犯罪 / 自残 / 色情内容",
        "禁止二次元 / 动漫风格、夸张人设",
    ],
}


class Moderator:
    async def moderate(
        self,
        llm,
        system_prompt: str,
        mode: PromptMode,
        target_capabilities: list[str],
    ) -> ModerationVerdict:
        """对生成产物做单裁判合规校验，返回结构化裁决。"""
        rules = list(RULES[mode])
        if target_capabilities:
            caps = "、".join(target_capabilities)
            rules.append(f"该 Agent 仅具备以下能力：{caps}；提示词不得承诺这些能力之外的任何功能")

        payload = (
            f"待校验的系统提示词：\n{system_prompt}\n\n"
            f"适用规则（逐条判断）：\n" + "\n".join(f"{i + 1}. {r}" for i, r in enumerate(rules))
            + "\n\n若违反任一规则，passed=false 并在 violated_rules/reasons 说明；否则 passed=true。"
        )

        structured = llm.with_structured_output(ModerationVerdict)
        verdict = await structured.ainvoke([
            SystemMessage(content=_MOD_SYSTEM),
            HumanMessage(content=payload),
        ])
        # 兜底：LLM 偶发不回填 mode 时，按本次请求补齐
        if verdict.mode is None:
            verdict.mode = mode
        return verdict
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_prompt.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/moderator.py tests/test_prompt.py
git commit -m "feat(prompt): add mode-aware single-judge moderator"
```

---

## Task 5: Prompt Builder (meta-prompt → system_prompt)

**Files:**
- Create: `app/core/prompt_builder.py`
- Test: `tests/test_prompt.py` (append)

- [ ] **Step 1: Append the failing test**

Append to `tests/test_prompt.py`:

```python
@pytest.mark.asyncio
async def test_builder_returns_llm_content():
    """Builder 应把 LLM 返回的正文作为 system_prompt。"""
    from app.core.prompt_builder import PromptBuilder
    from app.models.prompt import PromptMode

    fake = FakeLLM(content="你是一名专业的客服助手。")
    result = await PromptBuilder().build(fake, ["专业客服"], PromptMode.compliant, [])
    assert result == "你是一名专业的客服助手."


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
```

> Note: `test_builder_returns_llm_content` asserts the builder returns the LLM content verbatim; `PromptBuilder.build` must `.strip()` trailing whitespace, so the test uses `"你是一名专业的客服助手."` (the fake returns `"你是一名专业的客服助手。"` and build strips — adjust the expected string to match: the fake returns content ending in `。`, strip() does not remove `。`, so expected must equal the fake's content exactly). Use the value shown in the fake.

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_prompt.py::test_builder_returns_llm_content -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.prompt_builder'`

- [ ] **Step 3: Write the builder**

Create `app/core/prompt_builder.py`:

```python
"""
提示词生成器。

构造一段'元提示词'交给 meta-LLM（非流式 ainvoke），让它根据用户零散要求
组装成一段可用的 system_prompt 正文。temperature≈0.7（在 prompt_service 构造 LLM 时设定）。
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.prompt import PromptMode

_META_SYSTEM = "你是一名资深提示词工程师，擅长把用户的零散要求组装成一段清晰、可用的 Agent 系统提示词。"

_STYLE = {
    PromptMode.acg: "风格：可使用二次元/动漫人设语气，但仍保持专业。",
    PromptMode.compliant: "风格：中性专业，避免二次元/动漫风格与夸张人设。",
}


class PromptBuilder:
    async def build(
        self,
        llm,
        user_hints: list[str],
        mode: PromptMode,
        target_capabilities: list[str],
    ) -> str:
        """根据用户要求生成 system_prompt 正文。"""
        hints_text = "\n".join(f"- {h}" for h in user_hints) or "-（用户未提供具体要求）"
        cap_text = ""
        if target_capabilities:
            cap_text = f"\n能力边界：该 Agent 仅具备 {('、'.join(target_capabilities))}；提示词不得承诺这些能力之外的功能。"

        payload = (
            f"{_STYLE[mode]}\n"
            f"用户要求：\n{hints_text}{cap_text}\n"
            f"输出：只输出系统提示词正文，不要解释、不要前缀、不要 Markdown 代码块。"
        )

        resp = await llm.ainvoke([
            SystemMessage(content=_META_SYSTEM),
            HumanMessage(content=payload),
        ])
        return (resp.content or "").strip()
```

> **Test fix-up:** In Step 1's `test_builder_returns_llm_content`, the fake returns `"你是一名专业的客服助手。"` and `build()` returns it stripped (unchanged). Set the assertion to the exact fake content. Correct the expected literal to `"你是一名专业的客服助手。"` (full-width period) so the test passes. (Do not change the production code to satisfy a half-width period.)

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_prompt.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/prompt_builder.py tests/test_prompt.py
git commit -m "feat(prompt): add meta-prompt-based prompt builder"
```

---

## Task 6: Prompt Service + meta-LLM config

Wires builder/moderator/estimator/preference together, owns the meta-LLM instances, returns `Result`. Also adds the `meta_llm_*` settings fields.

**Files:**
- Create: `app/services/prompt_service.py`
- Modify: `app/config.py`
- Test: `tests/test_prompt.py` (append)

- [ ] **Step 1: Append the failing tests + service cache-reset fixture**

Append to `tests/test_prompt.py`:

```python
@pytest.fixture(autouse=True)
def _reset_prompt_service_llm():
    """每个用例重置 prompt_service 的 LLM 缓存，使 _build_*_llm monkeypatch 生效。"""
    from app.services.prompt_service import prompt_service
    prompt_service._gen_llm = None
    prompt_service._mod_llm = None
    yield
    prompt_service._gen_llm = None
    prompt_service._mod_llm = None


def _wire_fakes(gen_content="生成的系统提示词", structured_passed=True, mode=None):
    """把 prompt_service 的 meta-LLM 构造方法替换为 FakeLLM。"""
    from app.services.prompt_service import prompt_service
    from app.models.prompt import ModerationVerdict, PromptMode

    resolved_mode = mode or PromptMode.acg
    prompt_service._build_gen_llm = lambda self: FakeLLM(content=gen_content)
    prompt_service._build_mod_llm = lambda self: FakeLLM(
        structured=ModerationVerdict(passed=structured_passed, mode=resolved_mode)
    )


@pytest.mark.asyncio
async def test_generate_happy_path():
    """通过校验时：返回 code=200，含提示词/裁决/估算，且偏好落库。"""
    from app.services.prompt_service import prompt_service
    from app.db.preference_store import preference_store
    from app.models.prompt import PromptGenerateRequest, PromptMode

    _wire_fakes(structured_passed=True)
    before = len(preference_store.list_by_user("u_happy"))
    result = await prompt_service.generate(
        PromptGenerateRequest(user_hints=["客服"], mode=PromptMode.acg), user_id="u_happy"
    )
    assert result.code == 200
    assert result.data.system_prompt == "生成的系统提示词"
    assert result.data.moderation.passed is True
    assert result.data.estimate.prompt_tokens > 0
    after = len(preference_store.list_by_user("u_happy"))
    assert after == before + 1, "成功生成应写入偏好"


@pytest.mark.asyncio
async def test_generate_blocked_returns_403_with_verdict():
    """校验不通过：code=403, message=blocked, data 为裁决结果（含原因）。"""
    from app.services.prompt_service import prompt_service
    from app.models.prompt import PromptGenerateRequest, PromptMode

    _wire_fakes(structured_passed=False, mode=PromptMode.compliant)
    result = await prompt_service.generate(
        PromptGenerateRequest(user_hints=["x"], mode=PromptMode.compliant), user_id="u_block"
    )
    assert result.code == 403
    assert result.message == "blocked"
    assert result.data.passed is False


@pytest.mark.asyncio
async def test_generate_skips_preference_when_blocked():
    """校验不通过时不写偏好——避免把不合规内容沉淀进推荐库。"""
    from app.services.prompt_service import prompt_service
    from app.db.preference_store import preference_store
    from app.models.prompt import PromptGenerateRequest, PromptMode

    _wire_fakes(structured_passed=False)
    before = len(preference_store.list_by_user("u_nopref"))
    await prompt_service.generate(
        PromptGenerateRequest(user_hints=["x"], mode=PromptMode.acg), user_id="u_nopref"
    )
    assert len(preference_store.list_by_user("u_nopref")) == before


@pytest.mark.asyncio
async def test_preference_failure_does_not_block_generate(monkeypatch):
    """偏好写入抛异常时，generate 仍正常返回——验证 best-effort。"""
    from app.services.prompt_service import prompt_service
    from app.db.preference_store import preference_store
    from app.models.prompt import PromptGenerateRequest, PromptMode

    _wire_fakes(structured_passed=True)

    def boom(*a, **k):
        raise RuntimeError("chroma down")

    monkeypatch.setattr(preference_store, "record", boom)
    result = await prompt_service.generate(
        PromptGenerateRequest(user_hints=["x"], mode=PromptMode.acg), user_id="u_ok"
    )
    assert result.code == 200
    assert result.data.system_prompt == "生成的系统提示词"


@pytest.mark.asyncio
async def test_generate_meta_llm_not_configured():
    """meta-LLM api_key 缺失时返回 code=500（而非抛异常拖垮服务）。"""
    from app.services.prompt_service import prompt_service, MetaLLMNotConfigured
    from app.models.prompt import PromptGenerateRequest, PromptMode

    prompt_service._gen_llm = None
    prompt_service._mod_llm = None

    def raise_unconfigured(self):
        raise MetaLLMNotConfigured("meta llm not configured")

    prompt_service._build_gen_llm = raise_unconfigured
    prompt_service._build_mod_llm = raise_unconfigured
    result = await prompt_service.generate(
        PromptGenerateRequest(user_hints=["x"], mode=PromptMode.acg), user_id="u_x"
    )
    assert result.code == 500
    assert "not configured" in result.message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_prompt.py::test_generate_happy_path -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.prompt_service'`

- [ ] **Step 3: Add meta-LLM settings fields**

Modify `app/config.py` — add four fields inside `class Settings` (after `log_level`, before `model_config`):

```python
    log_level: str = "INFO"

    # meta-LLM：用于提示词生成与合规校验（服务级基础设施任务，不绑定具体 Agent）
    meta_llm_provider: str = "deepseek"
    meta_llm_model: str = "deepseek-chat"
    meta_llm_base_url: str = "https://api.deepseek.com/v1"
    meta_llm_api_key: str = ""   # 缺失时 generate/moderate 返回 500

    model_config = {"env_prefix": "ACG_AI_", "env_file": ".env", "env_file_encoding": "utf-8"}
```

- [ ] **Step 4: Write the service**

Create `app/services/prompt_service.py`:

```python
"""
提示词生成编排服务。

generate(): 元提示词生成 → 单裁判校验 → 消耗估算 → 偏好写入。
- 校验不通过 → Result(code=403, message=blocked, data=裁决)
- meta-LLM 未配置 → Result(code=500)
- 偏好写入失败 → 仅 warning，不阻断主流程

meta-LLM 由 settings 配置，派生两个实例（生成 temp=0.7、校验 temp=0.0），
非流式（streaming=False），不复用 create_chat_model（其强制 streaming=True）。
"""
import logging

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.cost_estimator import CostEstimator
from app.core.moderator import Moderator
from app.core.prompt_builder import PromptBuilder
from app.db.preference_store import preference_store
from app.models.common import Result
from app.models.prompt import (
    ModerateRequest,
    PromptGenerateRequest,
    PromptGenerateResponse,
    PromptMode,
)

logger = logging.getLogger("acgagent-ai")


class MetaLLMNotConfigured(RuntimeError):
    """meta-LLM 缺少 api_key 时抛出。"""


class PromptService:
    def __init__(self):
        self._gen_llm = None
        self._mod_llm = None
        self.builder = PromptBuilder()
        self.moderator = Moderator()
        self.estimator = CostEstimator(settings.meta_llm_model)
        self.prefs = preference_store

    # -- meta-LLM 构造（可被测试 monkeypatch）--
    def _require_meta_config(self):
        if not settings.meta_llm_api_key:
            raise MetaLLMNotConfigured("meta llm not configured (set ACG_AI_META_LLM_API_KEY)")

    def _build_gen_llm(self):
        self._require_meta_config()
        return ChatOpenAI(
            model=settings.meta_llm_model,
            base_url=settings.meta_llm_base_url,
            api_key=settings.meta_llm_api_key,
            temperature=0.7,
            streaming=False,
        )

    def _build_mod_llm(self):
        self._require_meta_config()
        return ChatOpenAI(
            model=settings.meta_llm_model,
            base_url=settings.meta_llm_base_url,
            api_key=settings.meta_llm_api_key,
            temperature=0.0,
            streaming=False,
        )

    def _get_gen_llm(self):
        if self._gen_llm is None:
            self._gen_llm = self._build_gen_llm()
        return self._gen_llm

    def _get_mod_llm(self):
        if self._mod_llm is None:
            self._mod_llm = self._build_mod_llm()
        return self._mod_llm

    # -- 主入口 --
    async def generate(self, req: PromptGenerateRequest, user_id: str | None) -> Result:
        try:
            gen_llm = self._get_gen_llm()
            mod_llm = self._get_mod_llm()
        except MetaLLMNotConfigured as e:
            return Result.error(code=500, message=str(e))

        candidate = await self.builder.build(
            gen_llm, req.user_hints, req.mode, req.target_capabilities
        )
        verdict = await self.moderator.moderate(
            mod_llm, candidate, req.mode, req.target_capabilities
        )
        if not verdict.passed:
            return Result(code=403, message="blocked", data=verdict)

        estimate = self.estimator.estimate(candidate, req.user_hints)
        try:
            self.prefs.record(user_id, req.mode, req.user_hints, candidate)
        except Exception as e:
            logger.warning("preference record failed (best-effort, ignored): %s", e)

        return Result.success(PromptGenerateResponse(
            system_prompt=candidate,
            mode=req.mode,
            moderation=verdict,
            estimate=estimate,
        ))

    async def moderate(self, req: ModerateRequest) -> Result:
        """独立校验：始终返回裁决（code=200，由调用方读 passed 字段）。"""
        try:
            mod_llm = self._get_mod_llm()
        except MetaLLMNotConfigured as e:
            return Result.error(code=500, message=str(e))
        verdict = await self.moderator.moderate(
            mod_llm, req.system_prompt, req.mode, req.target_capabilities
        )
        return Result.success(data=verdict)

    def estimate(self, system_prompt: str, user_hints: list[str]) -> Result:
        """独立消耗估算：纯计算，无需 LLM。"""
        return Result.success(data=self.estimator.estimate(system_prompt, user_hints))


prompt_service = PromptService()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/test_prompt.py -v`
Expected: PASS (19 tests)

- [ ] **Step 6: Commit**

```bash
git add app/services/prompt_service.py app/config.py tests/test_prompt.py
git commit -m "feat(prompt): add prompt service with meta-LLM orchestration"
```

---

## Task 7: API endpoints + router mount

**Files:**
- Create: `app/api/v1/prompt.py`
- Modify: `app/api/v1/router.py`
- Test: `tests/test_prompt.py` (append)

- [ ] **Step 1: Append the failing API tests**

Append to `tests/test_prompt.py`:

```python
@pytest.mark.asyncio
async def test_generate_endpoint_happy(client, auth_headers):
    """POST /prompts/generate 成功返回信封结构与生成结果。"""
    _wire_fakes(structured_passed=True)
    resp = await client.post(
        "/api/v1/prompts/generate",
        json={"user_hints": ["客服"], "mode": "acg"},
        headers={**auth_headers, "X-User-Id": "u_api"},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["system_prompt"] == "生成的系统提示词"
    assert body["data"]["moderation"]["passed"] is True


@pytest.mark.asyncio
async def test_generate_endpoint_blocked_returns_403_envelope(client, auth_headers):
    """校验不通过：HTTP 200，body code=403，data 带原因——这是给 Java 的契约。"""
    _wire_fakes(structured_passed=False, mode="compliant")
    resp = await client.post(
        "/api/v1/prompts/generate",
        json={"user_hints": ["x"], "mode": "compliant"},
        headers=auth_headers,
    )
    body = resp.json()
    assert resp.status_code == 200  # 业务码在 body，非 HTTP 状态
    assert body["code"] == 403
    assert body["message"] == "blocked"
    assert body["data"]["passed"] is False


@pytest.mark.asyncio
async def test_estimate_endpoint(client, auth_headers):
    """POST /prompts/estimate 纯计算返回 token 估算（无需 LLM）。"""
    resp = await client.post(
        "/api/v1/prompts/estimate",
        json={"system_prompt": "你是一名助手", "user_hints": ["简洁"]},
        headers=auth_headers,
    )
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["prompt_tokens"] > 0
    assert body["data"]["est_completion_tokens"] == 0


@pytest.mark.asyncio
async def test_moderate_endpoint(client, auth_headers):
    """POST /prompts/moderate 始终返回裁决（code=200），由调用方读 passed。"""
    _wire_fakes(structured_passed=False, mode="acg")
    resp = await client.post(
        "/api/v1/prompts/moderate",
        json={"system_prompt": "含暴力内容", "mode": "acg"},
        headers=auth_headers,
    )
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["passed"] is False


@pytest.mark.asyncio
async def test_generate_invalid_mode_returns_422(client, auth_headers):
    """mode 非法时 FastAPI 校验层返回 HTTP 422。"""
    resp = await client.post(
        "/api/v1/prompts/generate",
        json={"user_hints": ["x"], "mode": "bogus"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_prompt.py::test_generate_endpoint_happy -v`
Expected: FAIL — 404 (route not yet mounted)

- [ ] **Step 3: Write the API router**

Create `app/api/v1/prompt.py`:

```python
"""
系统提示词生成 API。

三个端点（均挂 /api/v1 前缀、需 X-API-Key、user_id 由 Java 经 X-User-Id 透传）：
- POST /prompts/generate  组装→校验→估算→写偏好，一次返回
- POST /prompts/moderate  独立校验（Java 校验用户已保存模板）
- POST /prompts/estimate  独立消耗估算
读取 X-User-Id 的方式与 chat.py 一致（Header 直取，不走 Depends）。
"""
from fastapi import APIRouter, Header

from app.models.common import Result
from app.models.prompt import EstimateRequest, ModerateRequest, PromptGenerateRequest
from app.services.prompt_service import prompt_service

router = APIRouter(tags=["prompt"])


@router.post("/prompts/generate")
async def generate(
    body: PromptGenerateRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> Result:
    """生成系统提示词。校验不通过时返回 code=403。"""
    return await prompt_service.generate(body, user_id=x_user_id)


@router.post("/prompts/moderate")
async def moderate(body: ModerateRequest) -> Result:
    """独立合规校验，始终返回裁决（code=200，读 data.passed）。"""
    return await prompt_service.moderate(body)


@router.post("/prompts/estimate")
async def estimate(body: EstimateRequest) -> Result:
    """独立消耗估算，纯计算。"""
    return prompt_service.estimate(body.system_prompt, body.user_hints)
```

- [ ] **Step 4: Mount the router**

Modify `app/api/v1/router.py` — add the import and include. Final file:

```python
"""
API v1 路由汇总。

所有子路由挂载在 /api/v1 前缀下，统一经过 API Key 认证。
"""
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router
from app.api.v1.agent import router as agent_router
from app.api.v1.knowledge_base import router as kb_router
from app.api.v1.document import router as doc_router
from app.api.v1.tool import router as tool_router
from app.api.v1.prompt import router as prompt_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
router.include_router(agent_router)
router.include_router(kb_router)
router.include_router(doc_router)
router.include_router(tool_router)
router.include_router(prompt_router)
```

- [ ] **Step 5: Run the full prompt test suite**

Run: `poetry run pytest tests/test_prompt.py -v`
Expected: PASS (24 tests)

- [ ] **Step 6: Run the entire suite to confirm no regressions**

Run: `poetry run pytest tests/ -v`
Expected: ALL PASS (no regressions in existing health/agent/chat/knowledge/document/tool tests)

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/prompt.py app/api/v1/router.py tests/test_prompt.py
git commit -m "feat(prompt): add generate/moderate/estimate endpoints"
```

---

## Manual Smoke Test (optional, after Task 7)

Requires a real meta-LLM key. Set in `.env`:
```
ACG_AI_META_LLM_API_KEY=sk-...
```
Then:
```bash
poetry run uvicorn app.main:app --port 8100 &
curl -s -X POST http://localhost:8100/api/v1/prompts/generate \
  -H "X-API-Key: dev-api-key" -H "X-User-Id: u1" -H "Content-Type: application/json" \
  -d '{"user_hints":["毒舌但专业的客服","回答简洁"],"mode":"acg","target_capabilities":["chat"]}' | python -m json.tool
```
Expect `code=200`, a generated `system_prompt`, `moderation.passed=true`, and a non-zero `estimate.prompt_tokens`.

---

## Self-Review (run after writing — done)

**1. Spec coverage** (spec § in brackets):

| Spec requirement | Task |
|---|---|
| §2.1 生成 (b) | Task 5 (builder) + Task 6 (wired) |
| §2.1 单裁判 moderation (c), mode-aware | Task 4 (moderator + RULES) |
| §2.1 生成前消耗估算 (d) | Task 2 (cost_estimator) |
| §2.1 偏好写入 (f) | Task 3 (preference_store) + Task 6 (wired) |
| §3.3 meta-LLM via settings, two temps | Task 6 (config + _build_*_llm) |
| §5.4 编排 + 403 block + best-effort pref | Task 6 (generate) |
| §7 三端点 + X-User-Id | Task 7 |
| §8 错误处理 (403/422/500/retry-none) | Task 6 + Task 7 (moderation structured-output retry is a phase-2 concern; phase-1 fail path covered by 500) |
| §9 测试（7 项意图） | Tasks 1–7 (all 7 intents present as named tests) |

**2. Placeholder scan:** No TBD/TODO/"implement later"/"add validation". Every code step shows complete code. The two `> Note:`/`> Test fix-up:` callouts in Task 5 are explicit corrections with concrete values, not placeholders.

**3. Type consistency:**
- `Moderator.moderate(llm, system_prompt, mode, target_capabilities)` — same signature in Task 4 def, Task 6 calls. ✓
- `PromptBuilder.build(llm, user_hints, mode, target_capabilities)` — same in Task 5 def, Task 6 calls. ✓
- `CostEstimator(model)` + `.estimate(system_prompt, user_hints)` — same in Task 2 def, Task 6 init/call. ✓
- `PreferenceStore.record(user_id, mode, hints, prompt)` — same in Task 3 def, Task 6 call. ✓
- `PromptService.generate(req, user_id)` / `.moderate(req)` / `.estimate(system_prompt, user_hints)` — same in Task 6 def, Task 7 calls. ✓
- `Result(code=403, message="blocked", data=verdict)` used consistently (Task 6 + Task 7 test). ✓
- `_build_gen_llm` / `_build_mod_llm` / `_gen_llm` / `_mod_llm` attribute names match across service + test fixture + `_wire_fakes`. ✓

**Coverage note:** structured-output parse-failure retry (spec §8) is deferred — phase-1 relies on `with_structured_output` raising → the endpoint surfaces it as a 500 (fail loud). A retry wrapper is a phase-2 hardening addition, out of this plan's MVP scope. This matches the spec's phase split.
