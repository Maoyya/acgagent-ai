# acgagent-ai 业务流程文档

> 版本：1.1.0 | 更新日期：2026-06-21

---

## 1. 文档概述

本文档描述 acgagent-ai 系统中各核心业务流程，包括参与角色、触发条件、处理步骤和异常处理。适用于开发人员理解系统行为，以及产品/测试人员进行功能验证。

---

## 2. 角色定义

| 角色        | 说明                                          |
| ----------- | --------------------------------------------- |
| 调用方      | 前端应用或第三方系统，通过 REST API 调用服务  |
| 系统        | acgagent-ai 后端服务                          |
| LLM 服务    | 外部大模型 API（豆包/通义/DeepSeek 等 OpenAI 兼容接口） |
| ChromaDB    | 本地向量数据库，存储知识库 chunks 和对话记忆  |

---

## 3. 核心业务流程

### 3.1 Agent 管理流程

Agent 是系统的核心实体，定义了 AI 助手的人格、模型、能力和关联资源。

#### 3.1.1 创建 Agent

```
调用方                          系统
  │                              │
  │  POST /api/v1/agents         │
  │  {name, llm_config, ...}     │
  │ ──────────────────────────>  │
  │                              │  1. 校验请求参数
  │                              │  2. 生成唯一 ID (12位 hex)
  │                              │  3. 构建 AgentConfig 对象
  │                              │  4. 保存到 data/agents/{id}.json
  │                              │
  │  {code:200, data: AgentConfig}
  │ <──────────────────────────  │
```

**请求参数（AgentCreateRequest）：**

| 字段              | 必填 | 默认值                     | 说明                        |
| ----------------- | ---- | -------------------------- | --------------------------- |
| name              | 是   | -                          | Agent 名称                  |
| description       | 否   | null                       | 描述                        |
| system_prompt     | 否   | null                       | 系统提示词                  |
| llm_config        | 是   | -                          | 模型配置（provider/model/base_url/api_key） |
| memory_config     | 否   | conversation_window/8000   | 记忆配置                    |
| capabilities      | 否   | ["chat"]                   | 能力标签                    |
| knowledge_base_ids | 否  | []                         | 关联知识库 ID 列表          |
| tool_ids          | 否   | []                         | 关联工具 ID 列表            |

#### 3.1.2 更新 Agent

调用方提交部分更新字段（`AgentUpdateRequest`），系统合并到已有配置，更新 `updated_at` 时间戳后保存。

#### 3.1.3 删除 Agent

系统删除 `data/agents/{id}.json`。注意：不会自动清理关联的对话记忆。

---

### 3.2 对话流程（核心流程）

对话是系统最核心的业务流程，支持流式和同步两种模式。

#### 3.2.1 整体流程

```
调用方                        ChatService                     LLM / ChromaDB
  │                              │                                │
  │  POST /chat/{agent_id}       │                                │
  │  /completions                │                                │
  │  {message, conversation_id,  │                                │
  │   stream: true}              │                                │
  │ ──────────────────────────>  │                                │
  │                              │                                │
  │                              │  1. 加载 Agent 配置             │
  │                              │  2. 校验 Agent 状态 (status=1)  │
  │                              │                                │
  │                              │  [路由决策]                     │
  │                              │  ─ capabilities 含 "workflow"?  │
  │                              │    → 走 LangGraph 工作流        │
  │                              │  ─ capabilities 含 "tool_use"   │
  │                              │    且有 tool_ids?               │
  │                              │    → 走工具调用模式              │
  │                              │  ─ 否则 → 走纯聊天模式          │
  │                              │                                │
  │  SSE: data: {"type":"content","content":"..."}               │
  │ <──────────────────────────────────────────────────────────  │
  │  SSE: data: {"type":"content","content":"..."}               │
  │ <──────────────────────────────────────────────────────────  │
  │  ...                                                         │
  │  SSE: data: {"type":"done","usage":{...}}                    │
  │ <──────────────────────────────────────────────────────────  │
```

#### 3.2.2 路由决策详解

**路径 A — 纯聊天模式**

最简路径，无工具、无 RAG：
1. 保存用户消息到对话记忆
2. 构建 Messages：System Prompt → 历史消息 → 当前用户消息
3. 调用 LLM 流式生成
4. 逐块通过 SSE 返回 `content` 事件
5. 保存助手回复到对话记忆
6. 返回 `done` 事件

**路径 B — 工具调用模式**

Agent 启用 `tool_use` 能力且配置了 `tool_ids`：
1. 保存用户消息到对话记忆
2. 实例化对应工具（calculator / web_search / knowledge_search）
3. 将工具绑定到 LLM（`llm.bind_tools()`）
4. 构建消息后流式调用 LLM
5. LLM 生成过程中：
   - 文本内容 → 发送 `content` 事件
   - 工具调用 → 发送 `tool_call` 事件（含工具名和参数）
6. 保存助手回复到记忆
7. 返回 `done` 事件

**路径 C — LangGraph 工作流模式**

