# Agent 可用性验证功能 — 设计文档（Spec）

> 版本：1.0.0 | 日期：2026-06-28 | 所属项目：acgagent-ai
> 状态：待评审 → 通过后进入 writing-plans

---

## 1. 目标与背景

当前创建 / 更新 Agent **完全不做任何校验**（`agent_service.create()` / `update()` 只构造对象并写 JSON）。唯一存在的校验在**对话时**（`chat.py:35-38`），且仅检查「api_key 能否解析（是否存在）」，**不检查 key 是否有效、base_url 是否可达、模型名是否正确、引用资源是否存在**。结果是一个配错的 Agent 要等到真正对话时才暴露，且在流式模式下可能在中途崩溃。

本功能在**创建 / 更新阶段**前置一道可用性校验，让「不可用」的 Agent 根本无法落库，把错误左移到配置环节。

### 1.1 关键边界决策（已与用户确认）

| # | 决策 | 选择 |
|---|---|---|
| 1 | 验证范围 | **LLM 连通性 ping（主）+ 引用完整性（顺带）** |
| 2 | ping 方式 | **方案 A：发一次最小 completion**（`max_tokens=1`、非流式、带超时），真实触达 provider |
| 3 | 失败处理 | **失败即拒绝**：不创建 / 不更新，返回 `code=400` + 可读原因 |
| 4 | 触发时机·创建 | 创建时默认校验（`validate=true` 时执行 LLM ping + 引用完整性；ping 可被 #6 豁免，引用不可） |
| 5 | 触发时机·更新 | **仅对本次实际变更的字段做对应校验**：改 `llm_config` → ping；改 `knowledge_base_ids` → 校验 KB 存在；改 `tool_ids` → 校验 tool 合法。未变更字段不触发，避免无谓费用 / 延迟 |
| 6 | 跳过开关 | 路由 query 参数 `validate: bool = True`；`?validate=false` **仅豁免 LLM ping**（昂贵、网络依赖） |
| 7 | 引用完整性是否随 `validate=false` 豁免 | **不豁免**。引用校验纯本地、零成本、零网络依赖，始终执行 |
| 8 | ping 超时 | 默认 **15s**（`ping_llm` 默认参数，先不做成配置项 — YAGNI） |
| 9 | 异常风格 | 沿用项目现有惯例：`ping_llm` / 引用校验失败抛 `ValueError(中文可读原因)`；路由层捕获转 `Result.error`（与 `resolve_api_key` 一致，Rule 11） |
| 10 | 内置工具合法性 | `calculator` / `web_search` / `knowledge_search` 视为合法 tool_id（不查 `tool_store`，因其不入库） |

---

## 2. 范围

### 2.1 本 spec 覆盖

1. **LLM 连通性 ping**：用 agent 的 `llm_config` 发一次最小 completion，验证 key 有效 + base_url 可达 + 模型名正确。
2. **引用完整性校验**：`knowledge_base_ids` / `tool_ids` 指向的资源必须存在（自定义工具查 `tool_store`；内置工具按 ID 白名单放行）。
3. **触发编排**：在 `create` / `update` 两条路径接入校验，失败即拒绝落库。
4. **跳过开关**：`validate` query 参数（仅豁免 ping）。

### 2.2 明确不在本 spec 范围

- 不修复 `chat_service._get_tools` **不消费自定义工具**（`tool_store` 中的工具）这一既有行为 — 仅保证引用 ID 合法，不改变对话时工具实例化逻辑。
- 不引入 agent 的 `last_validated_at` / 校验状态持久化字段 — 失败即拒绝，成功才落库，无需记录校验时间（YAGNI）。
- 不做异步 / 后台校验 — 创建是低频管理操作，同步阻塞 1~2s 可接受。
- 不把 `validate=false` 暴露为持久化开关（仅本次请求生效）。

---

## 3. 架构

### 3.1 分层（沿用现有结构，最小改动）

```
Core     app/core/llm.py               （改；新增 ping_llm(config, timeout)）
Tools    app/tools/__init__.py         （改；新增 BUILTIN_TOOL_IDS 常量，供校验与 chat_service 共用，消除两处硬编码）
Service  app/services/chat_service.py  （改；_get_tools 改为引用 BUILTIN_TOOL_IDS — 针对性去重，Rule 7）
         app/services/agent_service.py （改；create/update 接入校验，新增 _validate_* 私有方法 + validate 形参）
API      app/api/v1/agent.py           （改；create/update 加 validate query param，捕获 ValueError → Result.error(400)）
Models   （不改；AgentConfig 无需新字段）
```

> 引入 `BUILTIN_TOOL_IDS` 常量并让 `chat_service._get_tools` 引用它，是因为校验逻辑必须与对话时的工具判定**保持同一真相**（Rule 7：不折中处理两处冲突的硬编码）。这是服务于本次正确性的针对性改进，不顺带重构其它内容（Rule 3）。

