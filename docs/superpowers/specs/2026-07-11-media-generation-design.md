# 媒体生成能力（文生图 + 图生视频）— 设计文档（Spec）

> 版本：1.0.0 | 日期：2026-07-11 | 所属项目：acgagent-ai
> 状态：待评审 → 通过后进入 writing-plans

---

## 1. 目标与背景

为 acgagent-ai 新增「媒体生成」能力：**文生图**（text→image）与 **图生视频**（image+prompt→video）。

此前项目只有**图生文**（多模态视觉输入：`/chat/images` 上传图片 → 视觉模型读图），**没有任何生成能力**（grep `dall/wanx/kling/sora/tts/video` 零命中，`config.py` 无生成配置，路由无生成端点）。本 spec 从 0 建立生成子系统。

> 注：已配置的 provider（豆包/通义/智谱）虽自带生成模型，但项目此前只用了其 OpenAI 兼容 chat 接口。生成是**全新集成**，不复用 `create_chat_model`。

### 1.1 关键边界决策（已与用户确认）

| # | 决策 | 选择 |
|---|---|---|
| 1 | 模态范围 | **文生图 + 图生视频**（文生视频 / TTS 不在本期） |
| 2 | 暴露方式 | **独立 HTTP 端点**（与 prompt 端点同一模式），生成与对话解耦 |
| 3 | 异步模式 | **提交+轮询**：POST 返 `task_id`（HTTP 200 + `Result` 信封，与现有 API 一致），Java 轮询 `GET /tasks/{id}` |
| 4 | Provider | **通义万相（dashscope）**，MVP 单家 |
| 5 | 轮询架构 | **无状态即时轮询**：`GET` 实际查 dashscope，完成即下载资产 |
| 6 | 图生视频输入图 | 要求 Java 传**公网可达** `image_url`（本地图 dashscope 拉不到；本地代理上传留二期） |
| 7 | 内容审核 | MVP **依赖 dashscope 内置审核**，不引入自定义 gen-moderation |
| 8 | 默认模型 | 文生图 `wanx2.1-t2i-turbo`；图生视频 `wan2.1-i2v-turbo`（后续可改） |

---

## 2. 范围

### 2.1 一期范围（本 spec 覆盖，Python 侧）

1. **文生图**：提交 + 轮询 + 资产下载
2. **图生视频**：提交 + 轮询 + 资产下载
3. **任务持久化**（JSON，与现有 KB/agent/tool 一致）
4. **dashscope 异步任务 HTTP 客户端**
5. **内容审核**：透传 dashscope 内置审核结果

### 2.2 二期范围（留接口/钩子，不实现）

- 对话内工具调用生成（依赖工具调用回路修复）
- 多 provider 抽象
- 自定义内容审核 / ACG-compliant mode 适配
- 文生视频、TTS
- 本地图代理上传到 dashscope（解决输入图可达性的另一条路）
- 配额/计费、任务过期兜底清理、产物 URL 过期兜底下载

### 2.3 明确不在本 spec 范围

- 前端轮询 UI、Java 业务编排 —— **Java 侧**
- 公网图存储/OSS —— Java 负责 `image_url` 可达性

---

## 3. 架构

### 3.1 分层（严格沿用现有项目结构）

```
API      app/api/v1/generation.py         （新；复用 verify_api_key + Result<T>）
Service  app/services/generation_service.py （新；编排 提交/查询/下载）
Core     app/core/dashscope_client.py     （新；dashscope 异步任务 HTTP 客户端）
Storage  app/db/generation_store.py       （新；JSON 任务表）
Models   app/models/generation.py         （新；任务/请求/响应/枚举）
Config   app/config.py                    （改；加 generation_* 字段）
Router   app/api/v1/router.py             （改；挂载 generation_router）
```

### 3.2 Java / Python 边界

```
Java acgagent                          Python acgagent-ai
  │  POST /api/v1/generations/images     │  submit → dashscope → 存 task(pending)
  │ ──────────────────────────────────>  │
  │  Result<{task_id}>（code=200）        │
  │ <──────────────────────────────────  │
  │                                       │
  │  GET /api/v1/generations/tasks/{id}   │  query dashscope；succeeded→下载资产
  │ ──────────────────────────────────>  │
  │  Result<GenerationTask>               │
  │ <──────────────────────────────────  │
```

Python 不持有业务编排，只产出「任务状态 + 资产 URL」。

### 3.3 dashscope 集成要点（异步任务模式，已核实官方文档）

- 提交：Header `X-DashScope-Async: enable` + `Authorization: Bearer {api_key}`
- 查询：`GET {base}/tasks/{provider_task_id}`
- 状态机：`PENDING → RUNNING → SUCCEEDED / FAILED`
- `SUCCEEDED` 时产物在 `output.results[].url`（图）/ `output.video_url`（视频）返回

| 项 | 文生图 | 图生视频 |
|---|---|---|
| 提交端点 | `POST /services/aigc/text2image/image-synthesis` | `POST /services/aigc/multimedia-generation/video-synthesis` |
| model | `wanx2.1-t2i-turbo` | `wan2.1-i2v-turbo`（基于首帧） |
| input | `{prompt}` | `{prompt, img_url}` |
| parameters | `{size, n}` | `{duration, resolution}` |
| 产物字段 | `output.results[0].url` | `output.video_url` |

