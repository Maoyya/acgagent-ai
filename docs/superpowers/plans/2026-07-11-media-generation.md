# 媒体生成（文生图 + 图生视频）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 acgagent-ai 增加文生图 + 图生视频生成能力，通过 dashscope（通义万相）异步任务 + 提交/轮询 HTTP 端点暴露给 Java。

**Architecture:** 新增独立 `generation` 子系统（API → Service → dashscope_client + generation_store）。提交端点立即返回 `task_id`，Java 轮询 `GET /tasks/{id}`；Python 采用**无状态即时轮询**——`GET` 实际查 dashscope，`SUCCEEDED` 时立即下载产物到本地（dashscope 产物 URL 临时约 24h），返回 `storage_base_url` 形式的持久 URL。资产由 Java 侧 HTTP 服务（与现有 `/chat/images` 上传图一致，Python 不挂 StaticFiles）。

**Tech Stack:** FastAPI 0.115、pydantic v2、httpx 0.28（已是依赖，**无需新增依赖**）、dashscope REST（非 SDK，httpx 直调）、pytest + pytest-asyncio（JSON 文件持久化）。

## Global Constraints

- Python ^3.11；httpx ^0.28、fastapi ^0.115、pydantic ^2.10 已在 `pyproject.toml`，**禁止新增依赖**。
- 配置前缀 `ACG_AI_`，`Settings.extra="forbid"`——新增配置字段**必须**在 `app/config.py` 声明，否则启动 ValidationError。
- 统一 `Result<T>` 信封（`app/models/common.py`）：业务错误用 **body 内 `code`**（HTTP 200）；认证失败 HTTP 401（`verify_api_key`，router 级）；Pydantic 字段非法 HTTP 422。
- 认证 `X-API-Key` 在 `app/api/v1/router.py` 的 `dependencies=[Depends(verify_api_key)]` 统一挂载，端点内不再写；`user_id` 经 `X-User-Id` Header 直取（与 `prompt.py` 一致）。
- 测试：`asyncio_mode="auto"`（async 测试函数**无需** `@pytest.mark.asyncio`）；**禁止真实 dashscope 调用**——用 `httpx.MockTransport` 或 `monkeypatch`。
- 中文 docstring/注释，匹配现有代码风格（Rule 11）。
- TDD：每个任务先写失败测试 → 跑红 → 实现 → 跑绿 → commit。运行命令统一 `python -m pytest <path> -v`（在 `acgagent-ai` conda 环境下）。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `app/models/generation.py` | 枚举 + 请求模型 + `GenerationTask` 实体 | 新建 |
| `app/config.py` | 4 个 `generation_*` 配置字段 | 修改 |
| `app/db/generation_store.py` | JSON 任务表（create/get/update） | 新建 |
| `app/core/dashscope_client.py` | dashscope 异步任务 HTTP 客户端（submit/query） | 新建 |
| `app/services/generation_service.py` | 编排：提交 / 轮询 / 下载资产 | 新建 |
| `app/api/v1/generation.py` | 3 个端点 | 新建 |
| `app/api/v1/router.py` | 挂载 `generation_router` | 修改 |
| `tests/test_generation_*.py`、`tests/test_dashscope_client.py` | 各层测试 | 新建 |

依赖链：Task 1（models）→ Task 2（config）→ Task 3（store）→ Task 4（client）→ Task 5（service 提交）→ Task 6（service 轮询/下载）→ Task 7（API + 挂载）。

---

### Task 1: 数据模型 `app/models/generation.py`

**Files:**
- Create: `app/models/generation.py`
- Test: `tests/test_generation_models.py`

**Interfaces:**
- Produces: `GenerationType`、`GenerationStatus`（str Enum）、`ImageGenerationRequest`、`VideoGenerationRequest`（`image_url` 必填）、`GenerationTask`（持久化实体）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_generation_models.py
import pytest
from pydantic import ValidationError

from app.models.generation import (
    GenerationStatus,
    GenerationTask,
    GenerationType,
    ImageGenerationRequest,
    VideoGenerationRequest,
)


def test_image_request_defaults():
    req = ImageGenerationRequest(prompt="a cat")
    assert req.size == "1024*1024"
    assert req.n == 1


def test_video_request_requires_image_url():
    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="pan")  # 缺 image_url 必须报错


