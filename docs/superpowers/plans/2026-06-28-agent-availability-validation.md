# Agent 可用性验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在创建/更新 Agent 时前置可用性校验（LLM 连通性 ping + 引用完整性），失败即拒绝落库，把「配错的 Agent」错误左移到配置环节。

**Architecture:** `app/core/llm.py` 新增 `ping_llm()` 发一次最小 completion 验证连通性；`agent_service` 新增 `_validate_references()` + `_validate()` 编排，接入 `create`/`update`（更新做完整复检）；路由加 `validate` query 参数并捕获 `ValueError` → `Result.error(400)`；提取 `BUILTIN_TOOL_IDS` 到 `app/tools/__init__.py` 供校验与 `chat_service._get_tools` 共用，消除两处硬编码。

**Tech Stack:** FastAPI · langchain-openai 0.3.35 · openai 2.38.0 · pydantic v2 · pytest（async，httpx ASGI client）

## Global Constraints

（复制自 spec `docs/superpowers/specs/2026-06-28-agent-availability-validation-design.md`，每个 task 隐式遵守）

- **失败即拒绝**：校验不通过 → 不创建/不更新，路由返回 `Result.error(code=400, message=中文可读原因)`；`Result.code` 是业务码（HTTP 仍 200），与 `chat.py` 现有用法一致。
- **`validate=false` 仅豁免 LLM ping**（query 参数 `?validate=false`）；**引用完整性校验始终执行**（本地、零成本）。
- **更新 = 完整复检**：先合并出更新后的完整配置，再对其做 `_validate_references` + `ping_llm`；即使只改 `name` 也复检。校验失败则不 `save`，旧 Agent 原子不变。
- **异常风格**：`ping_llm` / `_validate_references` 失败抛 `ValueError(中文原因)`（沿用 `resolve_api_key` 惯例）；路由捕获 `ValueError` 转 `Result.error(400)`。
- **ping 参数**：`max_tokens=1`、`temperature=0`、`streaming=False`、`timeout=15.0`；`openai.RateLimitError` 视为可用（已证明可联通）。
- **内置工具 ID**：`calculator` / `web_search` / `knowledge_search` 视为合法 tool_id，**不查 `tool_store`**（内置工具不入库）；自定义 tool_id 查 `tool_store.get()` 判存在。
- **测试不真实打 provider**：用 `monkeypatch` mock `ChatOpenAI` 或 `ping_llm`。
- **提交规范**：commit message 用中文；变更记录写 `docs/changelogs/`（复数，非 CHANGELOG.md）；代码改完后跑 `/code-review`。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `app/tools/__init__.py` | 内置工具 ID 清单与 `id→类` 映射（单一真相源） | 改（当前基本为空） |
| `app/services/chat_service.py` | 对话工具实例化（改用映射，去重） | 改 `_get_tools` (`:145-163`) |
| `app/core/llm.py` | LLM 工厂 + 连通性 ping | 改（加 `ping_llm`） |
| `app/services/agent_service.py` | Agent CRUD + 可用性校验编排 | 改（加 `_validate`/`_validate_references`，接入 `create`/`update`） |
| `app/api/v1/agent.py` | Agent REST 端点 | 改（加 `validate` query + 异常信封） |
| `tests/test_llm.py` | `resolve_api_key` + `ping_llm` 单测 | 改（加 ping 测试组） |
| `tests/test_agent_validation.py` | `_validate_references` 单测 | 新建 |
| `tests/test_agent_validation_api.py` | create/update 校验端到端测试 | 新建 |
| `tests/test_chat_service_tools.py` | `_get_tools` 行为回归 + 常量值 | 新建 |
| `tests/test_agent_api.py` | 现有 CRUD 回归 | 改（lifecycle 用 `validate=false`） |
| `tests/test_chat.py` | 现有对话回归 | 改（2 处建 Agent 用 `validate=false`） |
| `docx/business-flow.md` | 业务流程文档 | 改（3.1 加校验步骤） |
| `docs/changelogs/2026-06-28-agent-availability-validation.md` | 变更记录 | 新建 |

