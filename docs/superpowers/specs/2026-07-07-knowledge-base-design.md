# 结构化知识库（风格/角色/故事）— 设计文档

- 日期：2026-07-07
- 分支：aiagent_dev
- 状态：已与用户确认设计，待出实施计划

## 1. 背景与目标

项目已有一套**文档型 RAG 知识库**（`knowledge_base.py` + ChromaDB：上传文件 → 分块 → embedding → 检索文档片段）。
本次需要在此基础上新增一类**结构化知识**，用于维护：

- 用户的风格偏好
- 动漫风格（参考库）
- 故事集
- 动漫角色设定

这些内容更像是「带字段的结构化条目」（如角色 = 姓名+外貌+性格+背景故事），而非「上传一份文件再切块」。
现有文档型 KB 无法对单个「角色/故事」做结构化增删改，也发挥不出字段化优势。

目标：
- 提供结构化条目的 CRUD（类型化字段 + 公共/私有作用域）。
- 复用现有 ChromaDB 基础设施做语义检索（**不**复用文档 KB 的 collection，避免污染）。
- 核心设定**自动注入** Agent 的 system_prompt；次要/大量条目经**工具按需查**。
- 完全遵循现有五件套约定（model/store/service/api/tool），零风格分歧。

## 2. 关键决策（与用户逐项确认）

| # | 决策点 | 选择 | 理由 |
| --- | --- | --- | --- |
| ① | 与现有文档型 KB 的关系 | **混合：新增结构化条目 + 复用 ChromaDB 检索** | 结构化字段是核心诉求；复用 ChromaDB 基础设施（client/embedding）而非文档 KB collection，保持干净分离。 |
| ② | 作用域/归属 | **公共库 + 用户私有**（条目带 `scope` + `user_id`） | 项目无真实用户体系（Agent/KB 均全局，`user_id` 仅可选字符串）；「用户风格偏好」需私有隔离，「动漫风格/角色/故事」做公共参考库。 |
| ③ | 消费方式 | **核心设定自动注入 system_prompt + 工具按需查** | 风格/角色等核心设定应每次对话生效（自动注入）；大量条目按需检索省 token。 |
| ④ | 内容类型建模 | **3 个 type（style/character/story），scope 区分公共/私有** | 「动漫风格」=公共 style，「用户风格偏好」=私有 style，避免重复建模。「类型/字段方案由设计文档固化」已确认。 |
| ⑤ | 激活机制 | **Agent 上 `active_entry_ids: list[str]` 显式关联**（条目不带 `is_active`） | 与现有 `knowledge_base_ids`/`tool_ids` 同构；注入哪些条目完全由 Agent 配置决定，干净可控。 |
| ⑥ | 注入字段建模 | **单模型 + `details: dict`**（不强类型 discriminated-union） | Rule 2 简单优先；三类字段差异大，多态会让 store/service/api 膨胀；`details` 配合本 spec 约定 schema 足够清晰，易演进。 |
| ⑦ | 工具检索范围（v1） | **仅公共库**；私有条目只经自动注入触达 | 避免把 `user_id` 串进工具构造（与现有 `knowledge_search` 同为「Agent 关联驱动」）；私有风格偏好的正解本就是每次自动注入。 |

## 3. 数据模型

### 3.1 内容类型映射（决策④）

| 用户描述 | type | scope |
| --- | --- | --- |
| 动漫风格 | `style` | public |
| 用户的风格偏好 | `style` | private |
| 动漫角色设定 | `character` | public（可 private） |
| 故事集 | `story` | public（可 private） |

### 3.2 `app/models/knowledge_entry.py`

```python
class EntryType(str, Enum):     # style / character / story
class EntryScope(str, Enum):    # public / private

class KnowledgeEntry(BaseModel):
    id: str                     # uuid hex[:12]，同现有
    type: EntryType
    scope: EntryScope
    user_id: str | None         # private 必填；public 为 None
    name: str                   # 名称（story 标题亦用 name，保持一致）
    summary: str                # 一句话概述 → 同时是 embedding 文本 + 列表展示
    tags: list[str] = []
    details: dict = {}          # 类型特有字段（见 3.3），v1 不强类型
    created_at: datetime
    updated_at: datetime

class KnowledgeEntryCreateRequest(BaseModel):
    type: EntryType
    scope: EntryScope
    user_id: str | None = None
    name: str
    summary: str
    tags: list[str] = []
    details: dict = {}

class KnowledgeEntryUpdateRequest(BaseModel):
    # type 不可变（见 §6）；其余可选
    scope: EntryScope | None = None
    user_id: str | None = None
    name: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    details: dict | None = None
```

### 3.3 `details` 字段约定（spec 固化，v1 不强类型；决策⑥）