> 端点路径与字段以 dashscope 官方文档为准（[文生图 V2](https://help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference) / [图生视频-基于首帧](https://help.aliyun.com/zh/model-studio/legacy-image-to-video-api-reference/)）；实现时核对。

⚠️ **坑 1：dashscope 产物 URL 是临时的（约 24h）。** `GET` 查到 `SUCCEEDED` 时**必须立即下载到本地**，返回我们自己的持久 URL，不能直接回传 dashscope 的 URL。
⚠️ **坑 2：图生视频输入图必须 dashscope 服务器可公网访问。** 现有 `/chat/images` 存本地、用 `localhost` 提供，dashscope 拉不到。MVP 要求 **Java 传公网 `image_url`**（本地代理上传留二期）。

### 3.4 配置（settings 级，前缀 `ACG_AI_`，`extra=forbid` 需声明字段）

| 变量 | 默认 | 说明 |
|---|---|---|
| `ACG_AI_GENERATION_API_KEY` | `` | dashscope key；缺失 → 提交/查询返回 500 |
| `ACG_AI_GENERATION_BASE_URL` | `https://dashscope.aliyuncs.com/api/v1` | dashscope API 基址 |
| `ACG_AI_GENERATION_IMAGE_MODEL` | `wanx2.1-t2i-turbo` | 文生图模型 |
| `ACG_AI_GENERATION_VIDEO_MODEL` | `wan2.1-i2v-turbo` | 图生视频模型 |

资产存储**复用现有** `storage_root_dir` / `storage_base_url`，不新增配置。

---

## 4. 数据模型（`app/models/generation.py`）

```python
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class GenerationType(str, Enum):
    text_to_image = "text_to_image"
    image_to_video = "image_to_video"


class GenerationStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(description="文生图提示词")
    size: str = Field(default="1024*1024", description="图片尺寸，如 1024*1024")
    n: int = Field(default=1, description="生成数量")


class VideoGenerationRequest(BaseModel):
    prompt: str = Field(description="图生视频提示词")
    image_url: str = Field(description="公网可达的首帧图 URL（dashscope 需能拉取）")
    duration: int = Field(default=5, description="视频时长（秒），wan2.1 支持值")


class GenerationTask(BaseModel):
    id: str
    type: GenerationType
    status: GenerationStatus
    prompt: str
    input_image_url: Optional[str] = None       # 仅图生视频
    provider: str = "dashscope"
    provider_task_id: Optional[str] = None      # dashscope 返回的 task_id
    output_url: Optional[str] = None            # 我们本地的持久 URL
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
```

> `Result<T>` 信封沿用 `app/models/common.py`，不在本文件重复定义。

---

## 5. 核心逻辑

### 5.1 dashscope 客户端（`dashscope_client.py`）

基于 `httpx.AsyncClient`，统一处理 401/429/5xx → 抛异常（由 service 捕获转 500）。

```python
async def submit_text_to_image(prompt, size, n) -> str  # 返回 provider_task_id
async def submit_image_to_video(prompt, img_url, duration) -> str
async def query_task(provider_task_id) -> QueryResult
    # QueryResult: {status: PENDING|RUNNING|SUCCEEDED|FAILED, asset_url: str|None, error: str|None}
```

提交请求带 `X-DashScope-Async: enable` 头；查询走 `GET {base}/tasks/{id}`。

### 5.2 任务存储（`generation_store.py`）

复用 JSON 文件模式（与 `knowledge_store` / `tool_store` 一致）：`data/generation_tasks/{id}.json`。

```python
def create(task: GenerationTask) -> GenerationTask
def get(task_id: str) -> Optional[GenerationTask]
def update(task_id: str, **fields) -> GenerationTask   # 刷新 updated_at
```

### 5.3 编排（`generation_service.py`）

```
submit_image(req, user_id):
  1) provider_task_id = await dashscope_client.submit_text_to_image(req.prompt, req.size, req.n)
  2) task = GenerationTask(id=uuid, type=text_to_image, status=pending,
                           prompt=req.prompt, provider_task_id=provider_task_id, ...)
     store.create(task)
  3) return Result.success({"task_id": task.id})

submit_video(req, user_id):
  1) provider_task_id = await dashscope_client.submit_image_to_video(req.prompt, req.image_url, req.duration)
  2) task = GenerationTask(..., type=image_to_video, input_image_url=req.image_url, ...)
     store.create(task)
  3) return Result.success({"task_id": task.id})

get_task(task_id):
  1) task = store.get(task_id)   # None → 404
  2) if task.status in (pending, running):
        r = await dashscope_client.query_task(task.provider_task_id)
        match r.status:
          SUCCEEDED → url = download_asset(r.asset_url, task)
                      store.update(task.id, status=succeeded, output_url=url)
          FAILED    → store.update(task.id, status=failed, error=r.error)
          _         → store.update(task.id, status=running)
  3) return Result.success(store.get(task_id))   # 返回最新态
```

### 5.4 资产下载（`generation_service.download_asset`）

```
download_asset(remote_url, task) -> local_url:
  ext = 推断自 remote_url / content-type
  path = {storage_root_dir}/generations/{task.type}/{task.id}.{ext}
  httpx 流式下载 → 落盘 path
  return f"{storage_base_url}/generations/{task.type}/{task.id}.{ext}"
```

下载失败抛异常 → 由 `get_task` 捕获置 `failed`（Fail Loud，不静默）。

---

## 6. HTTP 契约（Python 暴露给 Java）

所有路由前缀 `/api/v1`，需 `X-API-Key`；`user_id` 由 Java 经 `X-User-Id` 透传。

| 方法 | 路径 | 用途 | 返回 |
|---|---|---|---|
| POST | `/api/v1/generations/images` | 文生图，提交任务 | `Result<{task_id}>`（code=200） |
| POST | `/api/v1/generations/videos` | 图生视频，提交任务 | `Result<{task_id}>`（code=200） |
| GET | `/api/v1/generations/tasks/{task_id}` | 轮询任务 | `Result<GenerationTask>` |

### 6.1 文生图

请求：
```jsonc
{ "prompt": "一只在月球上喝咖啡的橘猫，赛博朋克风", "size": "1024*1024", "n": 1 }
// Header: X-API-Key, X-User-Id
```
响应（`code=200`，HTTP 200）：
```jsonc
{ "code": 200, "message": "success", "data": { "task_id": "a1b2c3d4e5f6" } }
```

### 6.2 图生视频

请求：
```jsonc
{ "prompt": "镜头缓慢推进，猫转头", "image_url": "https://cdn.example.com/cat.png", "duration": 5 }
// Header: X-API-Key, X-User-Id
```
响应：同上 `{task_id}`。

### 6.3 轮询（`GET /tasks/{id}`）

进行中：
```jsonc
{ "code": 200, "data": { "id": "a1b2...", "type": "text_to_image", "status": "running", "prompt": "...", "output_url": null } }
```
完成：
```jsonc
{ "code": 200, "data": { "id": "a1b2...", "status": "succeeded",
    "output_url": "http://host:8100/uploads/generations/text_to_image/a1b2....png" } }
```
失败（含审核拦截）：
```jsonc
{ "code": 200, "data": { "id": "a1b2...", "status": "failed", "error": "data_inspection failed: 涉敏感内容" } }
```

---

## 7. 错误处理（Fail Loud）

| 场景 | 处理 |
|---|---|
| dashscope key 缺失 / 提交失败 / 401 / 5xx | `code=500`，清晰 message（沿用项目「外部异常=500」） |
| 查询返回 FAILED（含审核拦截） | 任务 `status=failed` + `error`（透传 dashscope 原因） |
| 资产下载失败 | `status=failed`，`error="资产下载失败"`，不静默 |
| `task_id` 不存在 | `code=404` |
| 图生视频缺 `image_url` / 字段非法 | 422（FastAPI Pydantic 自动） |

---

## 8. 内容安全

MVP **依赖 dashscope 内置 `data_inspection` 审核**：违规 prompt/输入图 → dashscope 任务 `FAILED`，原因透传到 `task.error`。

不引入自定义 gen-moderation，**不与 prompt-generation 的 ACG/compliant mode 耦合**（生成场景的 mode 适配留二期）。

---

## 9. 测试（CLAUDE.md 规则 9：验证意图，非仅行为）

mock `dashscope_client`（httpx 打桩），**不真打 dashscope**。

| 用例 | 验证的意图 |
|---|---|
| `test_submit_image_returns_task_id_pending` | 提交立即返 task_id + pending → 不阻塞、不等待生成 |
| `test_poll_running_then_succeeded_downloads_asset` | 查询到成功 → 下载资产到本地 → 返回**本地** URL（坑 1） |
| `test_poll_failed_records_error` | dashscope FAILED → 任务 failed + 带原因 |
| `test_resumes_via_provider_task_id_after_restart` | 仅凭本地存的 `provider_task_id` 即可继续查询（无状态轮询的核心价值） |
| `test_moderation_block_surfaces_as_failed` | dashscope 审核拦截 → failed 而非静默成功 |
| `test_i2v_requires_public_image_url` | 图生视频缺 `image_url` → 422 |
| `test_asset_download_failure_marks_failed` | 下载抛异常 → 任务 failed，不静默吞错 |

---

## 10. 假设与待办

- **假设**：Java 侧负责 `user_id` 透传、前端轮询 UI、公网图 URL 的获取（坑 2）。
- **假设**：Java 会轮询到 `succeeded`/`failed` 终态才停；否则 dashscope 产物 URL 过期会丢失（MVP 可接受，二期加后台兜底下载）。
- **假设**：dashscope 为 OpenAI 兼容之外的独立异步 API（不复用 `create_chat_model`）。
- **二期触发条件**：当需要对话内生成 / 多 provider / 自定义审核 / 文生视频 时再扩展。