---

## Task 1: 提取 `BUILTIN_TOOL_IDS` 常量 + `chat_service._get_tools` 去重

把内置工具的 `id→类` 映射集中到 `app/tools/__init__.py`，`chat_service._get_tools` 改为查映射，消除「校验逻辑」与「对话实例化逻辑」各硬编码一份内置工具清单的冲突（spec §3.1，Rule 7）。此 task 不触碰 Agent 创建/校验，行为不变。

**Files:**
- Modify: `app/tools/__init__.py`（当前基本为空 → 写入映射与常量）
- Modify: `app/services/chat_service.py:145-163`（`_get_tools` 改为查映射）
- Test: `tests/test_chat_service_tools.py`（新建）

**Interfaces:**
- Produces: `app.tools.BUILTIN_TOOLS: dict[str, type]`、`app.tools.BUILTIN_TOOL_IDS: set[str]`（后续 task 的 `_validate_references` 消费 `BUILTIN_TOOL_IDS`）

- [ ] **Step 1: 写失败测试** `tests/test_chat_service_tools.py`

```python
"""chat_service 工具实例化与内置工具常量测试。

锁定意图（Rule 9）：
- BUILTIN_TOOL_IDS 是「合法内置 tool_id」的单一真相源（校验逻辑将共用它）。
- _get_tools 改用映射后，内置工具实例化行为与旧版 switch 完全一致。
"""
from app.tools import BUILTIN_TOOL_IDS, BUILTIN_TOOLS
from app.models.agent import AgentConfig, LLMConfig
from app.services.chat_service import chat_service


def _agent(tool_ids):
    return AgentConfig(
        name="t",
        llm_config=LLMConfig(provider="x", model="m", base_url="http://x", api_key="k"),
        tool_ids=tool_ids,
    )


def test_builtin_tool_ids_is_the_three_builtins():
    """BUILTIN_TOOL_IDS 锁定三个内置工具 ID。"""
    assert BUILTIN_TOOL_IDS == {"calculator", "web_search", "knowledge_search"}
    assert set(BUILTIN_TOOLS.keys()) == BUILTIN_TOOL_IDS


def test_get_tools_instantiates_each_builtin_once():
    """calculator / web_search 各实例化一次；未关联 KB 时 knowledge_search 被跳过。"""
    tools = chat_service._get_tools(_agent(["calculator", "web_search", "knowledge_search"]))
    assert len(tools) == 2  # knowledge_search 无 KB → 跳过（沿用旧行为）


def test_get_tools_knowledge_search_requires_kb():
    """knowledge_search 有关联 KB 时才实例化。"""
    agent = _agent(["knowledge_search"])
    agent.knowledge_base_ids = ["kb-1"]
    assert len(chat_service._get_tools(agent)) == 1
    assert len(chat_service._get_tools(_agent(["knowledge_search"]))) == 0


def test_get_tools_ignores_unknown_and_custom_ids():
    """非内置 ID（含自定义工具 ID）在 _get_tools 中被忽略 —— 沿用既有行为，本计划不改变它。"""
    assert len(chat_service._get_tools(_agent(["calculator", "unknown_custom"]))) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_chat_service_tools.py -v`
Expected: FAIL — `ImportError: cannot import name 'BUILTIN_TOOL_IDS' ...`（常量尚未定义）

- [ ] **Step 3: 写入常量与映射** `app/tools/__init__.py`

完整覆盖该文件（当前基本为空）：

```python
"""内置工具注册中心。

集中定义「内置工具 id → 实现类」的映射，作为单一真相源：
- chat_service._get_tools 据此实例化内置工具；
- agent 可用性校验据此判断「合法 tool_id」（自定义工具另查 tool_store）。

注意：自定义（用户 API）工具不在此映射，存于 app/db/tool_store.py。
"""
from app.tools.calculator import CalculatorTool
from app.tools.knowledge_search import KnowledgeSearchTool
from app.tools.web_search import WebSearchTool

# 内置工具 id → 实现类
BUILTIN_TOOLS = {
    "calculator": CalculatorTool,
    "web_search": WebSearchTool,
    "knowledge_search": KnowledgeSearchTool,
}

# 内置工具 id 集合（供引用完整性校验消费）
BUILTIN_TOOL_IDS = set(BUILTIN_TOOLS.keys())
```

