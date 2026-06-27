# Agent 可用性校验（创建/更新前置校验：LLM ping + 引用完整性）

> 日期：2026-06-28 | 类型：feat | 关联代码：`app/core/llm.py`、`app/services/agent_service.py`、`app/api/v1/agent.py`、`app/tools/__init__.py`、`app/services/chat_service.py`、`app/tools/base.py`
> 合并自：`2026-06-28-builtin-tool-ids-extraction.md` + `2026-06-28-ping-llm-connectivity-check.zh.md`（已删除，内容折叠进本记录）

---

## 1. 背景

此前 Agent 的创建/更新只做参数校验（pydantic）即落库，无法保证配置真的可用：

- 配置的 LLM 可能 key 错 / base_url 不可达 / model 名拼错，直到对话时才暴雷；
- `knowledge_base_ids` / `tool_ids` 可能引用不存在的资源，到对话路由才报错，排查链路长。

本 feature 在 Agent **创建/更新落库前**加一道可用性校验：任一失败即拒绝（`code=400`）、不落库，让「落库的 Agent 一定可用」成为不变量。

---

## 2. 新增能力

| 能力 | 说明 |
| --- | --- |
| LLM 连通性探活 `ping_llm(config, timeout=15.0)` | 用 Agent 的 `llm_config` 发一次 `max_tokens=1`、非流式的最小 completion；按 `openai.*` 异常类型翻译成中文可操作 `ValueError`（告诉用户该查哪个字段）。`RateLimitError` 视为可达（能限流即说明 key/url/model 全对）。 |
| 引用完整性校验 `_validate_references` | `knowledge_base_ids` / `tool_ids` 必须实际存在：KB 查 `knowledge_store`，内置工具以 `BUILTIN_TOOL_IDS` 为准，自定义工具查 `tool_store`。缺失即拒，错误消息列出全部缺失 ID。 |
| 创建/更新前置校验 | `AgentService._validate` 编排二者：引用校验始终执行（本地、零成本），LLM ping 受 `validate` 开关控制。失败抛 `ValueError` → 路由转 `code=400`，**不落库**。 |
| `?validate=true|false` 逃生口 | POST/PUT `/api/v1/agents` 默认 `validate=true`。`?validate=false` **仅豁免 LLM ping**，引用校验仍执行（防止落库悬空引用）。 |
| 更新 = 完整复检 | 更新合并后重跑与创建一致的完整校验；即使只改 `name` 也会重新 ping + 校验引用，校验失败不 save、旧配置原子不变。 |

---

## 3. 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/core/llm.py` | 顶部 import 块新增 `import openai`、`from langchain_core.messages import HumanMessage`；新增 `ping_llm(config, timeout=15.0) -> None`（独立构造 `ChatOpenAI(max_tokens=1, streaming=False, timeout=...)`，不复用对话模型） |
| `app/services/agent_service.py` | 新增 `_validate_references` / `_validate`；`create` / `update` 落库前调用 `_validate`；`update` 改为合并后完整复检 |
| `app/api/v1/agent.py` | `POST /agents`、`PUT /agents/{id}` 新增 `validate: bool = True` 查询参数；捕获 `ValueError` 转 `Result.error(code=400)` |
| `app/tools/__init__.py` | 由空文件改为内置工具注册中心：`BUILTIN_TOOLS`（id→类）与派生的 `BUILTIN_TOOL_IDS`（单一真相源，供校验 + 实例化共用） |
| `app/services/chat_service.py` | `_get_tools` 由 switch 改为查 `BUILTIN_TOOLS` 映射；对话行为不变（含 KB 依赖、忽略未知/自定义 ID） |
| `app/tools/base.py` | 顺带修既有 latent bug：`to_langchain_tool` 的 `_tool_func` 补 docstring，使新版 langchain-core 的 `@tool` 转换不再抛 `ValueError`（解锁 Agent 校验的端到端测试） |
| `tests/test_llm.py` | 新增 `ping_llm` 测试组：成功 / 鉴权失败 / 模型未找到 / 连接错误（含超时）/ 限流视为可用 / 未知异常包装 / key 缺失原样传播 |
| `tests/test_chat_service_tools.py` | 新建：锁定 `BUILTIN_TOOL_IDS` 三 ID、`_get_tools` 行为与旧版一致 |
| `tests/test_agent_validation.py` | 新建：`_validate_references` / `_validate` 单元测试（KB/工具缺失、validate 开关、update 完整复检） |
| `tests/test_agent_validation_api.py` | 新建：POST/PUT 路由端到端——校验失败返回 400 且不落库、`?validate=false` 仅豁免 ping |

---

## 4. 行为变化与对调用方影响

- **行为变化（破坏性）**：创建/更新 Agent 时，若 LLM 不可达或引用资源缺失，现在返回 `code=400` 且不落库（此前会落库到对话时才暴雷）。
- **调用方需保证**：建 Agent 前 LLM 配置可联通（key 有效 / base_url 可达 / model 名正确）。否则：
  - 临时方案：加 `?validate=false` 跳过 ping（**仅 ping**，引用校验仍跑）；
  - 引用资源（KB / 自定义工具）必须先创建好，无逃生口。
- **更新语义**：更新是完整复检，不是「只校验改动的字段」。即使只改 `name` 也会重新 ping + 校验全部引用。

---

## 5. 设计决定

| 决定 | 理由 |
| --- | --- |
| `ping_llm` 独立构造 `ChatOpenAI`，不复用 `create_chat_model` | 后者为对话用（`streaming=True`、无超时）；探活要的是非流式、`max_tokens=1`、显式 timeout，目标不同（Rule 2）。 |
| 异常按 `openai.*` 类型翻译 | 给出「该检查哪个字段」的可操作中文提示；未知异常仍包装成 `ValueError` 不静默放行（Rule 12 Fail Loud）。 |
| `RateLimitError` 视为可用 | 能触发限流即说明 key/base_url/model 全对，把限流当不可用会让用户误判配置错。 |
| 引用校验始终执行，不受 `validate` 开关豁免 | 本地、零成本；放任悬空引用落库会把问题推迟到对话路由，违背「落库即可用」初衷。 |
| 内置工具映射作为单一真相源（`BUILTIN_TOOLS` → `BUILTIN_TOOL_IDS`） | 校验（合法 id 判断）与实例化共用一份映射，避免两份清单再次分叉（Rule 7）。 |
| 顺带修 `base.py` docstring latent bug | 1 行修复解锁端到端测试；该 bug 在 pristine master 上即存在，非本 feature 引入。 |

---

## 6. 验证

- 全链路 TDD（先 RED 后 GREEN）：`ping_llm` 7 用例、`BUILTIN_TOOL_IDS` 4 用例、`_validate_references` / `_validate` 单元用例、POST/PUT 端到端用例。
- 全量 `pytest` 通过，无回归、无 warning。

---

## 7. 范围（未做）

- embedding / 知识库密钥的同模式探活未扩展。
- 自定义工具的实例化路径未触碰（沿用既有行为，仅做存在性校验）。
- 未覆盖 `openai` 其它具体异常（如 `PermissionDeniedError`）——它们落到通用 `except Exception` 分支，仍以 `ValueError` 上报，符合 Fail Loud。