| type | details 键 |
| --- | --- |
| `style` | `visual_elements`(视觉要素), `tone`(调性), `example_prompts`[](示例描述) |
| `character` | `series`(出处), `appearance`(外貌), `personality`(性格), `background`(背景), `traits`[](特征), `speech_style`(说话风格) |
| `story` | `genre`[](类型), `setting`(世界观), `plot_points`[](关键情节), `tone`(基调), `linked_characters`[](关联角色) |

> 注入/检索时仅渲染存在的键，缺失键跳过（见 §4.2）。

## 4. 架构与组件

完全对称现有 `knowledge_base` 五件套。

### 4.1 存储与向量化

| 层 | 文件 | 说明 |
| --- | --- | --- |
| store | `app/db/knowledge_entry_store.py` | JSON 文件 `data/knowledge_entries/{id}.json`，模块级单例（同 `knowledge_store`） |
| service | `app/services/knowledge_entry_service.py` | CRUD + ChromaDB 同步，模块级单例 |
| api | `app/api/v1/knowledge_entry.py` | REST，挂到 `router.py` |
| tool | `app/tools/knowledge_entry_lookup.py` | 注册进 `BUILTIN_TOOLS` |
| core | `app/core/knowledge_injector.py` | 自动注入 helper |

**向量化（复用 ChromaDB 基础设施，非文档 KB collection；决策①）：**
- 独有 collection `kb_structured_entries`，`metadata={"hnsw:space": "cosine"}`（与 `user_preferences` 同模式）。
- embedding 文本 = `name + summary + tags` 拼接；metadata = `{entry_id, type, scope, user_id}`。
- create/update → `col.upsert`；delete → `col.delete`（best-effort，同 `knowledge_service.delete` 清理 collection 的写法）。
- 复用 ChromaDB 默认 embedding：调 `col.query(query_texts=[...])`，与现有 `knowledge_search`/`retriever` 一致（现有 `RAGRetriever.OpenAIEmbeddings` 实际未被使用，v1 不强求配置 embedding model）。

### 4.2 自动注入 `app/core/knowledge_injector.py`（决策③⑤）

```python
def build_system_content(agent_config) -> str:
    # 1. 取 agent_config.active_entry_ids → 逐个 knowledge_entry_store.get(id)
    #    缺失/已删 → 跳过 + log warning（绝不中断对话）
    # 2. 按 type 分组，渲染【参考设定】块（仅含 details 中非空字段）
    # 3. system_prompt + 渲染块拼接；无 system_prompt 且无激活条目 → ""
```

注入块示例（token 友好，竖线分隔，跳过空字段）：
```
【参考设定】
[风格] 赛博朋克：高饱和霓虹+机械义体 | 调性:冷峻
[角色] 初音(Vocaloid)：双马尾歌姬 | 性格:元气 | 口吻:活泼
[故事] 星海日记：少女星际旅行 | 世界观:近未来 | 情节:发现遗迹/启程
```

**注入挂载点（两处，外科手术式；决策③）：**
- `chat_service._build_messages`：`SystemMessage(content=agent_config.system_prompt)` →
  `SystemMessage(content=build_system_content(agent_config))`（覆盖 `chat` + `tool_use` 模式）。
- `workflow.stream_workflow`（`workflow.py:120`）：同样改用 `build_system_content(agent_config)`（覆盖 `workflow` 模式）。

两处共用同一 helper，避免逻辑重复。无激活条目时 `build_system_content` 返回原 `system_prompt`，行为逐字一致（**零回归**）。

### 4.3 按需工具 `app/tools/knowledge_entry_lookup.py`（决策③⑦）

```python
class KnowledgeEntryLookupTool(BaseAgentTool):
    # id/name = "knowledge_entry_lookup"
    # 无构造参数（仅搜公共库）→ chat_service._get_tools 走 else 分支实例化（同 calculator/web_search）
    def execute(self, query="", entry_type=None, **kwargs) -> str:
        # query 缺失 → 提示提供查询（同 knowledge_search）
        # 查 kb_structured_entries：where={scope:public, type?}（+ entry_type 过滤），n_results=3
        # 返回格式化条目；无结果 → "未找到相关信息"
```

注册：`app/tools/__init__.py` 的 `BUILTIN_TOOLS` 增加 `"knowledge_entry_lookup": KnowledgeEntryLookupTool`。

> **v1 边界（决策⑦）**：工具仅检索公共库；私有条目只能经 `active_entry_ids` 自动注入触达。理由见决策⑦。

### 4.4 Agent 模型变更（决策⑤）

- `AgentConfig` / `AgentCreateRequest` / `AgentUpdateRequest` 新增 `active_entry_ids: list[str] = []`。
- `agent_service._validate_references` 扩展：新增 `entry_ids` 参数，逐个 `knowledge_entry_store.get(id)` 存在性校验（本地 JSON 读，零成本，与 KB/tool 一致）。缺失 → `ValueError`（路由转 400）。

## 5. 数据流

