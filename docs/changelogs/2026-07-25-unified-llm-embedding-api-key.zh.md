# 统一外部模型 API-key 到 .env + 接通云端 RAG embedding

> 日期：2026-07-25 | 类型：refactor（破坏性：移除 api_key 字段 + 变更 resolve_api_key 签名）+ feat（接通云端 embedding）| 关联 plan：`C:\Users\Administrator\.claude\plans\resilient-enchanting-hoare.md`

---

## 1. 背景

项目调用外部模型时 API-key 散落多处、未统一从 `.env` 取。调查发现 4 条用 key 路径中：

- meta-LLM、媒体生成：已统一到 `.env`（`ACG_AI_META_LLM_API_KEY` / `ACG_AI_GENERATION_API_KEY`）。
- **对话 / Agent LLM**：`resolve_api_key(provider, explicit)` 中 agent JSON 的 `api_key` 优先，`.env` 仅兜底。而 `LLMConfig.api_key` 是必填字段，402 个本地 agent JSON 全填占位符 `"sk-test"`（非空）→ 直接被采用 → `.env` 的 `ACG_AI_LLM_KEY_*` 形同虚设。
- **RAG embedding**：`EmbeddingConfig.api_key` 喂给一个**构造了却从不调用**的 `OpenAIEmbeddings`（死代码）；入库/检索实际走 ChromaDB 本地 MiniLM，没有活的 embedding key。

本次：移除 `LLMConfig.api_key` 与 `EmbeddingConfig.api_key`，对话 LLM 与 RAG embedding 的 key 一律按 provider 从 `.env` 取（`ACG_AI_LLM_KEY_<PROVIDER>`，chat 与 embedding 共用同一 key）；接通云端 embedding（入库 `embed_documents` + 检索 `embed_query`），默认走智谱 `embedding-3`。

## 2. 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/models/agent.py` | `LLMConfig` 删 `api_key` 字段 |
| `app/models/knowledge_base.py` | `EmbeddingConfig` 删 `api_key` 字段；默认 `provider=zhipu` / `model=embedding-3`（原 dashscope/text-embedding-v3） |
| `app/config.py` | `llm_key_*` 注释更新：明确 chat+embedding 共用同一 provider key |
| `app/core/llm.py` | `resolve_api_key(provider)`：删 `explicit` 形参，只从 settings 取；`create_chat_model`/`ping_llm` 调用点同步；错误文案去掉 `llm_config.api_key` 引用 |
| `app/api/v1/chat.py` | 预检 `resolve_api_key(agent_config.llm_config.provider)` |
| `app/core/embeddings.py`（新） | `resolve_embedding_key`（复用 `resolve_api_key`）+ `build_embeddings`（base_url 为空时按 provider 取默认 OpenAI 兼容端点）+ `_EMBEDDING_BASE_URL_DEFAULTS`（zhipu/qwen/doubao，provider 名与 `llm_key_*` 字段对齐） |
| `app/core/retriever.py` | `__init__` 用 `build_embeddings`；`retrieve` 改 `embed_query` + `col.query(query_embeddings=...)`（让 `self.embedding` 真正生效） |
| `app/services/document_service.py` | 入库分块后 `build_embeddings(...).embed_documents(chunks)`，`col.add` 传 `embeddings`（空 chunks 不调 embed） |
| `scripts/seed.py` | 删 `LLMConfig` 的 `api_key=""` |
| `.env.example` / `.env` | 更新对话 LLM 密钥段注释（去掉"agent 自带 api_key 优先"；说明 chat+embedding 共用）；不新增 embedding 专用变量 |
| `tests/test_llm.py` | 删 2 个 explicit 语义用例；3 处 `resolve_api_key` 去 explicit 参；`_ping_config` 去 api_key；新增 `deepseek_key` fixture 让 ping 测试不依赖 .env |
| `tests/test_embeddings.py`（新） | 10 测试：resolve_embedding_key 命中/未命中/大小写；build_embeddings 默认 base_url/显式覆盖/qwen 走 dashscope 端点/未知 provider 回退空/缺 key 抛错；默认配置锁定 zhipu+embedding-3、无 api_key 字段 |
| 其余 8 个测试文件 | 死代码清理：删 `LLMConfig(api_key=...)` / dict 里 `"api_key"` 项（pydantic extra=ignore 本不阻塞，清理避免误导）；`test_chat.py` 两个 qwen 图生文测试补 `monkeypatch llm_key_qwen` 以保持原意图（预检通过聚焦图片路径） |