def test_task_roundtrip_serialization():
    from datetime import datetime

    now = datetime(2026, 7, 11, 12, 0, 0)
    task = GenerationTask(
        id="abc123",
        type=GenerationType.text_to_image,
        status=GenerationStatus.pending,
        prompt="a cat",
        provider_task_id="ds-1",
        created_at=now,
        updated_at=now,
    )
    restored = GenerationTask.model_validate_json(task.model_dump_json())
    assert restored.provider_task_id == "ds-1"
    assert restored.output_url is None
    assert restored.type == GenerationType.text_to_image
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_generation_models.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.generation`

- [ ] **Step 3: 实现模型**

```python
# app/models/generation.py
"""
媒体生成数据模型。

文生图 / 图生视频 的请求与任务实体。任务持久化由 app/db/generation_store.py 负责。
Result<T> 信封沿用 app/models/common.py，不在此重复定义。
"""
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
    output_url: Optional[str] = None            # 本地持久 URL
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_generation_models.py -v`
Expected: PASS（3 用例）

- [ ] **Step 5: Commit**

```bash
git add app/models/generation.py tests/test_generation_models.py
git commit -m "feat(generation): 新增媒体生成数据模型（枚举/请求/任务实体）"
```

---

### Task 2: 配置字段 `app/config.py`

**Files:**
- Modify: `app/config.py`（在 `storage_base_url` 之后、`model_config` 之前插入 4 个字段）
- Test: `tests/test_generation_config.py`

**Interfaces:**
- Produces: `settings.generation_api_key` / `generation_base_url` / `generation_image_model` / `generation_video_model`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_generation_config.py
from app.config import settings


def test_generation_config_defaults():
    assert settings.generation_base_url == "https://dashscope.aliyuncs.com/api/v1"
    assert settings.generation_image_model == "wanx2.1-t2i-turbo"
    assert settings.generation_video_model == "wan2.1-i2v-turbo"
    assert isinstance(settings.generation_api_key, str)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_generation_config.py -v`
Expected: FAIL — `AttributeError: generation_base_url`

- [ ] **Step 3: 加配置字段**

Edit `app/config.py`：

```
old:
    storage_base_url: str = "http://localhost:8100/uploads"

    model_config = {
new:
    storage_base_url: str = "http://localhost:8100/uploads"

    # 媒体生成（dashscope 通义万相）：文生图 + 图生视频，异步任务
    generation_api_key: str = ""   # dashscope key；缺失 → 提交/查询返回 500
    generation_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    generation_image_model: str = "wanx2.1-t2i-turbo"
    generation_video_model: str = "wan2.1-i2v-turbo"

    model_config = {
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_generation_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_generation_config.py
git commit -m "feat(generation): 新增 dashscope 生成相关配置字段"
```

---

### Task 3: 任务存储 `app/db/generation_store.py`

**Files:**
- Create: `app/db/generation_store.py`
- Test: `tests/test_generation_store.py`

**Interfaces:**
- Consumes: `app.models.generation.GenerationTask`（Task 1）
- Produces: `generation_store` 单例，方法 `create(task) -> GenerationTask`、`get(task_id) -> GenerationTask | None`、`update(task_id, **fields) -> GenerationTask`（刷新 `updated_at`；不存在抛 `KeyError`）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_generation_store.py
from datetime import datetime

import pytest

from app.db.generation_store import GenerationStore
from app.models.generation import (
    GenerationStatus,
    GenerationTask,
    GenerationType,
)


def _new(task_id="t1", provider_task_id="ds-1"):
    now = datetime(2026, 7, 11, 12, 0, 0)
    return GenerationTask(
        id=task_id,
        type=GenerationType.text_to_image,
        status=GenerationStatus.pending,
        prompt="cat",
        provider_task_id=provider_task_id,
        created_at=now,
        updated_at=now,
    )


def test_create_get_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    store = GenerationStore()
    store.create(_new())
    got = store.get("t1")
    assert got is not None
    assert got.provider_task_id == "ds-1"


def test_get_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    assert GenerationStore().get("nope") is None