```
管理员                  后端                              ChromaDB            Agent 对话
 │                                                       │
 │─ POST /knowledge-entries ──► entry_service.create     │
 │   {type,scope,user_id,     │ JSON 存盘 + upsert ─────►│ kb_structured_entries
 │    name,summary,details}   ◄──── id                   │
 │                                                       │
 │─ POST /agents {active_entry_ids:[...]} ──► 校验引用存在性（含 entry）
 │                                                       │
 │─ POST /chat/{id}/completions ──► chat_service         │
 │                                 │ _build_messages:     │
 │                                 │   build_system_content
 │                                 │   → 取激活条目→渲染  │
 │                                 │   → SystemMessage    │
 │                                 ├── (含【参考设定】) ──► LLM
 │ ◄──── SSE 文本流 ───────────────│                      │
 │                                                         │
 │   LLM 自主决定按需查：bind_tools(knowledge_entry_lookup)│
 │                                 ├── query 公共库 ─────►│ kb_structured_entries
 │                                 │◄── 格式化条目 ───────│
```

## 6. 错误处理（Fail Loud，Rule 12）

- 创建/更新 `scope=private` 但缺 `user_id` → service 抛 `ValueError` → 路由转 400（同 Agent 校验模式）。
- 未知 `type` / `scope` → pydantic 422。
- 更新时试图改 `type` → 400 拒绝（`type` 为条目身份的一部分，不可变）。
- 更新/删除不存在 → 404。
- ChromaDB 同步失败 → log warning，**不**阻断 CRUD（best-effort，同 `knowledge_service.delete` 吞 collection 异常）。
- 注入遇 `active_entry_ids` 中已删条目 → 跳过 + log warning，绝不中断对话。
- Agent 创建/更新校验遇缺失 entry id → `ValueError` → 400（与 KB/tool 引用校验一致）。
- 工具空 query → 返回提示串（同 `knowledge_search`），不抛错。

## 7. 范围与非目标

- **不做用户认证体系**：`user_id` 仅为字段 + 查询过滤，不引入登录/鉴权（与现有 `preference_store` 一致）。
- **工具不检索私有库**（决策⑦）：私有条目仅自动注入；用户级按需检索私有条目为后续增强。
- **`details` 不强类型**（决策⑥）：v1 用 dict + spec 约定；discriminated-union 留待后续按需升级。
- **不做条目版本/软删除**：YAGNI；删除即移除 JSON + ChromaDB 记录。
- **不自动从 `details` 全文重建 embedding**：embedding 文本固定为 `name+summary+tags`，`details` 仅参与注入渲染。
- **不改文档型 KB**：现有 `knowledge_base`/`document`/`retriever` 链路零改动。

## 8. 测试策略（验证意图，Rule 9）

新增 `tests/test_knowledge_entry.py` + 扩展现有：

- **store**：JSON 往返 CRUD（写后读一致；删除后 get 返回 None）。
- **service**：
  - create/update/delete 同步 ChromaDB（mock `get_chroma`，断言 upsert/delete 调用）；
  - `scope=private` 缺 `user_id` → 抛 `ValueError`（验证「私有必须归属用户」的业务意图）；
  - 更新改 `type` → 拒绝。
- **injector**：
  - 无激活条目/空 `active_entry_ids` → 返回原 `system_prompt`（零回归）；
  - 有条目 → 产出含【参考设定】的分组块，且仅含非空字段；
  - 激活列表含已删 id → 该条被跳过、其余正常注入（验证 Fail-soft 不中断）。
- **tool**：
  - 公共检索返回格式化条目；`entry_type` 过滤生效；空 query 返回提示；
  - 不返回 private 条目（验证决策⑦的作用域隔离意图）。
- **API**：CRUD 全链路（TestClient）；400（private 缺 user_id / 改 type）、404、422 校验。
- **集成**：
  - `chat_service._build_messages` 与 `workflow.stream_workflow` **两路径**在 `active_entry_ids` 非空时都注入设定块；空时逐字回归。
- **agent**：`active_entry_ids` 建模；`_validate_references` 对缺失 entry 抛错（扩展 `test_agent_validation.py`）。

## 9. 实施顺序（概要，详细步骤由 writing-plans 展开）

1. `models/knowledge_entry.py`（模型 + Enum + 请求体）+ store + 单测。
2. `services/knowledge_entry_service.py`（CRUD + ChromaDB 同步）+ 单测。
3. `core/knowledge_injector.py`（`build_system_content`）+ 单测。
4. `tools/knowledge_entry_lookup.py` + 注册 `BUILTIN_TOOLS` + 单测。
5. `api/v1/knowledge_entry.py` + 路由注册 + API 测试。
6. Agent 模型加 `active_entry_ids` + `_validate_references` 扩展 + 注入挂载两处改造 + 集成/校验测试。
7. 改动后跑 `/code-review`（项目规矩），再提交（中文 commit message，待用户放行）。