- [ ] **Step 4: 改 `_get_tools` 改用映射** `app/services/chat_service.py`

把 `:145-163` 的 `_get_tools` 整体替换为：

```python
    def _get_tools(self, agent_config: AgentConfig) -> list:
        """根据 Agent 的 tool_ids 实例化对应工具并转换为 LangChain Tool 格式。

        内置工具按 BUILTIN_TOOLS 映射实例化（id→类单一真相源，去重 Rule 7）；
        自定义工具 ID 不在此处理 —— chat_service 当前不消费 tool_store，
        仅由 agent 可用性校验保证其存在性。
        knowledge_search 需关联知识库，未关联时跳过。
        """
        from app.tools import BUILTIN_TOOLS

        tools = []
        for tid in agent_config.tool_ids:
            cls = BUILTIN_TOOLS.get(tid)
            if cls is None:
                continue
            if tid == "knowledge_search":
                if agent_config.knowledge_base_ids:
                    tools.append(cls(agent_config.knowledge_base_ids))
            else:
                tools.append(cls())
        return [t.to_langchain_tool() for t in tools]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_chat_service_tools.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: 跑全量回归确认无破坏**

Run: `pytest -q`
Expected: PASS（与改动前一致的通过数；本 task 不改变对话/创建行为）

- [ ] **Step 7: 提交**

```bash
git add app/tools/__init__.py app/services/chat_service.py tests/test_chat_service_tools.py
git commit -m "refactor(tools): 提取 BUILTIN_TOOL_IDS 常量，chat_service._get_tools 改用映射去重"
```

---

## Task 2: `ping_llm` 连通性校验函数

在 `app/core/llm.py` 新增 `ping_llm(config, timeout)`：发一次 `max_tokens=1` 的最小 completion，成功返回，失败按异常类型翻译成中文原因的 `ValueError`。

**Files:**
- Modify: `app/core/llm.py`（加 `ping_llm`）
- Test: `tests/test_llm.py`（加 ping 测试组）

**Interfaces:**
- Consumes: `resolve_api_key(provider, explicit)`（已存在于本文件，缺失抛 `ValueError`）
- Produces: `ping_llm(config: LLMConfig, timeout: float = 15.0) -> None`（成功 return；失败 `raise ValueError`）—— Task 4 的 `agent_service` 将 `from app.core.llm import ping_llm` 消费

- [ ] **Step 1: 写失败测试** —— 追加到 `tests/test_llm.py` 末尾

```python
# ---------- ping_llm 连通性校验 ----------

import httpx
import openai
from unittest.mock import MagicMock

from app.core.llm import ping_llm


def _ping_config(model="deepseek-chat", api_key="sk-real"):
    return LLMConfig(
        provider="deepseek", model=model,
        base_url="https://api.deepseek.com/v1", api_key=api_key,
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


def test_ping_llm_success(monkeypatch):
    """invoke 正常返回 → ping_llm 不抛（连通性 OK）。"""
    from langchain_core.messages import AIMessage
    fake = _mock_chat_model(monkeypatch, invoke_return=AIMessage(content="ok"))
    ping_llm(_ping_config())  # 不抛即通过
    fake.invoke.assert_called_once()


def test_ping_llm_translates_auth_error(monkeypatch):
    """鉴权失败 → ValueError 含「鉴权失败」。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=openai.AuthenticationError(
        message="bad key", response=_http_resp(401), body=None))
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config())
    assert "鉴权失败" in str(exc.value)


def test_ping_llm_translates_model_not_found(monkeypatch):
    """模型名错 → ValueError 含模型名与「模型」字样。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=openai.NotFoundError(
        message="no model", response=_http_resp(404), body=None))
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config(model="deepseek-chet"))
    assert "模型" in str(exc.value) and "deepseek-chet" in str(exc.value)


