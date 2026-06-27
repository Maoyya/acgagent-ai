# 图生文（Image-to-Text）接入 Agent 对话链路 — 设计文档

- 日期：2026-06-28
- 分支：aiagent_dev
- 状态：已与用户确认设计，待出实施计划

## 1. 背景与目标

当前项目所有模型调用走 OpenAI 兼容协议（`langchain_openai.ChatOpenAI`），对话链路只处理纯文本
`HumanMessage(content=str)`。需要把「图生文」能力接入现有链路：创建 Agent（其 `llm_config` 配置一个
视觉模型），然后在与 Agent 对话时上传图片，模型看图生成文字。

目标：
- 用户上传原始图片文件 → 服务端存盘 → 返回可引用的 URL → 对话请求携带图片 URL → 模型看图回答。
- 不绑死具体 provider/模型（通义 qwen-vl / 豆包 / 智谱 glm-4v 等 OpenAI 兼容视觉模型均可）。
- 复用现有对话链路（`chat` 与 `tool_use` 两种 capability），不动 Agent 模型结构。

## 2. 关键决策（与用户逐项确认）

| # | 决策点 | 选择 | 理由 |
| --- | --- | --- | --- |
| ① | 图片如何交给云端视觉模型 | **发送时读本地文件转 base64 data URL 内联** | 云端模型（厂商服务器）无法访问本机/内网 URL；本地开发阶段只有 base64 稳。DB 里仍存 URL 作为引用。 |
| ② | 存储 URL/根目录配置方式 | **复用现有 `.env` + pydantic-settings**（放弃 yml） | 项目纯 `.env`、`extra="forbid"`；引入 yml 是新模式（需 PyYAML）。遵循一致性 > 引入新约定（Rule 7/11）。 |
| ③ | 历史图片轮次是否在后续轮次重发 | **仅当前轮有效**；memory 只存用户文字，图片不入记忆 | 重发历史图会导致 token 爆炸；图生文多为单轮场景。省 token、实现简单。后续轮次拿不到历史图是预期行为。 |
| ④ | 哪些 Agent 可收图 | **所有 Agent 透传**，不加 vision capability 标志；图片输入**完全可选** | 最简、最「通用」。`images` 默认空 = 纯文本对话逐字一致（零回归）。是否真能看图取决于用户配的模型：配视觉模型可用，配纯文本模型由 provider 报错透出。 |
| ⑤ | 上传流程形状 | **独立上传端点 + ChatRequest 携带图片 URL** | 仿现有 `document.py` 上传模式；「DB 存 URL」天然成立；SSE 流式对话接口保持 JSON 不变；解耦可复用。 |
| ⑥ | 本地存储目录位置 | **D 盘绝对路径**（默认 `D:/acgagent-ai/uploads`） | 脱离项目目录，避免大文件污染 git 树；可用 `.env` 覆盖。 |

## 3. 架构与组件

### 3.1 新增 `app/services/image_service.py`（图片唯一职责，单一真相源）

```
class ImageRef(BaseModel):          # 上传返回结构
    url: str                         # storage_base_url + 文件名，存入「DB/对话引用」
    filename: str                    # 落盘文件名（uuid + 原扩展名）

def save_upload(filename, content: bytes, content_type: str) -> ImageRef
    # 校验 content_type 以 image/ 开头；校验大小上限；
    # 生成 <uuid>.<ext> 文件名；mkdir(storage_root_dir, parents=True, exist_ok=True)；
    # 写入 storage_root_dir/<uuid>.<ext>；返回 ImageRef(url=base_url+"/"+name, filename=name)

def to_data_urls(urls: list[str]) -> list[str]
    # 对每个 url：取 basename → 读 storage_root_dir/basename 字节 →
    # 拼 "data:<mime>;base64,<b64>"。文件缺失抛错（Fail Loud，不静默跳过）。

def build_message_content(text: str, image_urls: list[str]) -> str | list
    # image_urls 为空 → 返回原 text（保持现状，零侵入）；
    # 非空 → 返回多模态 content list：
    #   [{"type":"text","text":text},
    #    *({"type":"image_url","image_url":{"url":<data_url>}} for each image)]
```

mime 类型由文件扩展名推断（无扩展名或未知默认 `image/jpeg`）。

### 3.2 `app/config.py`：新增两个 Settings 字段（②，前缀 `ACG_AI_`）

```python
storage_root_dir: Path = Path("D:/acgagent-ai/uploads")   # 对应 ACG_AI_STORAGE_ROOT_DIR
storage_base_url: str = "http://localhost:8100/uploads"   # 对应 ACG_AI_STORAGE_BASE_URL
```

> 说明：`storage_root_dir` 是物理落盘位置；`storage_base_url` 是对外/DB 引用的 URL 前缀。二者逻辑对应，
> 但因①选 base64 内联，模型并不真的通过 HTTP 拉图——`base_url` 仅作为「DB 存的 URL」与前端引用。
> `image_service.save_upload` 自行 `mkdir` 确保目录存在，不依赖 `main.py` lifespan。
>
> **两者均为示例默认值，完全可由 `.env` 覆盖**（`ACG_AI_STORAGE_ROOT_DIR` / `ACG_AI_STORAGE_BASE_URL`），
> 并写入 `.env.example` 作为可配置项公示，不锁死。生产环境按实际部署改 `.env` 即可。

### 3.3 `app/services/chat_service.py`：透传 images 到 `_build_messages`

- `stream_chat` / `sync_chat` 新增参数 `images: list[str] | None = None`，透传到 `_build_messages`。
- `_build_messages` 末尾由
  `HumanMessage(content=message)` 改为
  `HumanMessage(content=image_service.build_message_content(message, images or []))`。
  - 无图时 `build_message_content` 返回纯字符串，行为与现状完全一致（零回归）。
