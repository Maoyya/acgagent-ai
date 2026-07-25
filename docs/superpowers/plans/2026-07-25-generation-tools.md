# 媒体生成 Agent 工具注册 + env 模板补全 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已有的文生图 / 图生视频 generation 能力注册为 Agent 内置工具（LLM 可在对话中决策调用），并补全 generation 相关 env 模板。

**Architecture:** 方案 A（元数据注册）。新增两个 `BaseAgentTool` 子类，`execute()` 复用模块单例 `generation_service`（用 `asyncio.run` 桥接 sync→async），只 submit 返回 task_id；注册到 `BUILTIN_TOOLS` 与 `tool_service`；顺带补齐 `knowledge_entry_lookup` 元数据。不改 `chat_service` 工具执行回路。

**Tech Stack:** Python / FastAPI / LangChain `@tool` / pydantic / pytest。

## Global Constraints

- 来源 spec：`docs/superpowers/specs/2026-07-25-generation-tools-design.md`
- `execute()` 只 submit，**不做轮询至完成**；用 `asyncio.run()` 桥接 async service。
- 复用现有单例：`from app.services.generation_service import generation_service`（与 REST API 同源）。
- `Result` 信封字段为 `code` / `message` / `data`（`app/models/common.py`），构造用 `Result.success(data)` / `Result.error(code, message)`。
- 工具无构造参数（`chat_service._get_tools` 走 `else` 分支 `cls()` 实例化）。
- 测试一律 monkeypatch `generation_service` 的方法，不真实调 dashscope、不依赖 `settings.generation_api_key`。
- **提交（git commit）需用户放行**：每个任务实现 + 测试通过后呈现，用户确认后再 commit（遵循用户全局规则，commit message 用中文）。
- 不改 `chat_service`、不动既有 176 个测试。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `app/tools/image_generation.py` | 文生图工具类（name/description/execute） | 新增 |
| `app/tools/video_generation.py` | 图生视频工具类 | 新增 |
| `app/tools/__init__.py` | 内置工具 id→类映射（单一真相源） | 修改（+2 映射） |
| `app/services/tool_service.py` | 工具元数据列表（供工具列表 API） | 修改（`_builtin_ids` +3、`_get_builtins` +3 `ToolVO`） |
| `.env.example` / `.env` | generation 配置模板 | 修改（各 +4 行） |
| `tests/test_image_generation_tool.py` | 文生图工具单测 | 新增 |
| `tests/test_video_generation_tool.py` | 图生视频工具单测 | 新增 |
| `tests/test_generation_tool_registration.py` | 注册完整性单测 | 新增 |

---

### Task 1: 文生图工具 ImageGenerationTool

**Files:**
- Create: `app/tools/image_generation.py`
- Test: `tests/test_image_generation_tool.py`

**Interfaces:**
- Consumes: `generation_service.submit_image(req: ImageGenerationRequest, user_id) -> Result`（async，单例）；`ImageGenerationRequest(prompt, size, n)`；`Result.success/error`。
- Produces: `ImageGenerationTool` 类（`BUILTIN_TOOLS` 在 Task 3 引用）。

- [ ] **Step 1: 写失败测试** `tests/test_image_generation_tool.py`

```python
"""文生图工具单元测试。monkeypatch generation_service，不真实调 dashscope。"""
from app.models.common import Result
from app.services.generation_service import generation_service
from app.tools.image_generation import ImageGenerationTool


async def _ok(req, user_id):
    return Result.success({"task_id": "tid123"})


async def _err(req, user_id):
    return Result.error(500, "generation api key not configured")


def test_execute_success_returns_task_id_and_poll_hint(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_image", _ok)
    out = ImageGenerationTool().execute(prompt="一只在窗台的猫")
    assert "tid123" in out
    assert "/api/v1/generations/tasks/tid123" in out


def test_execute_missing_prompt_returns_hint():
    out = ImageGenerationTool().execute(prompt="")
    assert out == "请提供文生图提示词"


def test_execute_failure_propagates_message(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_image", _err)
    out = ImageGenerationTool().execute(prompt="一只猫")
    assert "文生图提交失败" in out
    assert "generation api key not configured" in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_image_generation_tool.py -v`
Expected: FAIL（`ModuleNotFoundError: app.tools.image_generation`）

- [ ] **Step 3: 写最小实现** `app/tools/image_generation.py`