def test_ping_llm_translates_connection_error(monkeypatch):
    """连接错误/超时 → ValueError 含「base_url」。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=openai.APIConnectionError(message="conn"))
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config())
    assert "base_url" in str(exc.value)


def test_ping_llm_ratelimit_is_available(monkeypatch):
    """限流视为可用（已证明可联通）→ 不抛。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=openai.RateLimitError(
        message="limit", response=_http_resp(429), body=None))
    ping_llm(_ping_config())  # 不抛


def test_ping_llm_wraps_unknown_error(monkeypatch):
    """未预期异常 → 包装成 ValueError（Fail Loud，不静默放行）。"""
    _mock_chat_model(monkeypatch, invoke_side_effect=RuntimeError("boom"))
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config())
    assert "LLM 校验失败" in str(exc.value)


def test_ping_llm_propagates_missing_key(monkeypatch):
    """key 不可解析 → resolve_api_key 的 ValueError 原样传播（不被吞成通用错误）。"""
    monkeypatch.setattr(settings, "llm_key_deepseek", "")
    with pytest.raises(ValueError) as exc:
        ping_llm(_ping_config(api_key=""))
    assert "ACG_AI_LLM_KEY_DEEPSEEK" in str(exc.value)
```

> 注：`pytest`、`settings`、`LLMConfig` 已在该文件顶部 import（见现有 `test_llm.py`），无需重复。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_llm.py -k ping -v`
Expected: FAIL — `ImportError: cannot import name 'ping_llm' from app.core.llm`

- [ ] **Step 3: 实现 `ping_llm`** —— 在 `app/core/llm.py` 末尾追加

文件顶部已有 `from langchain_openai import ChatOpenAI`、`from app.config import settings`、`from app.models.agent import LLMConfig`。追加 import 与函数：

```python
import openai
from langchain_core.messages import HumanMessage


def ping_llm(config: LLMConfig, timeout: float = 15.0) -> None:
    """发起一次最小 completion 验证 LLM 连通性。成功 return；失败 raise ValueError(中文原因)。

    独立构造一个非流式、max_tokens=1 的 ChatOpenAI（不复用 create_chat_model，
    后者为对话用、streaming=True 且无超时）。key 解析复用 resolve_api_key。
    RateLimitError 视为可用（已成功触达 provider 并通过到限流判定）。
    """
    api_key = resolve_api_key(config.provider, config.api_key)  # 缺失抛 ValueError（原样传播）
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
            f"请检查 llm_config.api_key 或 ACG_AI_LLM_KEY_{config.provider.upper()}"
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_llm.py -k ping -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 跑全量回归**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/core/llm.py tests/test_llm.py
git commit -m "feat(llm): 新增 ping_llm 连通性校验（最小 completion + 异常翻译）"
```

---

## Task 3: `_validate_references` 引用完整性校验方法

在 `agent_service` 新增 `_validate_references(kb_ids, tool_ids)`（**仅新增方法，暂不接入 create/update**），保证本 task 不影响现有 HTTP 测试。

**Files:**
- Modify: `app/services/agent_service.py`（加 import + `_validate_references`）
- Test: `tests/test_agent_validation.py`（新建）

**Interfaces:**
- Consumes: `app.tools.BUILTIN_TOOL_IDS`（Task 1）、`knowledge_store.get()`、`tool_store.get()`
- Produces: `AgentService._validate_references(self, kb_ids: list[str], tool_ids: list[str]) -> None`（通过 return；缺失 `raise ValueError`）—— Task 4 的 `_validate` 将调用它

- [ ] **Step 1: 写失败测试** `tests/test_agent_validation.py`

