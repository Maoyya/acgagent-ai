# acgagent-ai 技术架构文档

> 版本：2.0.0 | 更新日期：2026-06-27

---

## 1. 系统概述

acgagent-ai 是一个 AI Agent 引擎服务，提供 Agent 管理、对话（流式/同步）、RAG 知识库检索、文档处理、工具调用、系统提示词生成等核心能力。服务通过 REST API 对外暴露，可被前端应用或第三方系统快速集成。

**核心定位：** 多模型、多 Agent 的统一 AI 后端引擎。

---

## 2. 技术栈

| 层面       | 技术选型                         | 说明                          |
| ---------- | -------------------------------- | ----------------------------- |
| Web 框架   | FastAPI 0.115+                   | 异步高性能，自动 OpenAPI 文档 |
| 数据验证   | Pydantic v2 + pydantic-settings  | 请求/响应模型，环境配置管理   |
| LLM 编排   | LangChain 0.3+ / LangGraph 0.2+ | 对话链、工具绑定、工作流图   |
| LLM 接入   | langchain-openai                 | 兼容 OpenAI 协议（豆包/通义/DeepSeek） |
| 向量数据库 | ChromaDB（PersistentClient）     | 知识库 chunks 存储、会话记忆  |
| 文本切分   | langchain-text-splitters         | RecursiveCharacterTextSplitter |
| Token 计数 | tiktoken                         | 对话窗口 token 预算控制       |
| 文档解析   | pypdf / python-docx              | PDF、Word、TXT、MD 文件解析   |
| 包管理     | Poetry                           | 依赖管理、构建                |
| 运行时     | Uvicorn (uvloop)                 | ASGI 服务器                   |
| 容器化     | Docker (multi-stage build)       | Python 3.11-slim 镜像         |
| 测试       | pytest + pytest-asyncio          | 异步测试支持                  |

---

## 3. 系统架构

### 3.1 分层架构

```
┌──────────────────────────────────────────────────────┐
│                    API Layer (v1)                     │
│  router → agent / chat / knowledge_base / document / tool / prompt │
├──────────────────────────────────────────────────────┤
│                  Middleware Layer                     │
│         CORS · Logging · API Key Auth                │
├──────────────────────────────────────────────────────┤
│                  Service Layer                        │
│  AgentService · ChatService · KnowledgeService       │
│  DocumentService · ToolService · PromptService       │
├──────────────────────────────────────────────────────┤
│                    Core Layer                         │
│  LLM · Memory · Retriever · Workflow (LangGraph)     │
│  PromptBuilder · Moderator · CostEstimator           │
├──────────────────────────────────────────────────────┤
│                  Storage Layer                        │
│  AgentStore · KnowledgeStore · DocumentStore          │
│  MemoryStore · ToolStore · PreferenceStore · ChromaClient │
├──────────────────────────────────────────────────────┤
│                   Tools Layer                         │
│  BaseAgentTool → Calculator · WebSearch · KnowledgeSearch │
├──────────────────────────────────────────────────────┤
│                  Data (File System)                   │
│  JSON files (agents/kb/doc/tool) · Chroma SQLite     │
└──────────────────────────────────────────────────────┘
```

### 3.2 各层职责

**API 层** (`app/api/`)
- 路由定义、请求校验、HTTP 状态码映射
- 统一 `Result<T>` 响应封装
- API Key 认证（`X-API-Key` Header）
- SSE 流式响应（`text/event-stream`）

**中间件层** (`app/api/middleware.py`)
- CORS 全放通
- 请求/响应日志中间件

**API Key 鉴权**（`app/api/deps.py:verify_api_key`，作为 `/api/v1` 路由依赖注入，非严格意义上的中间件）
- 所有 `/api/v1/*` 路由默认依赖该校验；`/api/v1/health` 免鉴权
- 缺失/空 `X-API-Key` → 401（Missing API key）
- 比对不符 → 401（Invalid API key），比对采用 `secrets.compare_digest` 常数时间比较，防计时侧信道

**Service 层** (`app/services/`)
- 业务逻辑编排，不直接操作存储
- 对象创建（ID 生成、时间戳）、CRUD 操作
- `ChatService` 是核心：根据 Agent 能力（capabilities）选择对话模式（纯聊天 / 工具调用 / LangGraph 工作流）
- `PromptService`：系统提示词生成编排（meta-LLM 生成 → 单裁判校验 → 消耗估算 → 偏好写入）

**Core 层** (`app/core/`)
- `llm.py`：通过 `ChatOpenAI` 创建 LLM 实例，支持任意 OpenAI 兼容 API
- `memory.py`：`ConversationMemory` 管理，基于 token 预算裁剪历史消息
- `retriever.py`：`RAGRetriever` 从 ChromaDB 中检索相关 chunks
- `workflow.py`：`AgentWorkflow` 用 LangGraph StateGraph 编排「加载记忆 → RAG 检索 → 生成」流程
- `prompt_builder.py`：`PromptBuilder` 用 meta-LLM + 元提示词组装系统提示词
- `moderator.py`：`Moderator` 单裁判合规校验（规则集由 `PromptMode` 决定）
- `cost_estimator.py`：`CostEstimator` 基于 tiktoken 估算 token 消耗