## 3. 设计要点

- **.env 布局：每家 provider 一个变量**（`ACG_AI_LLM_KEY_<PROVIDER>`），保留 `extra="forbid"` 的 fail-loud；新增 provider = Settings 加一个字段 + .env 加一行（已与用户确认，未采用 JSON dict 零代码扩展方案）。
- **embedding 复用 LLM key**：智谱/通义(qwen)/火山 的 chat 与 embedding 共用同一个 API key（均有对应 `llm_key_*` 字段），故 embedding 不单独配 key，直接 `resolve_embedding_key → resolve_api_key → settings.llm_key_for`。embedding 的 provider 名与 chat 对齐（qwen 走 dashscope 兼容端点，复用 `ACG_AI_LLM_KEY_QWEN`）；deepseek 无 embedding 服务、openai 未配 key 字段，故不在默认端点表。用户已配智谱 key，对话与 RAG 共用即可。
- **接通云端 embedding**：入库（`document_service`）与检索（`retriever`）都用 `OpenAIEmbeddings`（provider/model/base_url 取自 KB 配置，key 取自 .env），向量空间一致。base_url 为空时按 provider 取默认端点，开箱即用。
- **默认走智谱 embedding-3**：用户选定智谱，`EmbeddingConfig` 默认 `provider=zhipu` / `model=embedding-3` / base_url `https://open.bigmodel.cn/api/paas/v4/`（末尾 `/`，OpenAI 兼容）；可按 KB 覆盖。
- **旧数据零迁移**：`LLMConfig`/`EmbeddingConfig` 未设 `model_config`，pydantic v2 默认 `extra="ignore"` → 402 个旧 agent JSON 与 KB JSON 里残留的 `api_key` 加载时静默丢弃，无需迁移。

## 4. 验证

- 全量 `pytest -q` → **231 passed**（基线 223 + 新增 `test_embeddings.py` 10 个 − 删 `test_llm` 2 个 explicit 语义用例），无回归。
- 静态确认：`grep app/` 再无 `config.api_key` / `embedding_config.api_key` 读取，外部模型 key 全部经 `resolve_api_key`（LLM）/ `resolve_embedding_key`（embedding）从 settings 取。
- Pyright：新模块 `app/core/embeddings` 首次引用时短暂报 import 未解析（索引延迟），运行时无碍；既有 `max_tokens`/`_env_file`/`metadatas` 等类型 hint 误报保持不动（非本次引入）。

## 5. 范围（未做 / 二期 / 迁移提示）

- **破坏性**：`LLMConfig.api_key` / `EmbeddingConfig.api_key` 字段移除、`resolve_api_key` 签名变更。前端/调用方再传 `api_key` 会被 pydantic 静默忽略（不报 422）；agent CRUD 与 KB 路由响应体不再回显 `api_key`（顺手修掉既有泄露）。
- **迁移提示（重要）**：现有 KB 是用 ChromaDB 默认本地 MiniLM（384 维）索引的，切到云端 embedding（如智谱 embedding-3，2048 维）后向量维度不兼容——对旧 collection 执行 `col.add(embeddings=...)` 会失败并把文档标为 `failed`。升级前需清空 `data/chroma/`（或删除对应 KB collection）并重新上传文档，否则检索失效。
- meta-LLM、媒体生成 key 已统一，本次不动。
- `base_url`/`model` 仍保留在 per-entity 配置（非密钥）；仅 embedding 在 base_url 为空时按 provider 给默认值。
- 入库 embedding 路径（`_process_document`）当前无单测覆盖（`test_document_processing.py` 只覆盖解析/分块）；`build_embeddings`/`resolve_embedding_key` 已补单测，端到端入库待手动验证。