```python
"""Agent 引用完整性校验单测（_validate_references）。

锁定意图（Rule 9）：
- 不存在的 kb_id / 自定义 tool_id 必须被拦下（避免配出引用悬空的 Agent）。
- 内置 tool_id（calculator 等）合法，不查 tool_store（内置工具不入库）。
"""
import pytest

from app.services.agent_service import agent_service


def test_accepts_empty_references():
    """空 kb/tool → 通过（默认 Agent 无引用）。"""
    agent_service._validate_references([], [])  # 不抛


def test_rejects_missing_knowledge_base():
    """不存在的 kb_id → ValueError 列出缺失。"""
    with pytest.raises(ValueError) as exc:
        agent_service._validate_references(["no-such-kb"], [])
    assert "no-such-kb" in str(exc.value)


def test_accepts_builtin_tool_ids_without_store():
    """内置 tool_id 合法，不查 tool_store。"""
    agent_service._validate_references([], ["calculator", "web_search", "knowledge_search"])


def test_rejects_missing_custom_tool():
    """不存在的自定义 tool_id → ValueError 列出缺失。"""
    with pytest.raises(ValueError) as exc:
        agent_service._validate_references([], ["no-such-tool"])
    assert "no-such-tool" in str(exc.value)


def test_message_lists_all_missing():
    """同时缺失 kb 与 tool → 一条消息列全两类缺失。"""
    with pytest.raises(ValueError) as exc:
        agent_service._validate_references(["bad-kb"], ["bad-tool"])
    msg = str(exc.value)
    assert "bad-kb" in msg and "bad-tool" in msg
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_agent_validation.py -v`
Expected: FAIL — `AttributeError: 'AgentService' object has no attribute '_validate_references'`

- [ ] **Step 3: 实现 `_validate_references`** —— 改 `app/services/agent_service.py`

在文件顶部 import 区追加（`from app.db.agent_store import agent_store` 下方）：

```python
from app.db.knowledge_store import knowledge_store
from app.db.tool_store import tool_store
from app.tools import BUILTIN_TOOL_IDS
```

在 `AgentService` 类内、`def create` 之前插入：

```python
    def _validate_references(self, kb_ids: list[str], tool_ids: list[str]) -> None:
        """校验 KB / tool 引用存在。通过 return；缺失 raise ValueError（列出缺失 ID）。

        - KB：每个 id 必须 knowledge_store.get(id) 存在。
        - Tool：合法 ⟺ 在 BUILTIN_TOOL_IDS 中 或 tool_store.get(id) 存在（内置工具不入库）。
        """
        missing_kb = [kb for kb in kb_ids if knowledge_store.get(kb) is None]
        missing_tool = [
            tid for tid in tool_ids
            if tid not in BUILTIN_TOOL_IDS and tool_store.get(tid) is None
        ]
        if missing_kb or missing_tool:
            raise ValueError(
                f"引用资源不存在: knowledge_base_ids={missing_kb}, tool_ids={missing_tool}"
            )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_agent_validation.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 跑全量回归**

Run: `pytest -q`
Expected: PASS（方法尚未接入 create/update，现有行为不变）

- [ ] **Step 6: 提交**

```bash
git add app/services/agent_service.py tests/test_agent_validation.py
git commit -m "feat(agent): 新增 _validate_references 引用完整性校验（KB/tool 存在性）"
```

---

## Task 4: 接入 create/update 校验 + 路由 `validate` 参数 + 修回归 + 端到端测试

把校验接入 `create`/`update`（更新做完整复检），路由加 `validate` query 参数并捕获 `ValueError → Result.error(400)`，修复 3 处受影响的现有测试，补端到端测试。**这是接入的原子单元**：`service.create` 一旦 ping，现有建 Agent 的测试就会因假 key 失败，必须连同路由逃生口与回归修复一起完成，commit 时全绿。

**Files:**
- Modify: `app/services/agent_service.py`（`_validate` 编排 + `create`/`update` 加 `validate` 形参并调用）
- Modify: `app/api/v1/agent.py`（`create_agent`/`update_agent` 加 `validate` query + 捕获 `ValueError`）
- Modify: `tests/test_agent_api.py`（`test_agent_crud_lifecycle` 用 `?validate=false`）
- Modify: `tests/test_chat.py`（`test_chat_disabled_agent`、`test_chat_missing_llm_key_returns_500_envelope` 建 Agent 用 `?validate=false`）
- Test: `tests/test_agent_validation_api.py`（新建，端到端）

**Interfaces:**
- Consumes: `ping_llm`（Task 2）、`_validate_references`（Task 3）
- Produces: `AgentService.create(req, validate=True)`、`AgentService.update(agent_id, req, validate=True)`；路由 `POST/PUT /api/v1/agents[?validate=false]`

- [ ] **Step 1: 写端到端失败测试** `tests/test_agent_validation_api.py`

```python
"""Agent 创建/更新可用性校验端到端测试（经 HTTP，mock ping_llm）。

锁定意图（Rule 9）：
- ping 失败 → 400 且 Agent 未落库（不可用不入库）。
- validate=false 豁免 ping（逃生口），但引用校验不豁免。
- 更新=完整复检：即使只改 name 也触发 ping；失败则旧值不变（原子）。
"""
import pytest