**Storage 层** (`app/db/`)
- 基于 JSON 文件的轻量存储（agent_store / knowledge_store / document_store / tool_store）
- ChromaDB PersistentClient 存储向量数据（知识库 chunks、对话记忆）
- 每个知识库对应一个 Chroma collection（`kb_{id}_chunks`）
- 每个会话对应一个 Chroma collection（`memory_conv_{id}`）
- `preference_store.py`：`PreferenceStore` 把生成的 system_prompt 向量化存入 collection `user_preferences`（cosine 距离，供二期相似度推荐）

**Tools 层** (`app/tools/`)
- `BaseAgentTool` 抽象基类，统一 `execute()` 接口
- 自动转换为 LangChain Tool（`to_langchain_tool()`）
- 3 个内置工具：计算器、网络搜索、知识库搜索

---

## 4. 数据模型

### 4.1 核心实体关系

```
Agent (AgentConfig)
 ├── LLMConfig          # 模型配置
 ├── MemoryConfig       # 记忆策略
 ├── capabilities[]     # 能力标签: chat / rag / tool_use / workflow
 ├── knowledge_base_ids[] ──→ KnowledgeBase
 └── tool_ids[]         ──→ Tool

KnowledgeBase
 ├── EmbeddingConfig    # Embedding 模型配置
 ├── ChunkConfig        # 分块策略
 └── Document[]         # 关联文档

Document (DocumentVO)
 ├── knowledge_base_id  # 所属知识库
 ├── status             # processing / completed / failed
 └── chunk_count        # 分块数量

Tool (ToolVO)
 ├── type               # api / builtin
 └── config (ToolConfig) # API 工具的 HTTP 配置
```

### 4.2 通用响应

所有 API 返回统一的 `Result<T>` 结构：

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

### 4.3 提示词生成模型（prompt 模块）

prompt 模块（`/api/v1/prompts/*`）按用户零散要求自动生成系统提示词，模型定义在 `app/models/prompt.py`：

| 模型 | 说明 |
| --- | --- |
| `PromptMode` | 枚举：`acg`（二次元风格，仅挡暴力违法/超能力）/ `compliant`（中性专业，额外限制二次元风格），决定 moderation 规则集 |
| `PromptGenerateRequest` | 生成请求：`user_hints` + `mode` + 可选 `target_capabilities`（"不超能力"约束） |
| `PromptGenerateResponse` | 生成响应：`system_prompt` + `mode` + `moderation` + `estimate` |
| `ModerationVerdict` | 单裁判裁决：`passed` / `violated_rules` / `reasons` / `confidence`（二期多裁判投票预留）/ `mode` |
| `CostEstimate` | `prompt_tokens` / `est_completion_tokens`（一期恒 0）/ `model` |
| `ModerateRequest` / `EstimateRequest` | 独立校验 / 独立消耗估算请求 |

---

## 5. 对话引擎架构

ChatService 根据 Agent 的 `capabilities` 字段决定对话路径：

```
ChatService.stream_chat()
 │
 ├── capabilities 含 "workflow"?
 │   └── AgentWorkflow (LangGraph StateGraph)
 │       ├── load_memory → 加载会话历史
 │       ├── retrieve    → RAG 检索（如启用 rag 能力）
 │       └── generate    → LLM 流式生成
 │
 ├── capabilities 含 "tool_use" 且有 tool_ids?
 │   └── LLM.bind_tools(tools) → 工具调用流式输出
 │
 └── 其他
     └── 纯 LLM 对话流式输出
```

### 5.1 SSE 事件格式

所有流式响应使用 SSE 协议，事件类型：

| type       | 用途                          |
| ---------- | ----------------------------- |
| content    | LLM 生成的文本片段            |
| tool_call  | 工具调用事件（名称 + 参数）   |
| tool_result | 工具执行结果               |
| thinking   | 思考过程（预留）              |
| error      | 错误信息（code + message）    |
| done       | 流结束（含 token 用量统计）   |

---

## 6. RAG 管道

```
文档上传 → 文件解析 → 文本分块 → ChromaDB 向量化存储
                                    ↓
用户提问 → Embedding 查询 → ChromaDB 相似度检索 → 拼接上下文 → LLM 生成
```

- 文件类型支持：`.txt` `.md` `.pdf` `.docx`
- 分块策略：`RecursiveCharacterTextSplitter`，默认 500 字符/块，50 字符重叠
- ChromaDB 使用 cosine 距离
- 检索时按知识库 ID 查询对应 collection，取 top_k 条结果