- `memory.save_user_message(conversation_id, message)` 仍只存用户文字；**图片不入记忆**（决策③，单轮）。后续轮次拿不到历史图是预期行为，非缺陷。

### 3.4 `app/api/v1/chat.py` + `app/models/chat.py`

- `ChatRequest` 新增 `images: list[str] = []`。
- 新增端点 `POST /api/v1/chat/images`（multipart，`UploadFile = File(...)`，需 `X-API-Key`）：
  读 bytes → `image_service.save_upload` → `Result.success(data=ImageRef)`。仿 `document.py` 风格。
- 现有 `POST /chat/{agent_id}/completions` 把 `body.images` 透传给 `chat_service.stream_chat / sync_chat`。

## 4. 数据流

```
前端                         后端                                   视觉模型(云端)
 │                                                                  │
 │─ POST /chat/images (raw file, X-API-Key) ──► image_service 存盘  │
 │ ◄──── {url:"…/uploads/<uuid>.png"} ──────                        │
 │                                                                  │
 │─ POST /chat/{id}/completions ──► chat_service                    │
 │   {message, images:[url], stream}      │ save_user_message(文字) │
 │                                         │ _build_messages:        │
 │                                         │   build_message_content │
 │                                         │   → 读盘→base64         │
 │                                         │   → HumanMessage(list)  │
 │                                         ├── (多模态) ────────────►│ 看图→生成文字
 │ ◄──── SSE 文本流 / JSON ────────────────│                        │
```

## 5. 通用性（不绑死模型）

完全不碰 provider/model 字段。Agent 创建时由用户在 `llm_config.model` 填写视觉模型名
（如 `qwen-vl-max` / `doubao-1.5-vision-pro` / `glm-4v`），并填对应 provider 的 OpenAI 兼容 `base_url`。
本特性只负责把标准 OpenAI 多模态 content 透传——`ChatOpenAI` 原生支持，无需新 SDK。
支持多张图（`images` 为 list，生成多个 `image_url` 内容块）。

### 5.1 图生文是「可选能力」，不假设模型支持（用户反馈）

配置的模型**不一定**支持图生文，因此本特性把图片输入做成**完全可选**，系统层面不假设、不保证每个模型都能看图：

- `ChatRequest.images` 默认为空；为空时 `build_message_content` 返回纯字符串，对话行为与现状逐字一致（**零回归**）。
- **能否真完成图生文，取决于用户创建 Agent 时在 `llm_config.model` 配置的模型本身是否具备视觉能力**——这是用户的责任。
- 若给纯文本模型发了图，由 provider 报错透出（见 §6），系统不做跨厂商的「是否支持图片」探测。
- 产品/前端层面应把「图生文」呈现为依赖模型的可选能力，而非所有 Agent 的标配。

与决策④一致：不加 vision capability 标志，纯透传。

## 6. 错误处理（Fail Loud，Rule 12）

- 上传非图片（`content_type` 不以 `image/` 开头）→ 400 拒绝，可操作提示。
- 上传超大小上限 → 400 拒绝（上限为模块常量，本轮不做成配置项，YAGNI）。
- 发送时文件已被删（上传后、对话前被清理）→ `to_data_urls` 抛错 →
  流式路径产出 `error` 事件 / 同步路径 500 信封，**不静默跳过**。
- 纯文本模型收到图 → provider 报错，沿用 `chat_service` 现有 `try/except` 透出。
  （跨厂商可靠识别「不支持图片」不可行，不过度工程。）
- 上传端点遵循现有 `X-API-Key` 认证（与其它 v1 端点一致）。

## 7. 范围与非目标

- **workflow/RAG 路径不支持图**：`workflow.stream_workflow` 自建消息、不走 `_build_messages`
  （`chat_service.py:41-46`）；图 + RAG 混合更复杂，本轮 YAGNI。覆盖 `chat` + `tool_use` 两种 capability。
- **不挂 StaticFiles 公网服务**：base64 方案无需模型拉图。前端预览图如需要，后续可选挂载。
- **不加 vision capability 标志**（④所有 Agent 透传）。
- **不改 Agent 模型结构**（`AgentConfig` / `LLMConfig` 不动）。

## 8. 测试策略（验证意图，Rule 9）

- `image_service`：
  - `save_upload` 真的写文件到 `storage_root_dir` 并返回 `url=base_url+name`；
  - 非 `image/*` mime 被拒（验证「只接受图片」的业务意图）；
  - `to_data_urls` 把文件字节编成合法 `data:<mime>;base64,...`；
  - 文件缺失时 `to_data_urls` 抛错而非返回空（验证 Fail Loud）；
  - `build_message_content`：无图返回 `str`（零回归）、有图返回含 1 个 text + N 个 image_url 的 list。
- `chat_service`：
  - 带图时 `_build_messages` 产出多模态 `HumanMessage`、不带图保持纯字符串；
  - `save_user_message` 只存文字、不含图片字节（验证「历史轮不重发图」）。
- API：
  - 上传端点返回 `url`；非图被拒；
  - 对话端点把 `images` 透传到 service（LLM 打桩，断言传给 `build_message_content` 的图片列表）。

## 9. 实施顺序（概要，详细步骤由 writing-plans 展开）

1. `config.py` 加两个 storage 字段 + `.env.example` 补例。
2. `image_service.py`（save_upload / to_data_urls / build_message_content）+ 单测。
3. `chat_service.py` 透传 images + `_build_messages` 改造 + 单测。
4. `chat.py` 上传端点 + `ChatRequest.images` + 对话端点透传 + API 测试。
5. 路由注册 + 手动联调（配一个视觉模型 Agent，上传图 → 对话）。
6. 改动后跑 `/code-review`（项目规矩），再提交（中文 commit message）。