VALID_LLM = {
    "provider": "deepseek", "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "sk-test", "temperature": 0.7,
}


def _ping_raises(monkeypatch, msg="Agent LLM 不可用: API Key 鉴权失败"):
    """让 agent_service 内的 ping_llm 抛 ValueError。"""
    def _fail(*a, **kw):
        raise ValueError(msg)
    monkeypatch.setattr("app.services.agent_service.ping_llm", _fail)


def _ping_succeeds_counting(monkeypatch):
    """让 ping_llm 成功并计数（验证是否被调用）。"""
    counter = {"n": 0}

    def _ok(*a, **kw):
        counter["n"] += 1
    monkeypatch.setattr("app.services.agent_service.ping_llm", _ok)
    return counter


@pytest.mark.asyncio
async def test_create_rejected_when_ping_fails(client, auth_headers, monkeypatch):
    """ping 失败 → 400 且 Agent 未落库。"""
    _ping_raises(monkeypatch)
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "NoSave", "llm_config": VALID_LLM},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400
    assert "鉴权失败" in resp.json()["message"]
    listing = (await client.get("/api/v1/agents", headers=auth_headers)).json()["data"]
    assert all(a["name"] != "NoSave" for a in listing)


@pytest.mark.asyncio
async def test_create_skips_ping_when_validate_false(client, auth_headers, monkeypatch):
    """validate=false → ping 不被调用：把 ping mock 成必抛，validate=false 下仍应创建成功。"""
    _ping_raises(monkeypatch)  # 若 ping 被调，必抛 → 创建会 400
    resp = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "Skipped", "llm_config": VALID_LLM},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200  # ping 没被调，所以没抛


@pytest.mark.asyncio
async def test_create_rejected_when_kb_not_found_even_with_validate_false(client, auth_headers, monkeypatch):
    """validate=false 也不豁免引用校验：不存在的 kb → 400。"""
    resp = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "BadRef", "llm_config": VALID_LLM, "knowledge_base_ids": ["no-such-kb"]},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400
    assert "no-such-kb" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_accepts_builtin_tool(client, auth_headers, monkeypatch):
    """内置 tool_id 合法 → 创建成功（validate=false）。"""
    resp = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "Builtin", "llm_config": VALID_LLM, "tool_ids": ["calculator"]},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200


@pytest.mark.asyncio
async def test_update_full_revalidate_triggers_ping(client, auth_headers, monkeypatch):
    """更新即使只改 name 也触发完整复检（ping 被调用一次）。"""
    create = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "Old", "llm_config": VALID_LLM},
        headers=auth_headers,
    )
    agent_id = create.json()["data"]["id"]
    counter = _ping_succeeds_counting(monkeypatch)
    resp = await client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "New"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200
    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_update_rejected_when_ping_fails_keeps_old(client, auth_headers, monkeypatch):
    """更新 ping 失败 → 400 且 Agent 配置仍是旧值（未 save）。"""
    create = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "Keep", "llm_config": VALID_LLM},
        headers=auth_headers,
    )
    agent_id = create.json()["data"]["id"]
    _ping_raises(monkeypatch)
    resp = await client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "Changed"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400
    got = (await client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)).json()["data"]
    assert got["name"] == "Keep"  # 旧值未变