---

## 7. 存储架构

| 数据类型   | 存储方式                         | 路径/命名规则                  |
| ---------- | -------------------------------- | ----------------------------- |
| Agent 配置 | JSON 文件                        | `data/agents/{id}.json`       |
| 知识库元数据 | JSON 文件                      | `data/knowledge_bases/{id}.json` |
| 文档元数据 | JSON 文件                        | `data/documents/{kb_id}/{id}.json` |
| 工具配置   | JSON 文件                        | `data/tools/{id}.json`        |
| 向量数据   | ChromaDB PersistentClient        | `data/chroma/chroma.sqlite3`  |
| 对话记忆   | ChromaDB Collection              | `memory_conv_{conversation_id}` |
| 上传文件   | 文件系统                         | `data/uploads/{kb_id}/{doc_id}_{filename}` |
| 用户偏好   | ChromaDB Collection              | `user_preferences`（cosine；document=生成的 system_prompt，metadata=user_id/mode/hint_tags/created_at） |

---

## 8. 部署架构

### 8.1 单机部署（当前）

```
Docker Container (Python 3.11-slim)
 ├── Uvicorn (port 8100)
 ├── FastAPI Application
 ├── ChromaDB (本地持久化)
 └── JSON 文件存储 (data/)
```

### 8.2 环境配置

通过环境变量或 `.env` 文件配置，前缀 `ACG_AI_`：

| 变量                | 默认值        | 说明               |
| ------------------- | ------------- | ------------------ |
| ACG_AI_HOST         | 0.0.0.0      | 监听地址           |
| ACG_AI_PORT         | 8100          | 监听端口           |
| ACG_AI_API_KEY      | dev-api-key   | API 认证密钥；启动时若仍为默认值会打印告警，生产环境须通过 `.env`/环境变量覆盖（已 gitignore，不入库） |
| ACG_AI_DATA_DIR     | ./data        | 数据目录           |
| ACG_AI_LOG_LEVEL    | INFO          | 日志级别           |
| ACG_AI_DEBUG        | false         | 调试模式           |
| ACG_AI_META_LLM_PROVIDER / MODEL / BASE_URL / API_KEY | deepseek / deepseek-chat / https://api.deepseek.com/v1 / （空） | meta-LLM：提示词生成 `generate` / 合规校验 `moderate` 使用；`API_KEY` 缺失返回 500 |
| ACG_AI_LLM_KEY_<PROVIDER> | （空）    | 对话/Agent LLM 按 provider 分键（`DEEPSEEK`/`ZHIPU`/`DOUBAO`/`QWEN`）；agent 自带 `llm_config.api_key` 非空时优先 |

---

## 9. API 路由总览

所有路由前缀 `/api/v1`，需携带 `X-API-Key` Header。

| 方法   | 路径                                  | 说明             |
| ------ | ------------------------------------- | ---------------- |
| GET    | /api/v1/health                        | 健康检查（无需认证） |
| GET    | /api/v1/agents                        | 列出所有 Agent   |
| GET    | /api/v1/agents/{agent_id}             | 获取 Agent 详情  |
| POST   | /api/v1/agents                        | 创建 Agent       |
| PUT    | /api/v1/agents/{agent_id}             | 更新 Agent       |
| DELETE | /api/v1/agents/{agent_id}             | 删除 Agent       |
| POST   | /api/v1/chat/{agent_id}/completions   | 对话（流式/同步） |
| GET    | /api/v1/knowledge-bases               | 列出知识库       |
| GET    | /api/v1/knowledge-bases/{kb_id}       | 获取知识库详情   |
| POST   | /api/v1/knowledge-bases               | 创建知识库       |
| PUT    | /api/v1/knowledge-bases/{kb_id}       | 更新知识库       |
| DELETE | /api/v1/knowledge-bases/{kb_id}       | 删除知识库       |
| GET    | /api/v1/knowledge-bases/{kb_id}/documents | 列出文档     |
| GET    | /api/v1/knowledge-bases/{kb_id}/documents/{doc_id} | 获取文档详情 |
| POST   | /api/v1/knowledge-bases/{kb_id}/documents | 上传文档     |
| DELETE | /api/v1/knowledge-bases/{kb_id}/documents/{doc_id} | 删除文档 |
| GET    | /api/v1/tools                         | 列出所有工具     |
| GET    | /api/v1/tools/{tool_id}               | 获取工具详情     |
| POST   | /api/v1/tools                         | 创建工具         |
| DELETE | /api/v1/tools/{tool_id}               | 删除工具         |
| POST   | /api/v1/prompts/generate              | 生成系统提示词（校验不通过返回 403） |
| POST   | /api/v1/prompts/moderate              | 独立合规校验     |
| POST   | /api/v1/prompts/estimate              | 独立消耗估算     |