Agent 启用 `workflow` 能力：
1. 构建 LangGraph StateGraph
2. 执行节点：
   - `load_memory`：从 ChromaDB 加载会话历史
   - `retrieve`（可选）：如启用 `rag` 且有知识库，执行 RAG 检索
   - `generate`：最终生成（预留扩展节点）
3. 图执行完成后，用完整上下文流式调用 LLM
4. SSE 逐步返回生成内容
5. 保存回复到记忆

#### 3.2.3 对话记忆管理

```
ConversationMemory
 │
 ├── type = "none"          → 不读写任何记忆
 ├── type = "conversation_window" → 滑动窗口策略
 │     1. 从 ChromaDB 加载历史消息
 │     2. 从最新消息开始向前累加 token 数
 │     3. 超过 max_tokens (默认 8000) 的早期消息被丢弃
 │     4. 返回裁剪后的消息列表
 └── type = "summary"       → 预留，尚未实现
```

**记忆存储位置：** ChromaDB collection `memory_conv_{conversation_id}`
**每条消息包含：** role（user/assistant）、content、timestamp、token_count

---

### 3.3 RAG 知识库流程

#### 3.3.1 创建知识库

```
调用方                          系统
  │                              │
  │  POST /api/v1/knowledge-bases│
  │  {name, embedding_config,   │
  │   chunk_config}              │
  │ ──────────────────────────>  │
  │                              │  1. 生成唯一 ID
  │                              │  2. 保存元数据到 JSON 文件
  │                              │  （ChromaDB collection 延迟创建）
  │  {code:200, data: KnowledgeBase}
  │ <──────────────────────────  │
```

**Embedding 配置：** 支持 dashscope / openai 提供商，默认 `text-embedding-v3` 模型。
**分块配置：** 默认 500 字符/块，50 字符重叠，分隔符优先级 `["\n\n", "\n", "。", " "]`。

#### 3.3.2 上传文档

```
调用方                      DocumentService                 ChromaDB
  │                              │                            │
  │  POST /kb/{id}/documents     │                            │
  │  (multipart file upload)     │                            │
  │ ──────────────────────────>  │                            │
  │                              │                            │
  │                              │  1. 校验知识库存在          │
  │                              │  2. 生成 doc_id            │
  │                              │  3. 保存原始文件到 uploads/ │
  │                              │  4. 创建 DocumentVO        │
  │                              │     (status="processing")  │
  │                              │  5. 保存元数据              │
  │                              │  6. 立即返回响应给调用方    │
  │  {data: DocumentVO}          │                            │
  │ <──────────────────────────  │                            │
  │                              │                            │
  │                    [异步处理] │                            │
  │                              │  7. 解析文件内容            │
  │                              │     (txt/md/pdf/docx)      │
  │                              │  8. 文本分块                │
  │                              │  9. 写入 ChromaDB           │
  │                              │     collection: kb_{id}_chunks
  │                              │                            │
  │                              │  10. 更新文档状态为         │
  │                              │      "completed"           │
  │                              │  11. 更新知识库统计         │
  │                              │      (document_count,      │
  │                              │       chunk_count)         │
  │                              │                            │
  │                    [异常时]   │                            │
  │                              │  status → "failed"         │
  │                              │  error_message → 异常信息   │
```

**关键设计：** 文档上传后立即返回，处理过程异步执行。调用方可通过查询文档列表来轮询处理状态。

**支持的文件类型：**

| 类型   | 扩展名         | 解析方式                     |
| ------ | -------------- | ---------------------------- |
| 纯文本 | .txt, .md      | 直接读取 UTF-8               |
| PDF    | .pdf           | pypdf PdfReader 逐页提取     |
| Word   | .docx          | python-docx 段落文本提取     |

#### 3.3.3 RAG 检索流程（对话中触发）

当 Agent 配置了 `rag` 能力且关联了知识库时，对话流程中会自动执行检索：

```
用户提问 "什么是深度学习？"
        │
        ▼
RAGRetriever.retrieve(query, knowledge_base_ids)
        │
        ├── 对每个 kb_id：
        │     1. 获取 ChromaDB collection: kb_{id}_chunks
        │     2. col.query(query_texts=[query], n_results=top_k)
        │     3. 返回匹配的文档片段
        │
        ▼
拼接 RAG 上下文：
"基于以下参考资料回答用户问题。如果资料中没有相关信息，请说明。

参考资料：
{chunk_1}
---
{chunk_2}
---
..."
        │
        ▼
将 RAG 上下文作为 SystemMessage 注入到 LLM 对话中
```

#### 3.3.4 删除文档

1. 从 ChromaDB 中删除该文档的所有 chunks（`col.delete(where={"doc_id": doc_id})`）
2. 更新知识库统计（document_count - 1, chunk_count - doc.chunk_count）
3. 删除文档元数据

#### 3.3.5 删除知识库

1. 删除整个 ChromaDB collection（`kb_{id}_chunks`）
2. 删除知识库元数据 JSON 文件

---

### 3.4 工具管理流程

#### 3.4.1 工具类型