```

- [ ] **Step 2: 跑新测试确认失败**

Run: `pytest tests/test_agent_validation_api.py -v`
Expected: FAIL — 创建仍返回 200（`code=200`），断言 `code == 400` 失败（校验尚未接入）

- [ ] **Step 3: 接入 service 层** —— 改 `app/services/agent_service.py`

顶部 import 追加：

```python
from app.core.llm import ping_llm
```

在 `_validate_references` 之后插入统一编排方法：

```python
    def _validate(self, llm_config, kb_ids, tool_ids, validate: bool) -> None:
        """完整可用性校验（创建/更新共用）。任一失败 raise ValueError。

        引用校验始终执行（本地、零成本）；LLM ping 受 validate 开关豁免。
        """
        self._validate_references(kb_ids, tool_ids)
        if validate:
            ping_llm(llm_config)
```

替换 `create`（`:24-40`）为：

```python
    def create(self, req: AgentCreateRequest, validate: bool = True) -> AgentConfig:
        """创建 Agent。自动生成 12 位 hex ID，默认启用（status=1）。

        创建前做完整可用性校验；失败抛 ValueError（由路由转 400），不落库。
        """
        self._validate(req.llm_config, req.knowledge_base_ids, req.tool_ids, validate)
        agent = AgentConfig(
            id=uuid.uuid4().hex[:12],
            name=req.name,
            description=req.description,
            system_prompt=req.system_prompt,
            llm_config=req.llm_config,
            memory_config=req.memory_config,
            capabilities=req.capabilities,
            knowledge_base_ids=req.knowledge_base_ids,
            tool_ids=req.tool_ids,
            status=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return agent_store.save(agent)
```

替换 `update`（`:42-52`）为：

```python
    def update(self, agent_id: str, req: AgentUpdateRequest, validate: bool = True) -> Optional[AgentConfig]:
        """部分更新 Agent。只修改请求中显式传入的字段（exclude_unset=True）。

        合并后做完整复检（与创建一致）：即使只改 name 也重新 ping + 校验引用。
        校验失败抛 ValueError（路由转 400），不 save，旧 Agent 原子不变。
        """
        agent = agent_store.get(agent_id)
        if agent is None:
            return None

        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(agent, field, value)
        agent.updated_at = datetime.now()

        self._validate(agent.llm_config, agent.knowledge_base_ids, agent.tool_ids, validate)
        return agent_store.save(agent)
```

- [ ] **Step 4: 路由层加 `validate` 参数 + 异常信封** —— 改 `app/api/v1/agent.py`

替换 `create_agent`（`:27-30`）为：

```python
@router.post("/agents")
async def create_agent(body: AgentCreateRequest, validate: bool = True):
    try:
        agent = agent_service.create(body, validate=validate)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    return Result.success(data=agent)
```

替换 `update_agent`（`:33-38`）为：

```python
@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdateRequest, validate: bool = True):
    try:
        agent = agent_service.update(agent_id, body, validate=validate)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    if agent is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success(data=agent)
```

> `validate: bool = True` 作为非路径、非 Body 参数，FastAPI 自动从 query string 解析（`?validate=false`）。FastAPI 的 bool 解析接受 `true/false/1/0` 等。

- [ ] **Step 5: 修复受影响的现有测试**

`tests/test_agent_api.py::test_agent_crud_lifecycle` —— 给 create 和 update 的 URL 加 `?validate=false`：

把 `:45` 的
```python
    resp = await client.post("/api/v1/agents", json=SAMPLE_AGENT, headers=auth_headers)
```
改为
```python
    resp = await client.post("/api/v1/agents?validate=false", json=SAMPLE_AGENT, headers=auth_headers)