```python
"""文生图工具 —— 把文字描述提交为 dashscope 异步任务，返回 task_id。

复用 generation_service（与 REST API /api/v1/generations/images 同源）。
execute() 只 submit，不轮询：当前 chat 流程不调 execute（工具回路由前端编排），
此处作为工具能力实现 + 可独立测试 + 备未来后端直连。
"""
import asyncio

from app.models.common import Result
from app.models.generation import ImageGenerationRequest
from app.services.generation_service import generation_service
from app.tools.base import BaseAgentTool


class ImageGenerationTool(BaseAgentTool):
    def __init__(self):
        super().__init__(
            tool_id="image_generation",
            name="image_generation",
            description=(
                "根据文字描述生成图片。传入 prompt（必填），可选 size（如 1024*1024）、"
                "n（生成数量）。提交后返回任务 task_id，需轮询取结果。"
            ),
        )

    def execute(self, prompt: str = "", size: str = "1024*1024", n: int = 1, **kwargs) -> str:
        """提交文生图任务，返回 task_id + 轮询引导；缺参/失败返回中文提示。"""
        prompt = prompt or kwargs.get("query", "")
        if not prompt:
            return "请提供文生图提示词"
        req = ImageGenerationRequest(prompt=prompt, size=size, n=n)
        result: Result = asyncio.run(generation_service.submit_image(req, user_id=None))
        if result.code != 200:
            return f"文生图提交失败：{result.message}"
        task_id = result.data["task_id"]
        return (
            f"已提交文生图任务，task_id={task_id}。"
            f"用 GET /api/v1/generations/tasks/{task_id} 轮询获取结果。"
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_image_generation_tool.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 呈现用户放行后 commit**

```bash
git add app/tools/image_generation.py tests/test_image_generation_tool.py
git commit -m "feat(generation-tool): 新增文生图工具 image_generation + 单测"
```

---

### Task 2: 图生视频工具 VideoGenerationTool

**Files:**
- Create: `app/tools/video_generation.py`
- Test: `tests/test_video_generation_tool.py`

**Interfaces:**
- Consumes: `generation_service.submit_video(req: VideoGenerationRequest, user_id) -> Result`（async）；`VideoGenerationRequest(prompt, image_url, duration)`。
- Produces: `VideoGenerationTool` 类（`BUILTIN_TOOLS` 在 Task 3 引用）。

- [ ] **Step 1: 写失败测试** `tests/test_video_generation_tool.py`

```python
"""图生视频工具单元测试。monkeypatch generation_service，不真实调 dashscope。"""
from app.models.common import Result
from app.services.generation_service import generation_service
from app.tools.video_generation import VideoGenerationTool


async def _ok(req, user_id):
    return Result.success({"task_id": "vid456"})


async def _err(req, user_id):
    return Result.error(500, "generation api key not configured")