### 3.2 校验时序

```
POST /api/v1/agents?validate=true
  └─ create_agent(body, validate)
       └─ agent_service.create(req, validate)
            ├─ _validate_references(req)          # 本地，始终执行；不通过 → ValueError
            ├─ if validate: ping_llm(req.llm_config)   # 网络；validate=false 跳过
            ├─ (全通过) → 构造 AgentConfig → agent_store.save → 返回
            └─ (任一失败) → 抛 ValueError，不 save

PUT /api/v1/agents/{id}?validate=true
  └─ update_agent(agent_id, body, validate)
       └─ agent_service.update(agent_id, req, validate)
            ├─ 读旧 agent（不存在 → 返回 None → 路由 404）
            ├─ 对"本次变更的字段"分别校验：
            │     llm_config 变更      → ping（受 validate 开关）
            │     knowledge_base_ids 变更 → 校验这些 KB 存在
            │     tool_ids 变更          → 校验这些 tool 合法
            ├─ (全通过) → setattr 合并 → save → 返回
            └─ (任一失败) → 抛 ValueError，旧 agent 不变（原子）
```

---

## 4. 核心逻辑

### 4.1 LLM 连通性 ping（`app/core/llm.py`）

```python
def ping_llm(config: LLMConfig, timeout: float = 15.0) -> None:
    """发起一次最小 completion 验证 LLM 连通性。成功 return；失败 raise ValueError(中文原因)。

    独立构造一个非流式、max_tokens=1 的 ChatOpenAI（不复用 create_chat_model，
    后者为对话用、streaming=True 且无超时），复用 resolve_api_key 取 key。
    """
```

实现要点：
- 复用 `resolve_api_key(config.provider, config.api_key)` 取 key —— 缺失时它已抛 `ValueError`（沿用现有「key 不可解析」语义），`ping_llm` 不重复处理。
- 构造 `ChatOpenAI(model=..., base_url=..., api_key=..., max_tokens=1, temperature=0, streaming=False, request_timeout=timeout)`，`invoke([HumanMessage(content="ping")])`。
- 捕获异常并翻译成可读原因（见 §6 异常映射表）。
- **限流视为可用**：`openai.RateLimitError` 说明已成功触达 provider 并通过到限流判定（key + endpoint 均有效），`ping_llm` 视为通过、不抛错。

### 4.2 引用完整性校验（`agent_service` 私有方法）

```python
def _validate_references(self, kb_ids: list[str], tool_ids: list[str]) -> None:
    """校验 KB / tool 引用存在。失败 raise ValueError(列出缺失 ID)。"""
    # KB：每个 id 必须 knowledge_store.get(id) is not None
    # Tool：每个 id 合法 ⟺ 在 BUILTIN_TOOL_IDS 中  或  tool_store.get(id) is not None
```

- KB：`knowledge_store.get(kb_id) is None` → 收集到缺失列表。
- Tool：`tid not in BUILTIN_TOOL_IDS and tool_store.get(tid) is None` → 收集到缺失列表。
- 任一缺失 → `ValueError(f"引用资源不存在: knowledge_base_ids={缺失kb}, tool_ids={缺失tool}")`。

### 4.3 更新时的「按变更字段校验」

`update()` 用 `req.model_dump(exclude_unset=True)` 判断哪些字段被显式传入：

| 变更字段 | 校验动作 | 受 `validate` 开关？ |
|---|---|---|
| `llm_config` | `ping_llm(new_llm_config)` | 是（`validate=false` 跳过） |
| `knowledge_base_ids` | `_validate_references(new_kb_ids, 当前tool_ids)` | 否（始终） |
| `tool_ids` | `_validate_references(当前kb_ids, new_tool_ids)` | 否（始终） |
| 其它（name / system_prompt / …） | 不触发任何校验 | — |

> 注意：引用校验对「未变更」的另一侧用**当前已存 agent 的值**，避免因部分更新漏判。

---

## 5. HTTP 契约变化

仅给两个既有端点加可选 query 参数，**无新端点、无 body 字段变化**。

| 方法 | 路径 | 变化 |
|---|---|---|
| POST | `/api/v1/agents` | 加 `validate: bool = True`（query） |
| PUT | `/api/v1/agents/{agent_id}` | 加 `validate: bool = True`（query） |

### 5.1 失败响应示例（`code=400`）

