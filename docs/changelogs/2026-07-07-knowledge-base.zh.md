# 结构化知识库（风格/角色/故事）— 设定自动注入 + 公共库检索

> 日期：2026-07-07 ~ 2026-07-11 | 类型：feat | 关联代码：`app/models/knowledge_entry.py`、`app/db/knowledge_entry_store.py`、`app/services/knowledge_entry_service.py`、`app/core/knowledge_injector.py`、`app/tools/knowledge_entry_lookup.py`、`app/api/v1/knowledge_entry.py` 等
> Plan：`docs/superpowers/plans/2026-07-07-knowledge-base.md` | Spec：`docs/superpowers/specs/2026-07-07-knowledge-base-design.md`

---

## 1. 背景

现有文档型 RAG 知识库（`knowledge_base` 五件套）面向"文档片段检索"。但 ACG 创作场景需要一类**结构化设定**——角色（character）、风格（style）、故事（story）——这些设定有固定字段结构，且需在对话时**自动注入** Agent 的 system_prompt，而非等 LLM 主动检索。

痛点：
- 角色性格 / 风格调性等"核心设定"每次对话都该带上，靠 LLM 自主调用检索工具不可靠（可能不调、可能漏）。
- 现有 KB 是非结构化文档，不适合存"角色=初音、性格=元气"这类带 schema 的设定。

---

## 2. 方案

在现有 `knowledge_base` 之上**对称新增**「结构化条目」五件套 + 一个注入器：

- **数据**：`KnowledgeEntry`（type: style/character/story × scope: public/private），JSON 存储 + 向量化进独立 ChromaDB collection `kb_structured_entries`（cosine），embedding 文本 = name+summary+tags。
- **自动注入**：Agent 新增 `active_entry_ids`；`build_system_content(agent_config)` 把激活条目渲染成【参考设定】块拼到 system_prompt 后，挂载在 `chat_service._build_messages` 与 `workflow.stream_workflow` 两处（空激活零回归）。
- **按需检索**：`knowledge_entry_lookup` 工具供 LLM 自主查**公共库**（private 经 active_entry_ids 注入触达，工具不搜）。

---

## 3. 改动清单

| 层 | 文件 | 说明 |
| --- | --- | --- |
| 模型 | `app/models/knowledge_entry.py` | `KnowledgeEntry` + `EntryType`/`EntryScope` Enum + Create/Update 请求体（Update `extra="forbid"`，type 不可变） |
| 存储 | `app/db/knowledge_entry_store.py` | JSON 文件存储（模块单例），`_path` 用 `Path(entry_id).name` 防 path traversal，`get` 损坏 JSON 防御 |
| 服务 | `app/services/knowledge_entry_service.py` | CRUD + ChromaDB 同步；`_validate_entry_id`（12 hex）前置于 get/update/delete；private 缺 user_id 抛 ValueError；update 用 `exclude_none=True` 防 null 损坏 |
| 注入器 | `app/core/knowledge_injector.py` | `build_system_content(agent_config)`：渲染【参考设定】块，仅渲染 details 非空字段 |
| 工具 | `app/tools/knowledge_entry_lookup.py` | `KnowledgeEntryLookupTool`（注册进 `BUILTIN_TOOLS`），`where={"scope":"public"}` 只搜公共库 |
| API | `app/api/v1/knowledge_entry.py` + `app/api/v1/router.py` | REST 5 端点 `/api/v1/knowledge-entries`：ValueError→400 / None→404 / extra=forbid→422 |
| Agent 集成 | `app/models/agent.py` + `app/services/agent_service.py` | `active_entry_ids` 字段 + `_validate_references` entry 引用校验（第 3 参可选，向后兼容） |
| 注入挂载 | `app/services/chat_service.py` + `app/core/workflow.py` | `_build_messages` / `stream_workflow` 改用 `build_system_content` |
| 测试 | `tests/test_knowledge_entry*.py`、`tests/conftest.py`（`fake_chroma`）、`tests/test_agent_validation.py` | store/service/injector/tool/API/注入 单测 + 集成测试 |

**安全硬化**（`b9ef859`）：store `_path` 用 `Path.name` + service `_validate_entry_id` 前置 + update 移除 user_id 字段（对齐 type 不可变）。
**code-review 修复**（`0a14242`）：update null 字段不再损坏条目（`exclude_none=True`）+ `store.get` 损坏 JSON 防御。

---