def test_update_changes_fields_and_refreshes_updated_at(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    store = GenerationStore()
    store.create(_new("t2", "ds-2"))
    updated = store.update(
        "t2", status=GenerationStatus.succeeded, output_url="http://x/y.png"
    )
    assert updated.status == GenerationStatus.succeeded
    assert updated.output_url == "http://x/y.png"
    assert updated.updated_at >= datetime(2026, 7, 11, 12, 0, 0)
    assert store.get("t2").status == GenerationStatus.succeeded


def test_update_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    with pytest.raises(KeyError):
        GenerationStore().update("missing", status=GenerationStatus.failed)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_generation_store.py -v`
Expected: FAIL — `ModuleNotFoundError: app.db.generation_store`

- [ ] **Step 3: 实现存储**

```python
# app/db/generation_store.py
"""
媒体生成任务 JSON 文件存储。

每个任务保存为 data/generation_tasks/{id}.json，模式与 tool_store / knowledge_store 一致。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.generation import GenerationTask


class GenerationStore:
    """生成任务的 JSON 文件存储（持久化到 data/generation_tasks/）。"""

    def __init__(self):
        self._dir: Path = settings.data_dir / "generation_tasks"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self._dir / f"{task_id}.json"

    def create(self, task: GenerationTask) -> GenerationTask:
        """新建任务（覆盖写）。"""
        self._path(task.id).write_text(
            task.model_dump_json(indent=2), encoding="utf-8"
        )
        return task

    def get(self, task_id: str) -> Optional[GenerationTask]:
        """按 ID 读取任务；文件不存在返回 None。"""
        path = self._path(task_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return GenerationTask(**data)

    def update(self, task_id: str, **fields) -> GenerationTask:
        """更新任务字段并刷新 updated_at；任务不存在抛 KeyError。"""
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        for k, v in fields.items():
            setattr(task, k, v)
        task.updated_at = datetime.now()
        self._path(task_id).write_text(
            task.model_dump_json(indent=2), encoding="utf-8"
        )
        return task


generation_store = GenerationStore()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_generation_store.py -v`
Expected: PASS（4 用例）

- [ ] **Step 5: Commit**

```bash
git add app/db/generation_store.py tests/test_generation_store.py
git commit -m "feat(generation): 新增 JSON 任务存储 generation_store"
```

---

### Task 4: dashscope 客户端 `app/core/dashscope_client.py`

**Files:**
- Create: `app/core/dashscope_client.py`
- Test: `tests/test_dashscope_client.py`

**Interfaces:**
- Produces: `QueryResult(status, asset_url, error)`、`DashScopeError`、`DashScopeClient(api_key, base_url, image_model, video_model, transport=None)`，方法：
  - `async submit_text_to_image(prompt, size, n) -> str`（返回 provider task_id）
  - `async submit_image_to_video(prompt, image_url, duration) -> str`
  - `async query_task(provider_task_id) -> QueryResult`
  - 测试用 `transport=httpx.MockTransport(handler)` 注入，不打真实网络。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dashscope_client.py
import json

import httpx
import pytest

from app.core.dashscope_client import DashScopeClient, DashScopeError


def _client(handler):
    return DashScopeClient(
        api_key="k",
        base_url="https://base/api/v1",
        image_model="img-m",
        video_model="vid-m",
        transport=httpx.MockTransport(handler),
    )


async def test_submit_text_to_image_returns_task_id_and_headers():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["async"] = req.headers.get("X-DashScope-Async")
        seen["auth"] = req.headers.get("Authorization")
        seen["model"] = json.loads(req.read()).get("model")
        return httpx.Response(
            200, json={"output": {"task_id": "ds-9", "task_status": "PENDING"}}
        )

    tid = await _client(handler).submit_text_to_image("cat", "1024*1024", 1)
    assert tid == "ds-9"
    assert seen["path"] == "/api/v1/services/aigc/text2image/image-synthesis"
    assert seen["async"] == "enable"
    assert seen["auth"] == "Bearer k"
    assert seen["model"] == "img-m"


async def test_submit_image_to_video_sends_img_url():
    def handler(req):
        payload = json.loads(req.read())
        assert payload["input"]["img_url"] == "https://cdn/x.png"
        assert payload["model"] == "vid-m"
        return httpx.Response(200, json={"output": {"task_id": "ds-v"}})

    tid = await _client(handler).submit_image_to_video("pan", "https://cdn/x.png", 5)
    assert tid == "ds-v"


async def test_submit_non_200_raises():
    c = _client(lambda req: httpx.Response(401, text="bad key"))
    with pytest.raises(DashScopeError):
        await c.submit_text_to_image("cat", "1024*1024", 1)


async def test_query_succeeded_image_extracts_url():
    def handler(req):
        assert req.url.path == "/api/v1/tasks/ds-1"
        return httpx.Response(
            200,
            json={"output": {"task_status": "SUCCEEDED",
                             "results": [{"url": "https://img/x.png"}]}},
        )

    r = await _client(handler).query_task("ds-1")
    assert r.status == "SUCCEEDED"
    assert r.asset_url == "https://img/x.png"


async def test_query_succeeded_video_extracts_video_url():
    def handler(req):
        return httpx.Response(
            200, json={"output": {"task_status": "SUCCEEDED",
                                  "video_url": "https://v/m.mp4"}}
        )

    r = await _client(handler).query_task("ds-2")
    assert r.asset_url == "https://v/m.mp4"


async def test_query_failed_carries_moderation_message():
    def handler(req):
        return httpx.Response(
            200,
            json={"output": {"task_status": "FAILED",
                             "message": "data_inspection failed: 敏感内容"}},
        )

    r = await _client(handler).query_task("ds-3")
    assert r.status == "FAILED"
    assert "data_inspection" in r.error


async def test_query_running_has_no_asset():
    def handler(req):
        return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

    r = await _client(handler).query_task("ds-4")
    assert r.status == "RUNNING"
    assert r.asset_url is None


async def test_query_non_200_raises():
    c = _client(lambda req: httpx.Response(500, text="boom"))
    with pytest.raises(DashScopeError):
        await c.query_task("ds-5")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_dashscope_client.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.dashscope_client`

- [ ] **Step 3: 实现客户端**

```python
# app/core/dashscope_client.py
"""
dashscope（通义万相）异步任务 HTTP 客户端。

文生图 / 图生视频 均为异步任务：提交（X-DashScope-Async: enable）拿 task_id →
轮询 GET /tasks/{id}。不依赖 dashscope SDK，直接 httpx 调 REST（OpenAI 兼容之外）。
端点/字段以官方文档为准：
- 文生图 https://help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference
- 图生视频 https://help.aliyun.com/zh/model-studio/legacy-image-to-video-api-reference/
"""
import logging
from typing import Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger("acgagent-ai")


class QueryResult(BaseModel):
    """dashscope 任务查询结果（归一化后供 service 消费）。"""

    status: str  # PENDING / RUNNING / SUCCEEDED / FAILED（dashscope 原文）
    asset_url: Optional[str] = None  # SUCCEEDED 时的产物 URL（图 results[0].url 或视频 video_url）
    error: Optional[str] = None  # FAILED 时的原因


class DashScopeError(Exception):
    """dashscope 调用异常（网络/非 2xx/解析失败），由 service 捕获转 code=500。"""


class DashScopeClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        image_model: str,
        video_model: str,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self._base = base_url.rstrip("/")
        self._image_model = image_model
        self._video_model = video_model
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(
            transport=transport, headers=headers, timeout=httpx.Timeout(60.0)
        )

    async def _submit(
        self, path: str, model: str, data_input: dict, parameters: dict
    ) -> str:
        """提交异步任务，返回 provider task_id。"""
        resp = await self._client.post(
            f"{self._base}{path}",
            json={"model": model, "input": data_input, "parameters": parameters},
            headers={"X-DashScope-Async": "enable"},
        )
        if resp.status_code != 200:
            raise DashScopeError(f"submit failed: {resp.status_code} {resp.text}")
        task_id = (resp.json().get("output") or {}).get("task_id")
        if not task_id:
            raise DashScopeError(f"submit returned no task_id: {resp.text}")
        return task_id

    async def submit_text_to_image(self, prompt: str, size: str, n: int) -> str:
        return await self._submit(
            "/services/aigc/text2image/image-synthesis",
            self._image_model,
            {"prompt": prompt},
            {"size": size, "n": n},
        )

    async def submit_image_to_video(
        self, prompt: str, image_url: str, duration: int
    ) -> str:
        return await self._submit(
            "/services/aigc/multimedia-generation/video-synthesis",
            self._video_model,
            {"prompt": prompt, "img_url": image_url},
            {"duration": duration},
        )

    async def query_task(self, provider_task_id: str) -> QueryResult:
        resp = await self._client.get(f"{self._base}/tasks/{provider_task_id}")
        if resp.status_code != 200:
            raise DashScopeError(f"query failed: {resp.status_code} {resp.text}")
        out = resp.json().get("output") or {}
        status = out.get("task_status", "PENDING")
        if status == "SUCCEEDED":
            results = out.get("results") or []
            asset_url = (results[0].get("url") if results else None) or out.get(
                "video_url"
            )
            return QueryResult(status=status, asset_url=asset_url)
        if status == "FAILED":
            return QueryResult(status=status, error=out.get("message") or str(out))
        return QueryResult(status=status)  # PENDING / RUNNING
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_dashscope_client.py -v`
Expected: PASS（8 用例）

- [ ] **Step 5: Commit**

```bash
git add app/core/dashscope_client.py tests/test_dashscope_client.py
git commit -m "feat(generation): 新增 dashscope 异步任务 HTTP 客户端"
```

---

### Task 5: Service 提交流程 `app/services/generation_service.py`

**Files:**
- Create: `app/services/generation_service.py`（本任务只写 `submit_image` / `submit_video` + `_build_client`；`get_task` 在 Task 6 追加）
- Test: `tests/test_generation_service.py`

**Interfaces:**
- Consumes: `DashScopeClient`（Task 4）、`generation_store`（Task 3）、`settings.generation_*`（Task 2）、请求模型（Task 1）
- Produces: `generation_service.submit_image(req, user_id) -> Result`、`generation_service.submit_video(req, user_id) -> Result`（成功 `code=200, data={"task_id": ...}`；key 缺失/调用失败 `code=500`）。`_build_client()` 为测试 seam。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_generation_service.py
from app.db.generation_store import GenerationStore
from app.models.common import Result
from app.models.generation import ImageGenerationRequest


def _wire(monkeypatch, tmp_path, fake_client):
    """统一接线：tmp 数据目录 + 新 store + api_key + 注入 fake client。"""
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.generation_api_key", "k")
    monkeypatch.setattr(
        "app.services.generation_service.generation_store", GenerationStore()
    )
    monkeypatch.setattr(
        "app.services.generation_service._build_client", lambda: fake_client
    )


class _FakeClient:
    def __init__(self, t2i_tid="ds-t2i", i2v_tid="ds-i2v", exc=None):
        self._t2i = t2i_tid
        self._i2v = i2v_tid
        self._exc = exc

    async def submit_text_to_image(self, prompt, size, n):
        if self._exc:
            raise self._exc
        return self._t2i

    async def submit_image_to_video(self, prompt, image_url, duration):
        if self._exc:
            raise self._exc
        return self._i2v


async def test_submit_image_returns_task_id_and_persists_pending(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, _FakeClient(t2i_tid="ds-task-1"))
    from app.services.generation_service import generation_service

    res = await generation_service.submit_image(
        ImageGenerationRequest(prompt="cat"), user_id="u1"
    )
    assert res.code == 200
    task_id = res.data["task_id"]
    task = GenerationStore().get(task_id)
    assert task is not None
    assert task.status.value == "pending"
    assert task.provider_task_id == "ds-task-1"
    assert task.type.value == "text_to_image"


async def test_submit_video_persists_input_image_url(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, _FakeClient(i2v_tid="ds-v1"))
    from app.services.generation_service import generation_service
    from app.models.generation import VideoGenerationRequest

    res = await generation_service.submit_video(
        VideoGenerationRequest(prompt="pan", image_url="https://cdn/x.png"),
        user_id="u1",
    )
    assert res.code == 200
    task = GenerationStore().get(res.data["task_id"])
    assert task.input_image_url == "https://cdn/x.png"
    assert task.type.value == "image_to_video"


async def test_submit_without_api_key_returns_500(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.generation_api_key", "")
    monkeypatch.setattr(
        "app.services.generation_service.generation_store", GenerationStore()
    )
    from app.services.generation_service import generation_service

    res = await generation_service.submit_image(
        ImageGenerationRequest(prompt="cat"), user_id="u1"
    )
    assert res.code == 500


async def test_submit_client_error_returns_500(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, _FakeClient(exc=RuntimeError("boom")))
    from app.services.generation_service import generation_service

    res = await generation_service.submit_image(
        ImageGenerationRequest(prompt="cat"), user_id="u1"
    )
    assert res.code == 500
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_generation_service.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.generation_service`

- [ ] **Step 3: 实现 service（提交流程）**

```python
# app/services/generation_service.py
"""
媒体生成服务 —— 编排 dashscope 提交/查询 + 任务持久化 + 资产下载。

- submit_image / submit_video：提交 dashscope 异步任务，落任务表（pending），返回 task_id。
- get_task：无状态即时轮询——查 dashscope；SUCCEEDED 立即下载资产到本地，FAILED 记原因。
"""
import logging
import uuid
from datetime import datetime

import httpx

from app.config import settings
from app.core.dashscope_client import DashScopeClient
from app.db.generation_store import generation_store
from app.models.common import Result
from app.models.generation import (
    GenerationStatus,
    GenerationTask,
    GenerationType,
)

logger = logging.getLogger("acgagent-ai")


def _build_client() -> DashScopeClient:
    """用 settings 构造 dashscope 客户端（测试 seam：monkeypatch 此函数）。"""
    return DashScopeClient(
        api_key=settings.generation_api_key,
        base_url=settings.generation_base_url,
        image_model=settings.generation_image_model,
        video_model=settings.generation_video_model,
    )


class GenerationService:
    async def submit_image(self, req, user_id) -> Result:
        """文生图：提交 dashscope 任务，落 pending 任务表，返回 task_id。"""
        if not settings.generation_api_key:
            return Result.error(500, "generation api key not configured")
        try:
            provider_task_id = await _build_client().submit_text_to_image(
                req.prompt, req.size, req.n
            )
        except Exception as e:
            logger.error("submit image failed: %s", e)
            return Result.error(500, f"submit failed: {e}")
        now = datetime.now()
        task = GenerationTask(
            id=uuid.uuid4().hex[:12],
            type=GenerationType.text_to_image,
            status=GenerationStatus.pending,
            prompt=req.prompt,
            provider_task_id=provider_task_id,
            created_at=now,
            updated_at=now,
        )
        generation_store.create(task)
        return Result.success({"task_id": task.id})

    async def submit_video(self, req, user_id) -> Result:
        """图生视频：需公网 image_url；提交后落 pending 任务表，返回 task_id。"""
        if not settings.generation_api_key:
            return Result.error(500, "generation api key not configured")
        try:
            provider_task_id = await _build_client().submit_image_to_video(
                req.prompt, req.image_url, req.duration
            )
        except Exception as e:
            logger.error("submit video failed: %s", e)
            return Result.error(500, f"submit failed: {e}")
        now = datetime.now()
        task = GenerationTask(
            id=uuid.uuid4().hex[:12],
            type=GenerationType.image_to_video,
            status=GenerationStatus.pending,
            prompt=req.prompt,
            input_image_url=req.image_url,
            provider_task_id=provider_task_id,
            created_at=now,
            updated_at=now,
        )
        generation_store.create(task)
        return Result.success({"task_id": task.id})


generation_service = GenerationService()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_generation_service.py -v`
Expected: PASS（4 用例）

- [ ] **Step 5: Commit**

```bash
git add app/services/generation_service.py tests/test_generation_service.py
git commit -m "feat(generation): 新增 generation_service 提交流程（文生图/图生视频）"
```

---

### Task 6: Service 轮询 + 资产下载（追加 `get_task`）

**Files:**
- Modify: `app/services/generation_service.py`（在 `GenerationService` 内追加 `get_task` / `_refresh` / `_download_asset` / `_ext_of`；顶部补 import）
- Test: `tests/test_generation_service.py`（追加用例）

**Interfaces:**
- Consumes: `DashScopeClient.query_task` → `QueryResult`（Task 4）、`generation_store.get/update`（Task 3）、`settings.storage_root_dir` / `storage_base_url`
- Produces: `generation_service.get_task(task_id) -> Result`（`code=404` 不存在；`code=500` 查询异常；成功返回最新 `GenerationTask`，`output_url` 为本地持久 URL）。

- [ ] **Step 1: 写失败测试（追加到 `tests/test_generation_service.py`）**

```python
# 追加到 tests/test_generation_service.py
from datetime import datetime

from app.core.dashscope_client import QueryResult
from app.db.generation_store import GenerationStore
from app.models.generation import (
    GenerationStatus,
    GenerationTask,
    GenerationType,
)


def _seed_pending(monkeypatch, tmp_path, task_id="t-run", provider_task_id="ds-1"):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr(
        "app.config.settings.storage_root_dir", tmp_path / "uploads"
    )
    monkeypatch.setattr("app.config.settings.storage_base_url", "http://test/uploads")
    monkeypatch.setattr("app.config.settings.generation_api_key", "k")
    store = GenerationStore()
    monkeypatch.setattr(
        "app.services.generation_service.generation_store", store
    )
    now = datetime(2026, 7, 11, 12, 0, 0)
    store.create(
        GenerationTask(
            id=task_id,
            type=GenerationType.text_to_image,
            status=GenerationStatus.pending,
            prompt="cat",
            provider_task_id=provider_task_id,
            created_at=now,
            updated_at=now,
        )
    )
    return store


class _QueryFake:
    """按顺序返回给定 QueryResult 列表。"""

    def __init__(self, results):
        self._results = list(results)

    async def query_task(self, tid):
        return self._results.pop(0)


async def test_get_task_running_reports_running(monkeypatch, tmp_path):
    _seed_pending(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.generation_service._build_client",
        lambda: _QueryFake([QueryResult(status="RUNNING")]),
    )
    from app.services.generation_service import generation_service

    r = await generation_service.get_task("t-run")
    assert r.code == 200
    assert r.data.status.value == "running"
    assert r.data.output_url is None


async def test_get_task_succeeded_marks_succeeded_and_lands_asset(monkeypatch, tmp_path):
    _seed_pending(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.generation_service._build_client",
        lambda: _QueryFake([QueryResult(status="SUCCEEDED", asset_url="https://img/x.png")]),
    )
    from pathlib import Path as P
    from app.services.generation_service import generation_service

    # 真实 httpx 下载在 test_download_asset_writes_file_and_returns_local_url 单测；
    # 此处 patch _download_asset 模拟「下载并落盘」，验证编排 + 坑 1（产物落本地、URL 本地格式）+ 幂等。
    async def fake_download(remote_url, task):
        root = P(str(tmp_path / "uploads"))
        rel = f"generations/{task.type.value}/{task.id}.png"
        (root / f"generations/{task.type.value}").mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"PNG")
        return f"http://test/uploads/{rel}"

    monkeypatch.setattr(generation_service, "_download_asset", fake_download)

    r = await generation_service.get_task("t-run")
    assert r.data.status.value == "succeeded"
    assert r.data.output_url.startswith("http://test/uploads/generations/text_to_image/")
    assert (tmp_path / "uploads" / "generations" / "text_to_image" / "t-run.png").exists()
    r2 = await generation_service.get_task("t-run")
    assert r2.data.output_url == r.data.output_url


async def test_download_asset_writes_file_and_returns_local_url(monkeypatch, tmp_path):
    # 单测真实 _download_asset：monkeypatch httpx.AsyncClient，不打网络
    monkeypatch.setattr("app.config.settings.storage_root_dir", tmp_path / "uploads")
    monkeypatch.setattr("app.config.settings.storage_base_url", "http://test/uploads")
    import app.services.generation_service as gs
    from datetime import datetime
    from app.models.generation import (
        GenerationStatus,
        GenerationTask,
        GenerationType,
    )

    class _Resp:
        content = b"PNGBYTES"

        def raise_for_status(self):
            pass

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url):
            return _Resp()

    monkeypatch.setattr(gs.httpx, "AsyncClient", lambda **kw: _Client())

    task = GenerationTask(
        id="t-dl",
        type=GenerationType.text_to_image,
        status=GenerationStatus.pending,
        prompt="c",
        provider_task_id="ds",
        created_at=datetime(2026, 7, 11),
        updated_at=datetime(2026, 7, 11),
    )
    url = await gs.generation_service._download_asset("https://img/x.png", task)
    assert url == "http://test/uploads/generations/text_to_image/t-dl.png"
    assert (
        tmp_path / "uploads" / "generations" / "text_to_image" / "t-dl.png"
    ).read_bytes() == b"PNGBYTES"


async def test_get_task_failed_records_moderation_reason(monkeypatch, tmp_path):
    _seed_pending(monkeypatch, tmp_path, provider_task_id="ds-mod")
    monkeypatch.setattr(
        "app.services.generation_service._build_client",
        lambda: _QueryFake(
            [QueryResult(status="FAILED", error="data_inspection failed: 敏感内容")]
        ),
    )
    from app.services.generation_service import generation_service

    r = await generation_service.get_task("t-run")
    assert r.data.status.value == "failed"
    assert "data_inspection" in r.data.error


async def test_get_task_resumes_from_persisted_provider_task_id(monkeypatch, tmp_path):
    # 模拟「进程重启」：仅本地 JSON 存在，service 无内存态，仍能凭 provider_task_id 继续查
    _seed_pending(monkeypatch, tmp_path, task_id="t-restart", provider_task_id="ds-only-json")
    queried = {}

    class C:
        async def query_task(self, tid):
            queried["tid"] = tid
            return QueryResult(status="RUNNING")  # 用 RUNNING 避免 SUCCEEDED 触发下载

    monkeypatch.setattr("app.services.generation_service._build_client", lambda: C())
    from app.services.generation_service import generation_service

    r = await generation_service.get_task("t-restart")
    assert queried["tid"] == "ds-only-json"
    assert r.data.status.value == "running"


async def test_get_task_not_found_returns_404(monkeypatch, tmp_path):
    _seed_pending(monkeypatch, tmp_path)
    from app.services.generation_service import generation_service

    r = await generation_service.get_task("missing")
    assert r.code == 404


async def test_get_task_query_error_returns_500(monkeypatch, tmp_path):
    _seed_pending(monkeypatch, tmp_path)

    class C:
        async def query_task(self, tid):
            raise RuntimeError("network down")

    monkeypatch.setattr("app.services.generation_service._build_client", lambda: C())
    from app.services.generation_service import generation_service

    r = await generation_service.get_task("t-run")
    assert r.code == 500


async def test_asset_download_failure_marks_failed(monkeypatch, tmp_path):
    _seed_pending(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.generation_service._build_client",
        lambda: _QueryFake([QueryResult(status="SUCCEEDED", asset_url="https://img/z.png")]),
    )
    from app.services.generation_service import generation_service

    async def boom(remote_url, task):
        raise RuntimeError("502 bad gateway")

    monkeypatch.setattr(generation_service, "_download_asset", boom)
    r = await generation_service.get_task("t-run")
    assert r.data.status.value == "failed"
    assert "资产下载失败" in r.data.error
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_generation_service.py -v`
Expected: 旧 4 用例 PASS，新 7 用例 FAIL（`get_task` 不存在）

- [ ] **Step 3: 追加实现**

顶部 import 补 `Path` 与 `urlparse`：

```
old:
import logging
import uuid
from datetime import datetime

import httpx
new:
import logging
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
```

在 `GenerationService` 类内、`submit_video` 方法之后、`generation_service = GenerationService()` 之前追加：

```python
    async def get_task(self, task_id: str) -> Result:
        """轮询任务：pending/running 查 dashscope；终态直接返回（幂等）。

        不存在 → code=404；查询异常 → code=500；否则返回最新任务态。
        """
        task = generation_store.get(task_id)
        if task is None:
            return Result.error(404, f"task not found: {task_id}")
        if task.status in (GenerationStatus.pending, GenerationStatus.running):
            try:
                await self._refresh(task)
            except Exception as e:
                logger.error("query task %s failed: %s", task_id, e)
                return Result.error(500, f"query failed: {e}")
        return Result.success(generation_store.get(task_id))

    async def _refresh(self, task: GenerationTask) -> None:
        """查 dashscope 并按结果更新任务（无状态即时轮询）。

        查询异常上抛，交 get_task 转 500；下载失败就地置 failed（Fail Loud）。
        """
        r = await _build_client().query_task(task.provider_task_id)
        if r.status == "SUCCEEDED":
            try:
                local_url = await self._download_asset(r.asset_url, task)
            except Exception as e:
                logger.error("download asset for %s failed: %s", task.id, e)
                generation_store.update(
                    task.id, status=GenerationStatus.failed, error=f"资产下载失败: {e}"
                )
                return
            generation_store.update(
                task.id, status=GenerationStatus.succeeded, output_url=local_url
            )
        elif r.status == "FAILED":
            generation_store.update(
                task.id, status=GenerationStatus.failed,
                error=r.error or "generation failed",
            )
        else:  # PENDING / RUNNING
            generation_store.update(task.id, status=GenerationStatus.running)

    async def _download_asset(self, remote_url: str, task: GenerationTask) -> str:
        """下载 dashscope 产物到 storage_root_dir，返回 storage_base_url 形式的持久 URL。

        dashscope 产物 URL 临时（约 24h），必须落本地；资产 HTTP 服务由 Java 侧提供。
        """
        ext = self._ext_of(remote_url) or (
            ".png" if task.type == GenerationType.text_to_image else ".mp4"
        )
        rel = f"generations/{task.type.value}/{task.id}{ext}"
        root = Path(settings.storage_root_dir)
        (root / f"generations/{task.type.value}").mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as dl:
            resp = await dl.get(remote_url)
            resp.raise_for_status()
            (root / rel).write_bytes(resp.content)
        return f"{settings.storage_base_url.rstrip('/')}/{rel}"

    @staticmethod
    def _ext_of(url: str) -> str:
        path = urlparse(url).path
        return Path(path).suffix.lower()
```

- [ ] **Step 4: 跑全部 service 测试确认通过**

Run: `python -m pytest tests/test_generation_service.py -v`
Expected: PASS（4 旧 + 8 新 = 12 用例）

- [ ] **Step 5: Commit**

```bash
git add app/services/generation_service.py tests/test_generation_service.py
git commit -m "feat(generation): service 新增 get_task 无状态轮询 + 资产下载"
```

---

### Task 7: API 端点 + 路由挂载

**Files:**
- Create: `app/api/v1/generation.py`
- Modify: `app/api/v1/router.py`（import + include）
- Test: `tests/test_generation_api.py`

**Interfaces:**
- Consumes: `generation_service`（Task 5/6）、请求模型（Task 1）、`Result`（`app.models.common`）
- Produces: 3 个端点（`POST /generations/images`、`POST /generations/videos`、`GET /generations/tasks/{task_id}`），全部 `-> Result`，`X-API-Key` 由 router 级 `verify_api_key` 守卫。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_generation_api.py
from app.models.common import Result


async def test_create_image_returns_task_id(client, auth_headers, monkeypatch):
    async def fake_submit(req, user_id):
        return Result.success({"task_id": "t-1"})

    monkeypatch.setattr(
        "app.api.v1.generation.generation_service.submit_image", fake_submit
    )
    resp = await client.post(
        "/api/v1/generations/images",
        json={"prompt": "cat"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["task_id"] == "t-1"


async def test_create_video_missing_image_url_returns_422(client, auth_headers):
    resp = await client.post(
        "/api/v1/generations/videos",
        json={"prompt": "pan"},  # 缺 image_url
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_get_task_returns_envelope(client, auth_headers, monkeypatch):
    async def fake_get(task_id):
        return Result.success(
            {"id": task_id, "type": "text_to_image", "status": "running",
             "prompt": "...", "output_url": None}
        )

    monkeypatch.setattr("app.api.v1.generation.generation_service.get_task", fake_get)
    resp = await client.get(
        "/api/v1/generations/tasks/t-1", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "running"


async def test_get_task_not_found_body_code_404(client, auth_headers, monkeypatch):
    async def fake_get(task_id):
        return Result.error(404, f"task not found: {task_id}")

    monkeypatch.setattr("app.api.v1.generation.generation_service.get_task", fake_get)
    resp = await client.get(
        "/api/v1/generations/tasks/nope", headers=auth_headers
    )
    assert resp.status_code == 200  # 业务错误走 body code
    assert resp.json()["code"] == 404


async def test_endpoints_require_api_key(client):
    resp = await client.post(
        "/api/v1/generations/images", json={"prompt": "cat"}
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_generation_api.py -v`
Expected: FAIL — 404（路由未挂载，端点不存在）

- [ ] **Step 3: 实现端点**

```python
# app/api/v1/generation.py
"""
媒体生成 API。

三个端点（均挂 /api/v1 前缀、需 X-API-Key、user_id 由 Java 经 X-User-Id 透传）：
- POST /generations/images   文生图，提交任务，返回 task_id
- POST /generations/videos   图生视频，提交任务，返回 task_id
- GET  /generations/tasks/{task_id}  轮询任务
读取 X-User-Id 的方式与 chat.py / prompt.py 一致（Header 直取，不走 Depends）。
"""
from fastapi import APIRouter, Header

from app.models.common import Result
from app.models.generation import ImageGenerationRequest, VideoGenerationRequest
from app.services.generation_service import generation_service

router = APIRouter(tags=["generation"])


@router.post("/generations/images")
async def create_image(
    body: ImageGenerationRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> Result:
    """文生图：提交 dashscope 异步任务，返回 task_id。"""
    return await generation_service.submit_image(body, user_id=x_user_id)


@router.post("/generations/videos")
async def create_video(
    body: VideoGenerationRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> Result:
    """图生视频：需公网可达 image_url；提交后返回 task_id。"""
    return await generation_service.submit_video(body, user_id=x_user_id)


@router.get("/generations/tasks/{task_id}")
async def get_task(task_id: str) -> Result:
    """轮询任务：pending/running 查 dashscope；succeeded 返回本地资产 URL。"""
    return await generation_service.get_task(task_id)
```

- [ ] **Step 4: 挂载路由**

Edit `app/api/v1/router.py`：

```
old:
from app.api.v1.prompt import router as prompt_router
new:
from app.api.v1.prompt import router as prompt_router
from app.api.v1.generation import router as generation_router
```

```
old:
router.include_router(prompt_router)
new:
router.include_router(prompt_router)
router.include_router(generation_router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_generation_api.py -v`
Expected: PASS（5 用例）

- [ ] **Step 6: 跑全量测试确认无回归**

Run: `python -m pytest -v`
Expected: 全绿（含新增 generation 全部用例；既有用例不受影响）

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/generation.py app/api/v1/router.py tests/test_generation_api.py
git commit -m "feat(generation): 新增文生图/图生视频 HTTP 端点并挂载路由"
```

---

## 完成标准（Definition of Done）

- 文生图 + 图生视频 三端点可用，`Result<T>` 信封一致。
- 提交立即返 `task_id`（pending），轮询 `GET /tasks/{id}` 到 `succeeded` 返回**本地**资产 URL（坑 1）。
- 图生视频缺 `image_url` → HTTP 422；无 `X-API-Key` → HTTP 401；任务不存在 → body `code=404`；dashscope 异常 → `code=500`。
- 全程无真实 dashscope 调用（测试用 `MockTransport`/`monkeypatch`）。
- `python -m pytest -v` 全绿，既有测试无回归。