```jsonc
// key 鉴权失败
{ "code": 400, "message": "Agent LLM 不可用: API Key 鉴权失败，请检查 llm_config.api_key 或 ACG_AI_LLM_KEY_<PROVIDER>" }

// 模型名错
{ "code": 400, "message": "Agent LLM 不可用: 模型 'deepseek-chet' 不存在，请检查 llm_config.model" }

// base_url 不可达 / 超时
{ "code": 400, "message": "Agent LLM 不可用: 无法连接 base_url（或超时 15s），请检查 llm_config.base_url" }

// 引用资源不存在
{ "code": 400, "message": "引用资源不存在: knowledge_base_ids=['no-such-kb'], tool_ids=[]" }
```

成功响应不变（沿用 `Result.success(data=agent)`）。

---

## 6. 错误处理（异常映射）

| 捕获的异常 | 原因文案 | 处理 |
|---|---|---|
| `ValueError`（来自 `resolve_api_key`，key 缺失） | 沿用其原消息 | 抛 `ValueError` → 路由 400 |
| `openai.AuthenticationError` | API Key 鉴权失败 | 抛 `ValueError` → 路由 400 |
| `openai.NotFoundError` | 模型名不存在（或 endpoint 404） | 抛 `ValueError` → 路由 400 |
| `openai.APIConnectionError` / `httpx.TimeoutException` / `openai.APITimeoutError` | 无法连接 base_url / 超时 | 抛 `ValueError` → 路由 400 |
| `openai.RateLimitError` | （视为可用，不抛错） | return（通过） |
| 其它未预期异常 | 「LLM 校验失败: {原始信息}」 | 抛 `ValueError` → 路由 400（Fail Loud，不静默放行，Rule 12） |
| 引用缺失 | 列出缺失 ID | 抛 `ValueError` → 路由 400 |

> 统一 `code=400`（业务码，表示「校验未过 / 配置不可用，请求被拒」），原因细分放 `message`。Result 信封的 `code` 是业务码而非 HTTP 状态码（与 `chat.py` 现有用法一致）。

---

## 7. 测试（CLAUDE.md 规则 9：验证意图，非仅行为）

mock `ChatOpenAI.invoke`（复用 `tests/conftest.py` 现有 mock 机制），不真实打外部 provider。每个用例绑定一条业务意义。

| 用例 | 验证的意图 |
|---|---|
| `test_create_pings_llm_before_save` | 创建成功路径确实发了 ping，且成功才落库 | 创建保证可用 |
| `test_create_rejected_when_llm_auth_fails` | 鉴权失败 → 400 且 `agent_store` 查不到该 agent | 不可用的 agent 不入库 |
| `test_create_rejected_when_model_not_found` | 模型名错 → 400 未落库 | 能抓到模型名错误（方案 A 相对 `/models` 的价值） |
| `test_create_rejected_when_llm_unreachable` | 连接错误 / 超时 → 400 未落库 | 能抓到 base_url 不通 |
| `test_ratelimit_treated_as_available` | `RateLimitError` → 视为通过、正常创建 | 限流不代表配置错 |
| `test_create_skips_ping_when_validate_false` | `validate=false` → 不调 invoke，即使配置无效也创建 | 排查 / 抖动逃生口 |
| `test_update_pings_only_when_llm_config_changed` | 更新改 `llm_config`→invoke 被调用；只改 `name`→invoke **未**被调用 | 避免无谓费用 |
| `test_update_rejected_when_ping_fails_keeps_old` | 更新改 `llm_config` 且 ping 失败 → 400 且 agent 配置仍为旧值 | 更新原子性，不半改 |
| `test_create_rejected_when_kb_not_found` | `knowledge_base_ids` 含不存在 id → 400 未落库 | 引用完整性 |
| `test_create_rejected_when_custom_tool_not_found` | `tool_ids` 含不存在的自定义 id → 400 | 引用完整性 |
| `test_create_accepts_builtin_tool_id` | `tool_ids=['calculator']` → 通过、不误判 | 内置工具合法 |
| `test_validate_false_still_checks_references` | `validate=false` 但 KB 不存在 → 仍 400 | 引用校验不豁免 |

---

## 8. 假设与待办

- **假设**：agent 的 LLM provider 均为 OpenAI 兼容协议（与现有 `create_chat_model` 一致），`invoke` 走同一协议。
- **假设**：`tests/conftest.py` 现有 mock LLM 机制可复用来 mock `ChatOpenAI.invoke`（实施时确认；若不可，则在该文件补一个针对 `ping_llm` 的 mock fixture）。
- **待办（实施时确认）**：`openai` 各异常类的确切导入路径与 langchain-openai 当前版本的透传情况；若某些异常被 langchain 包装，按实际类型映射，保持「失败 → 可读原因」语义。
- **后续可选**：若低频管理场景未来出现 ping 延迟不可接受，再考虑异步校验 + `last_validated_at` 字段（当前 YAGNI）。
- **文档同步**：实现完成后更新 `docx/business-flow.md` 的 3.1 Agent 管理流程（加入「校验」步骤）；变更记录写 `docs/changelogs/`。