def test_execute_success_returns_task_id_and_poll_hint(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_video", _ok)
    out = VideoGenerationTool().execute(prompt="猫从窗台跳下", image_url="https://x/y.png")
    assert "vid456" in out
    assert "/api/v1/generations/tasks/vid456" in out


def test_execute_missing_prompt_returns_hint():
    out = VideoGenerationTool().execute(prompt="", image_url="https://x/y.png")
    assert out == "请提供图生视频提示词"


def test_execute_missing_image_url_returns_hint():
    out = VideoGenerationTool().execute(prompt="猫跑", image_url="")
    assert out == "请提供公网可达的首帧图 URL"


def test_execute_failure_propagates_message(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_video", _err)
    out = VideoGenerationTool().execute(prompt="猫跑", image_url="https://x/y.png")
    assert "图生视频提交失败" in out
    assert "generation api key not configured" in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_video_generation_tool.py -v`
Expected: FAIL（`ModuleNotFoundError: app.tools.video_generation`）

- [ ] **Step 3: 写最小实现** `app/tools/video_generation.py`

```python
"""图生视频工具 —— 把公网首帧图 + 描述提交为 dashscope 异步任务，返回 task_id。

复用 generation_service（与 REST API /api/v1/generations/videos 同源）。
execute() 只 submit，不轮询：约束同 image_generation。
"""
import asyncio

from app.models.common import Result
from app.models.generation import VideoGenerationRequest
from app.services.generation_service import generation_service
from app.tools.base import BaseAgentTool


class VideoGenerationTool(BaseAgentTool):
    def __init__(self):
        super().__init__(
            tool_id="video_generation",
            name="video_generation",
            description=(
                "根据一张公网可达的图片 URL 生成视频。必须传入 image_url（公网可达，"
                "dashscope 需能拉取）与 prompt，可选 duration（秒，默认 5）。"
                "提交后返回任务 task_id，需轮询取结果。"
            ),
        )

    def execute(self, prompt: str = "", image_url: str = "", duration: int = 5, **kwargs) -> str:
        """提交图生视频任务，返回 task_id + 轮询引导；缺参/失败返回中文提示。"""
        if not prompt:
            return "请提供图生视频提示词"
        if not image_url:
            return "请提供公网可达的首帧图 URL"
        req = VideoGenerationRequest(prompt=prompt, image_url=image_url, duration=duration)
        result: Result = asyncio.run(generation_service.submit_video(req, user_id=None))
        if result.code != 200:
            return f"图生视频提交失败：{result.message}"
        task_id = result.data["task_id"]
        return (
            f"已提交图生视频任务，task_id={task_id}。"
            f"用 GET /api/v1/generations/tasks/{task_id} 轮询获取结果。"
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_video_generation_tool.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 呈现用户放行后 commit**

```bash
git add app/tools/video_generation.py tests/test_video_generation_tool.py
git commit -m "feat(generation-tool): 新增图生视频工具 video_generation + 单测"
```

---

### Task 3: 注册到 BUILTIN_TOOLS + tool_service 元数据（含补齐 knowledge_entry_lookup）

**Files:**
- Modify: `app/tools/__init__.py`
- Modify: `app/services/tool_service.py`（`_builtin_ids`、`_get_builtins`）
- Test: `tests/test_generation_tool_registration.py`

**Interfaces:**
- Consumes: `ImageGenerationTool` / `VideoGenerationTool`（Task 1/2）；`ToolVO` / `ToolParameterSchema`（`app/models/tool.py`，`created_at` 有默认值无需传，内置工具显式 `type="builtin"`）。
- Produces: `BUILTIN_TOOLS` 含两个新工具；`tool_service.list_all()` 返回含两者的完整元数据。

- [ ] **Step 1: 写失败测试** `tests/test_generation_tool_registration.py`

```python
"""生成工具注册完整性测试。"""
from app.services.tool_service import tool_service
from app.tools import BUILTIN_TOOLS


def test_builtin_tools_includes_generation():
    assert "image_generation" in BUILTIN_TOOLS
    assert "video_generation" in BUILTIN_TOOLS


def test_tool_service_lists_generation_and_entry_lookup():
    ids = {t.id for t in tool_service.list_all()}
    # 新增的两个生成工具 + 补齐的 knowledge_entry_lookup
    assert {"image_generation", "video_generation", "knowledge_entry_lookup"} <= ids


def test_generation_tool_has_required_params_schema():
    by_id = {t.id: t for t in tool_service.list_all()}
    assert by_id["image_generation"].parameters.required == ["prompt"]
    assert set(by_id["video_generation"].parameters.required) == {"prompt", "image_url"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_generation_tool_registration.py -v`
Expected: FAIL（`KeyError: 'image_generation'` 等）

- [ ] **Step 3: 修改 `app/tools/__init__.py`**（在现有 import 后加两行、映射加两项）

在 `from app.tools.web_search import WebSearchTool` 之后新增：
```python
from app.tools.image_generation import ImageGenerationTool
from app.tools.video_generation import VideoGenerationTool
```
`BUILTIN_TOOLS` 字典内新增两项（紧跟 `knowledge_entry_lookup` 之后）：
```python
    "image_generation": ImageGenerationTool,
    "video_generation": VideoGenerationTool,
```

- [ ] **Step 4: 修改 `app/services/tool_service.py`**

`__init__` 中的 `_builtin_ids` 改为（补齐 `knowledge_entry_lookup` + 加两个生成工具）：
```python
        self._builtin_ids = {
            "calculator", "web_search", "knowledge_search",
            "knowledge_entry_lookup", "image_generation", "video_generation",
        }
```
`_get_builtins` 的返回 list 中，在现有三项之后追加三个 `ToolVO`（注意 import 链：`ToolParameterSchema` 已在同文件顶部 import）：
```python
            ToolVO(id="knowledge_entry_lookup", name="设定库检索",
                   description="在公共设定库中搜索风格/角色/故事等参考设定", type="builtin",
                   parameters=ToolParameterSchema(
                       properties={
                           "query": {"type": "string", "description": "搜索关键词"},
                           "entry_type": {"type": "string", "enum": ["style", "character", "story"],
                                          "description": "条目类型（可选）"},
                       },
                       required=["query"])),
            ToolVO(id="image_generation", name="文生图",
                   description="根据文字描述生成图片", type="builtin",
                   parameters=ToolParameterSchema(
                       properties={
                           "prompt": {"type": "string", "description": "文生图提示词"},
                           "size": {"type": "string", "description": "图片尺寸，如 1024*1024"},
                           "n": {"type": "integer", "description": "生成数量"},
                       },
                       required=["prompt"])),
            ToolVO(id="video_generation", name="图生视频",
                   description="根据公网图片 URL 生成视频", type="builtin",
                   parameters=ToolParameterSchema(
                       properties={
                           "prompt": {"type": "string", "description": "图生视频提示词"},
                           "image_url": {"type": "string", "description": "公网可达的首帧图 URL"},
                           "duration": {"type": "integer", "description": "视频时长（秒）"},
                       },
                       required=["prompt", "image_url"])),
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_generation_tool_registration.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 呈现用户放行后 commit**

```bash
git add app/tools/__init__.py app/services/tool_service.py tests/test_generation_tool_registration.py
git commit -m "feat(generation-tool): 注册文生图/图生视频为内置工具，补齐 knowledge_entry_lookup 元数据"
```

---

### Task 4: env 模板补全

**Files:**
- Modify: `.env.example`
- Modify: `.env`

**Interfaces:**
- Consumes: `app/config.py` 的 `generation_api_key` / `generation_base_url`（默认 `https://dashscope.aliyuncs.com/api/v1`）/ `generation_image_model`（默认 `wanx2.1-t2i-turbo`）/ `generation_video_model`（默认 `wan2.1-i2v-turbo`）。
- Produces: 两文件均含 4 个 `ACG_AI_GENERATION_*` 项；`.env` 的 `API_KEY` 留空由用户填。

> 注：`.env` 为 gitignored 本地文件，本步仅就地追加配置块，不涉及 commit（`.env` 不入库）。

- [ ] **Step 1: 在 `.env.example` 末尾追加** generation 配置块

```dotenv

# —— 媒体生成（文生图 / 图生视频，依赖阿里 dashscope 通义万相）——
# 必填：缺失时 POST /api/v1/generations/* 提交返 500。
ACG_AI_GENERATION_API_KEY=
# 以下均有默认值（见 app/config.py），按需取消注释覆盖。
# ACG_AI_GENERATION_BASE_URL=https://dashscope.aliyuncs.com/api/v1
# ACG_AI_GENERATION_IMAGE_MODEL=wanx2.1-t2i-turbo
# ACG_AI_GENERATION_VIDEO_MODEL=wan2.1-i2v-turbo
```

- [ ] **Step 2: 在 `.env` 末尾追加** 同样的 4 行（key 留空）

```dotenv

# —— 媒体生成（文生图 / 图生视频，dashscope 通义万相）——
ACG_AI_GENERATION_API_KEY=
# ACG_AI_GENERATION_BASE_URL=https://dashscope.aliyuncs.com/api/v1
# ACG_AI_GENERATION_IMAGE_MODEL=wanx2.1-t2i-turbo
# ACG_AI_GENERATION_VIDEO_MODEL=wan2.1-i2v-turbo
```

- [ ] **Step 3: 验证**

Run: `grep -c "ACG_AI_GENERATION_API_KEY=" .env.example .env`
Expected: 两个文件各输出 1（共 2 行计数）。

- [ ] **Step 4: 全量回归测试**

Run: `pytest -q`
Expected: PASS（原 176 + 新增 10 = 186 passed，无 fail）

- [ ] **Step 5: 呈现用户放行后 commit**（仅 `.env.example` 入库，`.env` 不入库）

```bash
git add .env.example
git commit -m "chore(env): 补全媒体生成配置模板（文生图/图生视频，dashscope）"
```

---

## Self-Review（已执行）

1. **Spec 覆盖**：spec §4.1 两个工具 → Task 1/2；§4.2 execute 只 submit → Task 1/2 实现；§4.3 注册三处 → Task 3；§4.3 knowledge_entry_lookup 补齐 → Task 3；§4.4 env → Task 4；§4.5 测试 → Task 1/2/3。§3.2「不做」均未引入任务。✓
2. **Placeholder 扫描**：无 TBD/TODO/「类似上文」，每步含完整代码与命令。✓
3. **类型一致性**：`ImageGenerationTool` / `VideoGenerationTool` 类名在 Task 1/2/3 一致；`submit_image` / `submit_video` 签名与 `generation_service.py` 一致；`Result.code/message/data` 与 `common.py` 一致；`ToolVO(type="builtin")` / `ToolParameterSchema(properties=, required=)` 与 `tool.py` 一致。✓