## 4. 设计决定

| 决定 | 理由 | 备选（为何不选） |
| --- | --- | --- |
| 访问控制 = 全局 X-API-Key，private 仅标签，**不在 Python 引入 per-user 隔离** | 架构分工：调用方（Java `acgAgent`）= Gateway JWT + `@RequireRole` + Java Service 归属校验；Python = 可信 CRUD/AI 引擎不持权限（`verify_api_key` 是 `/api/v1` 唯一鉴权）。同类 KB/文档/Agent 在 Java 均 `@RequireRole("admin")`。且 Java 当前未接 knowledge-entries，实际风险=0；在 Python 引入 per-user 会造双权限真相源 | 在 Python 加 ownership 校验：违反架构分工，且 Java 未透传 X-User-Id 到此接口 |
| 自动注入挂 chat + workflow 两处共用 `build_system_content` | 三种对话模式（chat/tool_use/workflow）都需注入，单一真相源避免漂移 | 各路径各自拼：重复逻辑、易漂移 |
| 工具只搜公共库（`scope=public`） | private 经 `active_entry_ids` 注入触达；工具让 LLM 能查到 private 会绕过"激活"语义（spec §4.3 v1 边界） | 工具也搜 private：模糊 public/private 边界 |
| ChromaDB 同步 best-effort（失败 log warning 不阻断 CRUD） | 向量检索是增强，不应因 ChromaDB 抖动阻断条目 CRUD | 同步失败回滚 CRUD：过度耦合 |
| `active_entry_ids` 第 3 参可选 | 向后兼容现有 2 参 `_validate_references` 调用 | 改签名强制传：破坏既有调用 |

---

## 5. 验证

- **单元/集成测试**：`pytest -q` → **176 passed**（含 store/service/injector/tool/API/注入/Agent 校验），无回归。
- **全分支 code-review**（opus，base=`935858e`）：注入连通性（`chat_service:120` + `workflow:121` 真调用）、零回归、`_validate_entry_id` 顺序、`Path.name` 防御均验证 OK；发现 2 个 correctness finding（update null 损坏链 + store.get 缺错误处理）→ 已修（`0a14242`）并补 3 个回归测试。
- **安全审查**（PostToolUse hook，`6f8607f`）：6 issue = 4 CRITICAL（缺 ownership）+ 1 HIGH（list user_id 来自 query）+ 1 MEDIUM（404 回显 entry_id）。前 5 项 **acknowledge** 为架构分工下不适用（见 §4，调用方 Java 未接此接口、权限归 Java）；1 MEDIUM 留后续。

---

## 6. 范围（未做）

- **Java 调用方尚未接入** knowledge-entries（无 controller/client）。接入前提（届时 Java 侧做）：controller 加 `@RequireRole`/归属校验；若需 per-user 则透传 `X-User-Id` + Java Service 做 private 归属校验；Python `get_user_id` 届时可启用为配合过滤。
- **per-user 隔离**：v1 不在 Python 做（架构分工，见 §4）。
- **workflow 注入挂载点测试偏弱**：`test_workflow_injects_when_active` 直接调 `build_system_content`，未真测 `stream_workflow`（brief 折中，避免真实 LLM）。留后续加强（spy + mock `llm.astream`）。
- **Pyright pre-existing 类型标注**（`dict vs LLMConfig` 测试 helper、`str|list` langchain content、`StateGraph/ainvoke` langgraph 等）：非本特性引入，留观察。

---

## 7. 配套修复与踩坑

- **brief 测试 `ghost` 与 `_validate_entry_id` 矛盾**：安全硬化给 service 加了 12 hex 校验后，brief 原 `test_update_nonexistent_404` 用 `"ghost"` 会触发 ValueError→400（非期望 404）。改为合法 hex `"deadbeef0000"` 命中 None→404。教训：brief 写于安全硬化前，跨 commit 的前置约束需在实现时校验。
- **update null 损坏链**（code-review F1）：`model_dump(exclude_unset=True)` 会保留显式设的 null，`setattr(None)` 越过 pydantic 校验持久化 null，下次 get 抛 ValidationError→API 500/聊天崩溃。修：`exclude_none=True`。
- **共享 working tree 冲突风险**（教训）：两路工作共享同一 working tree 时，看到不明 modified 文件先 `git log`/`git diff` 核来源，勿急于 `git checkout`（曾险些丢弃用户并行 docstring WIP）。