| 类型   | 说明                                        | 存储             |
| ------ | ------------------------------------------- | ---------------- |
| builtin | 内置工具，硬编码在 ToolService 中           | 无持久化         |
| api    | 自定义 API 工具，用户通过接口注册            | data/tools/{id}.json |

**内置工具（3个）：**

| ID                | 名称         | 描述               | 参数         |
| ----------------- | ------------ | ------------------ | ------------ |
| calculator        | 计算器       | 计算数学表达式     | expression   |
| web_search        | 网络搜索     | 搜索互联网信息     | query        |
| knowledge_search  | 知识库搜索   | 在知识库中检索     | query        |

#### 3.4.2 创建自定义工具

```
调用方                          系统
  │                              │
  │  POST /api/v1/tools          │
  │  {name, description,         │
  │   type: "api",               │
  │   config: {url, method,      │
  │            headers, ...},    │
  │   parameters: {properties,   │
  │                required}}    │
  │ ──────────────────────────>  │
  │                              │  1. 生成唯一 ID
  │                              │  2. 构建 ToolVO
  │                              │  3. 保存到 data/tools/{id}.json
  │  {data: ToolVO}              │
  │ <──────────────────────────  │
```

#### 3.4.3 工具在对话中的使用

1. Agent 配置中 `tool_ids` 包含工具 ID
2. Agent `capabilities` 包含 `"tool_use"`
3. ChatService 将对应工具实例化为 LangChain Tool
4. 通过 `llm.bind_tools()` 将工具注册到 LLM
5. LLM 自主决定是否调用工具，返回 `tool_call` 事件

---

### 3.5 健康检查流程

```
GET /api/v1/health（无需 API Key）
        │
        ├── 尝试 chroma.heartbeat() → "connected" / "not_initialized"
        │
        └── 返回 {status, version, chroma, llm}
```

---

## 4. 异常处理策略

| 场景                  | 处理方式                                         |
| --------------------- | ------------------------------------------------ |
| Agent 不存在          | 返回 `Result.error(code=404)`                    |
| Agent 已禁用          | 返回 `Result.error(code=400)`                    |
| API Key 缺失或无效    | HTTP 401（缺失/空 key 或比对不符均返回 401，比对采用常数时间 `secrets.compare_digest`） |
| 知识库不存在          | 返回 `Result.error(code=404)`                    |
| 文档处理失败          | DocumentVO.status → "failed"，记录 error_message |
| LLM 调用异常          | SSE 发送 `error` 事件（code=500）                 |
| RAG 检索失败          | 降级为空上下文，继续生成                          |
| ChromaDB 连接失败     | 健康检查返回 "not_initialized"                    |
| 不支持的文件类型      | 文档处理失败，记录错误信息                        |

---

## 5. 典型端到端场景

### 5.1 场景：带知识库的客服 Agent

```
前置准备：
  1. 创建知识库 → 上传产品手册 PDF → 等待处理完成
  2. 创建 Agent，配置：
     - llm_config: {provider: "doubao", model: "..."}
     - capabilities: ["chat", "rag", "workflow"]
     - knowledge_base_ids: ["<kb_id>"]
     - system_prompt: "你是产品客服助手..."

用户对话：
  用户: "这个产品怎么退货？"
    → AgentWorkflow 触发
    → load_memory: 加载历史（如有）
    → retrieve: 从知识库检索"退货"相关片段
    → 拼接 RAG 上下文
    → LLM 基于参考资料生成回答
    → SSE 流式返回
    → 保存对话记忆
```

### 5.2 场景：带工具的分析 Agent

```
前置准备：
  1. 创建 Agent，配置：
     - capabilities: ["chat", "tool_use"]
     - tool_ids: ["calculator"]
     - system_prompt: "你是数据分析助手..."

用户对话：
  用户: "帮我算一下 123 * 456 + 789"
    → ChatService 检测到 tool_use 能力
    → 绑定 CalculatorTool 到 LLM
    → LLM 决定调用 calculator 工具
    → SSE 返回 tool_call 事件
    → 工具执行并返回结果
    → LLM 继续生成最终回答
```

---

## 6. 配置项速查

| 配置           | 位置               | 默认值                          | 说明               |
| -------------- | ------------------ | ------------------------------- | ------------------ |
| 服务端口       | ACG_AI_PORT        | 8100                            | Uvicorn 监听端口   |
| API Key        | ACG_AI_API_KEY     | dev-api-key                     | 接口认证密钥；启动时若仍为默认值会打印告警，生产环境须通过 `.env`/环境变量覆盖 |
| 数据目录       | ACG_AI_DATA_DIR    | ./data                          | 所有持久化数据     |
| 记忆窗口       | Agent.memory_config | 8000 tokens                    | 单会话上下文上限   |
| 分块大小       | KB.chunk_config    | 500 字符                        | 文档切分粒度       |
| 分块重叠       | KB.chunk_config    | 50 字符                         | 相邻块重叠         |
| RAG top_k      | 硬编码             | 5                               | 每次检索返回条数   |
| LLM 温度       | Agent.llm_config   | 0.7                             | 生成随机性         |
| LLM max_tokens | Agent.llm_config   | 4096                            | 单次最大输出 token |