```
把 `:55-58` 的 PUT URL 改为 `f"/api/v1/agents/{agent_id}?validate=false"`。

`tests/test_chat.py::test_chat_disabled_agent` —— 该测试 create（`:54`，假 key `sk-test`）和随后禁用用的 PUT（`:67`，改 `status=0`）现在都会触发完整复检 ping，必须都加 `?validate=false`：create URL 改为 `"/api/v1/agents?validate=false"`，PUT URL 改为 `f"/api/v1/agents/{agent_id}?validate=false"`。该测试意图是对话禁用态，不关心 ping。

`tests/test_chat.py::test_chat_missing_llm_key_returns_500_envelope` —— 把 `:93` 建 Agent 的 URL 改为 `"/api/v1/agents?validate=false"`（该测试要测「对话时 key 不可解析→500」，必须先用逃生口建出无 key 的 Agent；引用校验空列表通过，ping 被豁免，创建成功）。

- [ ] **Step 6: 跑端到端新测试确认通过**

Run: `pytest tests/test_agent_validation_api.py -v`
Expected: PASS（6 passed）

- [ ] **Step 7: 跑全量回归确认全绿**

Run: `pytest -q`
Expected: PASS（含修好的 `test_agent_crud_lifecycle` / `test_chat_disabled_agent` / `test_chat_missing_llm_key_returns_500_envelope`）

- [ ] **Step 8: 提交**

```bash
git add app/services/agent_service.py app/api/v1/agent.py tests/test_agent_validation_api.py tests/test_agent_api.py tests/test_chat.py
git commit -m "feat(agent): 创建/更新接入可用性校验（ping+引用），失败拒绝落库；路由加 validate 跳过开关"
```

---

## Task 5: 文档同步 + code-review

更新业务流程文档、写变更记录、跑 code-review（项目强制流程）。

**Files:**
- Modify: `docx/business-flow.md`（3.1 Agent 管理流程加校验步骤）
- Create: `docs/changelogs/2026-06-28-agent-availability-validation.md`

- [ ] **Step 1: 更新业务流程文档** `docx/business-flow.md`

在「3.1 Agent 管理流程」中创建/更新 Agent 的步骤里补充：创建与更新时系统会做可用性校验（LLM 连通性 ping + KB/tool 引用完整性），任一失败返回 `code=400` 且不落库；更新为完整复检；`?validate=false` 可豁免 ping（引用校验不豁免）。具体措辞与现有 3.1 风格一致（先 Read 该节再改）。

- [ ] **Step 2: 写变更记录** `docs/changelogs/2026-06-28-agent-availability-validation.md`

参考 `docs/changelogs/2026-06-27-llm-apikey-env-resolution.md` 的格式（先 Read 它）。记录：新增能力（创建/更新前置校验）、新增/修改文件、行为变化（失败即拒绝、`validate` 逃生口）、对调用方的影响（建 Agent 前需保证 LLM 可联通，否则加 `?validate=false`）。

- [ ] **Step 3: 跑 code-review**

对本分支相对实现前的 diff 跑 `/code-review`（项目 memory 强制：代码改动后必须 review 再定稿）。按 review 结果修复后再提交。

- [ ] **Step 4: 提交文档**

```bash
git add docx/business-flow.md docs/changelogs/2026-06-28-agent-availability-validation.md
git commit -m "docs: 同步 Agent 可用性校验的业务流程与变更记录"
```

---

## 假设与待办

- **openai 异常构造签名**：本计划按 openai 2.38.0 编写（`AuthenticationError/NotFoundError/RateLimitError` 需 `response` + `body`；`APIConnectionError` 仅需 `message`）。若实际版本签名不同，调整 `_http_resp` helper 即可，不影响 `ping_llm` 实现的异常分支结构。
- **`ChatOpenAI(timeout=...)`**：langchain-openai 0.3.35 使用 `timeout` 参数。若该版本报参数名错误，改为 `request_timeout`（同义别名）。
- **测试环境 `data/`**：引用校验测试假设 `data/knowledge_bases/`、`data/tools/` 下不存在 `no-such-kb` / `no-such-tool`（合理；测试用 ID 故意取不存在值）。
