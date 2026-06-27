# 图生文（Image-to-Text）接入 Agent 对话链路 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户上传图片 → 服务端存盘返回 URL → 对话请求携带图片 URL → 走现有 `chat`/`tool_use` 链路，由 Agent 配置的视觉模型看图生成文字。

**Architecture:** 不引入新 SDK，复用现有 `langchain_openai.ChatOpenAI`（OpenAI 兼容协议）。新增 `app/services/image_service.py` 作为图片存储/编码/content 组装的唯一真相源；`chat_service._build_messages`（plain 与 tool_use 两条路径的共同 chokepoint）改为调用 `image_service.build_message_content` 构造 `HumanMessage`——无图时返回纯字符串（零回归），有图时返回标准 OpenAI 多模态 content list。发送时读本地文件转 base64 data URL 内联（云端模型无法访问本机 URL）。新增 `POST /api/v1/chat/images` 上传端点（仿 `document.py`），`ChatRequest` 加 `images` 字段。

**Tech Stack:** Python ^3.11、FastAPI（`UploadFile`/`File`，已有 `python-multipart`）、pydantic v2 / pydantic-settings（`.env`，前缀 `ACG_AI_`，`extra="forbid"`）、langchain-openai `ChatOpenAI`、pytest + pytest-asyncio（`asyncio_mode=auto`）。

## Global Constraints

- 仅用 OpenAI 兼容协议，**不引入新依赖**（`python-multipart` 已在 `pyproject.toml`，base64 用标准库）。
- 配置走现有 pydantic-settings `.env`（前缀 `ACG_AI_`，`extra="forbid"`）；新增字段必须在 `Settings` 里声明，否则启动 ValidationError。
- 存储：默认 D 盘（`D:/acgagent-ai/uploads`），**完全可 `.env` 覆盖**；发送时 base64 内联，模型不通过 HTTP 拉图。
- 图片输入**可选**：`images` 默认空 = 纯文本对话逐字一致（零回归）；能否真看图取决于 Agent 配置的模型，**不加 vision capability 标志**。
- 图片**单轮**：memory 只存用户文字，图片不入记忆；后续轮次拿不到历史图是预期行为。
- 范围：覆盖 `chat` + `tool_use` 两种 capability；**workflow/RAG 路径不支持图**（`stream_chat` 收到 `images` 但 workflow 分支不消费，spec §7）。
- 不挂 StaticFiles、不改 `AgentConfig`/`LLMConfig` 结构。
- **commit message 用中文**；改动后跑 `/code-review`；变更记录写 `docs/changelogs/`。
- 测试遵循 Rule 9：必须锁定业务意图（如「无图零回归」「记忆不存图」「模型真收到多模态」），业务逻辑变了测试要能失败。

**参考文件（实现前通读）：**
- `app/core/llm.py`（`create_chat_model`，构造 `ChatOpenAI`）
- `app/services/chat_service.py`（`_build_messages` 是 chokepoint；`stream_chat`/`sync_chat`/`_stream_plain`/`_stream_with_tools`）
- `app/services/document_service.py:35-54`（上传落盘参考：`settings.data_dir/"uploads"`、`mkdir(parents=True, exist_ok=True)`、`write_bytes`）
- `app/api/v1/document.py`（`UploadFile = File(...)` 端点风格）
- `app/api/v1/router.py:15`（`/api/v1` 父路由已挂 `Depends(verify_api_key)`，子端点自动继承鉴权）
- `app/core/memory.py:39,54,61`（`conversation_id` 为空时 load/save 均 short-circuit，测试可用空 conv_id 规避 ChromaDB）
- `tests/conftest.py`（`client`/`auth_headers` fixtures）、`tests/test_chat.py`（API 测试风格、`?validate=false` 建 agent）

---

### Task 1: image_service + storage 配置

**Files:**
- Modify: `app/config.py`（新增 `storage_root_dir` / `storage_base_url` 字段）
- Modify: `.env.example`（追加 storage 段）
- Create: `app/services/image_service.py`
- Test: `tests/test_image_service.py`

**Interfaces:**
- Consumes: `app.config.settings`（`storage_root_dir: Path`、`storage_base_url: str`，运行时读取，可用 monkeypatch 覆盖）
- Produces:
  - `ImageRef(BaseModel)` —— 字段 `url: str`、`filename: str`
  - `save_upload(filename: str, content: bytes, content_type: str) -> ImageRef`
  - `to_data_urls(urls: list[str]) -> list[str]`
  - `build_message_content(text: str, image_urls: list[str] | None) -> str | list`
  - `MAX_IMAGE_BYTES` 常量

- [ ] **Step 1: 在 `app/config.py` 的 Settings 加两个字段**

在 `llm_key_qwen` 字段之后、`model_config = {...}` 之前插入：

```python
    # 图片存储（图生文）：物理落盘根目录 + 对外/DB 引用 URL 前缀。均可由 .env 覆盖（不锁死）。
    # 发送时转 base64 内联，云端模型不真的拉图——base_url 仅作引用。
    storage_root_dir: Path = Path("D:/acgagent-ai/uploads")
    storage_base_url: str = "http://localhost:8100/uploads"
```

（`from pathlib import Path` 已在 `config.py:8` 导入，无需新增 import。）

- [ ] **Step 2: 在 `.env.example` 末尾追加 storage 段（值后禁止行内注释）**

在文件末尾追加：

```
# —— 图片存储（图生文为可选能力，依赖 Agent 配置的视觉模型）——
# 物理落盘根目录（默认 D 盘，脱离项目目录避免污染 git 树）。
ACG_AI_STORAGE_ROOT_DIR=D:/acgagent-ai/uploads
# 对外/DB 引用的 URL 前缀（云端模型不真的拉图——发送时转 base64 内联；此值仅作引用）。
ACG_AI_STORAGE_BASE_URL=http://localhost:8100/uploads
```

- [ ] **Step 3: 写失败测试 `tests/test_image_service.py`**

```python
"""image_service 测试 —— 图生文存储与编码的唯一真相源。

锁定意图（Rule 9）：
- save_upload 只接受 image/* 并落盘，返回 base_url+filename 的 url；
- to_data_urls 真实读盘转 base64；文件缺失 Fail Loud；
- build_message_content 无图=纯字符串（零回归），有图=多模态 list。
"""
import base64

import pytest

from app.services import image_service
from app.services.image_service import MAX_IMAGE_BYTES, ImageRef


PNG = b"\x89PNG\r\n\x1a\n"


def test_save_upload_writes_file_and_returns_url(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")

    ref = image_service.save_upload("cat.png", PNG, "image/png")

    assert isinstance(ref, ImageRef)
    assert ref.url == f"http://x/up/{ref.filename}"
    assert ref.filename.endswith(".png")
    assert (tmp_path / ref.filename).read_bytes() == PNG


def test_save_upload_rejects_non_image(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    with pytest.raises(ValueError):
        image_service.save_upload("a.txt", b"hello", "text/plain")


def test_save_upload_rejects_oversize(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    with pytest.raises(ValueError):
        image_service.save_upload("big.png", b"x" * (MAX_IMAGE_BYTES + 1), "image/png")


def test_to_data_urls_encodes_file_as_data_url(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", PNG, "image/png")

    [du] = image_service.to_data_urls([ref.url])

    assert du.startswith("data:image/png;base64,")
    assert base64.b64decode(du.split("base64,", 1)[1]) == PNG


def test_to_data_urls_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    with pytest.raises(FileNotFoundError):
        image_service.to_data_urls(["http://x/up/nope.png"])


def test_build_message_content_no_images_returns_plain_string():
    assert image_service.build_message_content("hi", None) == "hi"
    assert image_service.build_message_content("hi", []) == "hi"


def test_build_message_content_with_images_returns_multimodal_list(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", PNG, "image/png")

    content = image_service.build_message_content("describe", [ref.url])

    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
```

- [ ] **Step 4: 跑测试确认失败**

Run: `pytest tests/test_image_service.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.services.image_service'`

- [ ] **Step 5: 实现 `app/services/image_service.py`**

```python
"""
图片服务 —— 图生文能力的存储与编码唯一真相源。

- save_upload：校验 mime/大小，落盘到 settings.storage_root_dir，返回 ImageRef(url, filename)。
- to_data_urls：把存储 url 映射回本地文件，读字节转 base64 data URL（发送时内联，spec ①）。
- build_message_content：组装 HumanMessage.content——无图返回纯字符串（零回归），
  有图返回多模态 list（标准 OpenAI image_url 格式）。

云端模型不通过 HTTP 拉图（无法访问本机 URL），base_url 仅作「DB/前端引用」。
mime 由落盘文件名扩展名推断（落盘名保留原扩展名）。
"""
import base64
import uuid
from pathlib import Path

from pydantic import BaseModel

from app.config import settings

# 单张图片大小上限（spec §6：模块常量，本轮不做配置项）。
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


class ImageRef(BaseModel):
    url: str          # settings.storage_base_url + "/" + filename，存入对话引用
    filename: str     # 落盘文件名（uuid + 原扩展名）


def _ext_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def _mime_for(filename: str) -> str:
    return _EXT_MIME.get(_ext_of(filename), "image/jpeg")


def save_upload(filename: str, content: bytes, content_type: str) -> ImageRef:
    """保存上传图片到 storage_root_dir，返回引用。

    content_type 不以 image/ 开头、或 content 超过 MAX_IMAGE_BYTES → ValueError（Fail Loud）。
    落盘名 = uuid.hex + 原扩展名（防碰撞、保扩展名以推断 mime）。
    """
    if not content_type or not content_type.startswith("image/"):
        raise ValueError(f"unsupported image content_type: {content_type!r} (must be image/*)")
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError(f"image too large: {len(content)} bytes > {MAX_IMAGE_BYTES}")

    ext = _ext_of(filename) or ".png"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    root = Path(settings.storage_root_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / stored_name).write_bytes(content)
    return ImageRef(url=f"{settings.storage_base_url.rstrip('/')}/{stored_name}", filename=stored_name)


def to_data_urls(urls: list[str]) -> list[str]:
    """把存储 url 列表转成 base64 data URL 列表（发送时内联）。

    basename(url) → 读 storage_root_dir/basename → data:<mime>;base64,<b64>。
    文件缺失抛 FileNotFoundError（Fail Loud，不静默跳过——spec §6）。
    """
    root = Path(settings.storage_root_dir)
    out = []
    for url in urls:
        name = url.rsplit("/", 1)[-1]
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"image file not found for url: {url}")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        out.append(f"data:{_mime_for(name)};base64,{b64}")
    return out


def build_message_content(text: str, image_urls: list[str] | None) -> str | list:
    """组装 HumanMessage.content。

    image_urls 为空 → 返回原 text（零回归，行为与改造前逐字一致）。
    非空 → 返回 [{type:text}, {type:image_url}...]（标准 OpenAI 多模态格式）。
    """
    if not image_urls:
        return text
    data_urls = to_data_urls(image_urls)
    content = [{"type": "text", "text": text}]
    content.extend({"type": "image_url", "image_url": {"url": du}} for du in data_urls)
    return content
```

- [ ] **Step 6: 跑测试确认通过**

Run: `pytest tests/test_image_service.py -v`
Expected: PASS（7 passed）

- [ ] **Step 7: 回归确认现有测试未被 Settings 改动破坏**

Run: `pytest tests/test_llm.py tests/test_chat.py tests/test_chat_service_tools.py -q`
Expected: PASS（新字段有默认值，`extra="forbid"` 不受影响）

- [ ] **Step 8: Commit**

```bash
git add app/config.py .env.example app/services/image_service.py tests/test_image_service.py
git commit -m "feat(image): 新增 image_service（存储/base64/content 组装）+ storage 配置"
```

---

### Task 2: chat_service 透传 images 到 _build_messages

**Files:**
- Modify: `app/services/chat_service.py`（import、`stream_chat`、`_stream_plain`、`_stream_with_tools`、`_build_messages`、`sync_chat`）
- Test: `tests/test_chat_service_images.py`

**Interfaces:**
- Consumes: Task 1 的 `image_service.build_message_content(text, image_urls) -> str | list`
- Produces:
  - `ChatService.stream_chat(..., images: list[str] | None = None)`
  - `ChatService.sync_chat(..., images: list[str] | None = None)`
  - `ChatService._build_messages(..., images: list[str] | None = None)`
  - `_stream_plain` / `_stream_with_tools` 各加一个 `images` 末位参数

- [ ] **Step 1: 写失败测试 `tests/test_chat_service_images.py`**

```python
"""chat_service 图生文接入测试。

锁定意图（Rule 9）：
- 无图时 _build_messages 产出纯字符串 HumanMessage（零回归）；
- 有图时产出多模态 list（真实读盘转 base64）；
- 发图时存入记忆的是用户文字，不含图片负载（图片不入记忆）。
"""
import pytest
from langchain_core.messages import HumanMessage

from app.models.agent import AgentConfig, LLMConfig
from app.services import image_service
from app.services.chat_service import ChatService


def _agent():
    return AgentConfig(name="t", llm_config=LLMConfig(provider="x", model="m", base_url="http://x", api_key="k"))


class _NoHistoryMemory:
    def load_messages(self, conv_id):
        return []


def test_build_messages_no_images_is_plain_string():
    svc = ChatService()
    msgs = svc._build_messages(_agent(), _NoHistoryMemory(), "hello", "c1", images=None)
    assert isinstance(msgs[-1], HumanMessage)
    assert msgs[-1].content == "hello"


def test_build_messages_with_images_is_multimodal(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", b"\x89PNG", "image/png")

    svc = ChatService()
    msgs = svc._build_messages(_agent(), _NoHistoryMemory(), "describe", "c1", images=[ref.url])

    last = msgs[-1]
    assert isinstance(last, HumanMessage)
    assert isinstance(last.content, list)
    assert last.content[0] == {"type": "text", "text": "describe"}
    assert last.content[1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_sync_chat_persists_text_not_images(monkeypatch, tmp_path):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", b"\x89PNG", "image/png")

    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages):
            captured["messages"] = messages

            class _R:
                content = "reply"
            return _R()

    monkeypatch.setattr("app.services.chat_service.create_chat_model", lambda cfg: _FakeLLM())

    saved = {}

    class _Mem:
        def load_messages(self, conv_id):
            return []

        def save_user_message(self, conv, msg):
            saved["user"] = msg

        def save_assistant_message(self, conv, msg):
            saved["asst"] = msg

    monkeypatch.setattr(ChatService, "_build_memory", lambda self, cfg: _Mem())

    svc = ChatService()
    await svc.sync_chat(_agent(), "describe this", conversation_id="c1", images=[ref.url])

    assert saved["user"] == "describe this"                                   # 记忆只有文字
    assert captured["messages"][-1].content[0] == {"type": "text", "text": "describe this"}  # 模型收到多模态
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_chat_service_images.py -v`
Expected: FAIL —— `_build_messages() got an unexpected keyword argument 'images'` / `sync_chat() ... 'images'`

- [ ] **Step 3: 改 `app/services/chat_service.py` —— 加 import**

在 `from app.core.llm import create_chat_model`（第 16 行）之后新增一行：

```python
from app.services import image_service
```

- [ ] **Step 4: 改 `stream_chat` 签名与路由（传 images；workflow 分支不消费，spec §7）**

把 `stream_chat` 改为：

```python
    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
        images: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """对话入口。保存用户消息后根据能力路由到对应模式。"""
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        # 优先级：workflow > tool_use > 纯聊天
        # 注意：workflow/RAG 路径本轮不支持图（spec §7），images 不传入。
        if "workflow" in agent_config.capabilities:
            from app.core.workflow import AgentWorkflow
            workflow = AgentWorkflow(agent_config, memory, conversation_id)
            async for event in workflow.stream_workflow(message):
                yield event
            return

        llm = create_chat_model(agent_config.llm_config)

        if self._has_tools(agent_config):
            async for event in self._stream_with_tools(llm, agent_config, message, memory, conversation_id, images):
                yield event
        else:
            async for event in self._stream_plain(llm, agent_config, message, memory, conversation_id, images):
                yield event
```

- [ ] **Step 5: 改 `_stream_plain`（加 images 参数 + 传给 _build_messages）**

```python
    async def _stream_plain(self, llm, agent_config, message, memory, conversation_id, images=None):
        """纯聊天模式：直接流式调用 LLM，无工具绑定。"""
        messages = self._build_messages(agent_config, memory, message, conversation_id, images)
        full_content = ""
        try:
            async for chunk in llm.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"
            memory.save_assistant_message(conversation_id, full_content)
            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"
        except Exception as e:
            logger.error("Chat streaming error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"
```

- [ ] **Step 6: 改 `_stream_with_tools`（加 images 参数 + 传给 _build_messages）**

把 `_build_messages(...)` 调用行（原第 84 行）与函数签名改为：

```python
    async def _stream_with_tools(self, llm, agent_config, message, memory, conversation_id, images=None):
        """工具调用模式：将工具绑定到 LLM，LLM 在生成过程中可自主调用工具。
        ...（docstring 不变）"""
        tools = self._get_tools(agent_config)
        llm_with_tools = llm.bind_tools(tools)
        messages = self._build_messages(agent_config, memory, message, conversation_id, images)
        full_content = ""
        # ...（其余 try/except 体不变）
```

（仅两处改动：签名加 `images=None`；`_build_messages(...)` 调用末尾加 `, images`。函数体其余逐字保留。）

- [ ] **Step 7: 改 `_build_messages`（加 images 参数 + 用 build_message_content）**

```python
    def _build_messages(self, agent_config, memory, message, conversation_id, images=None):
        """构建发送给 LLM 的消息列表。

        顺序：system_prompt → 会话历史（经 token 裁剪） → 当前用户消息。
        当前用户消息的 content 由 image_service.build_message_content 组装：
        无图返回纯字符串（零回归），有图返回多模态 list（图生文）。
        """
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))
        history = memory.load_messages(conversation_id)
        messages.extend(history)
        messages.append(HumanMessage(content=image_service.build_message_content(message, images)))
        return messages
```

- [ ] **Step 8: 改 `sync_chat`（加 images 参数 + 传给 _build_messages）**

```python
    async def sync_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
        images: list[str] | None = None,
    ) -> ChatCompletionVO:
        """同步对话模式。等待 LLM 完整响应后一次性返回，不使用流式。"""
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        llm = create_chat_model(agent_config.llm_config)
        messages = self._build_messages(agent_config, memory, message, conversation_id, images)

        try:
            response = await llm.ainvoke(messages)
            content = response.content or ""
            memory.save_assistant_message(conversation_id, content)
            return ChatCompletionVO(content=content, usage=UsageInfo())
        except Exception as e:
            logger.error("Chat sync error: %s", e)
            raise
```

- [ ] **Step 9: 跑新测试确认通过**

Run: `pytest tests/test_chat_service_images.py -v`
Expected: PASS（3 passed）

- [ ] **Step 10: 回归现有 chat_service 测试**

Run: `pytest tests/test_chat_service_tools.py tests/test_chat.py -q`
Expected: PASS（`images` 默认 None，零回归）

- [ ] **Step 11: Commit**

```bash
git add app/services/chat_service.py tests/test_chat_service_images.py
git commit -m "feat(chat): _build_messages 透传 images，按需构造多模态 HumanMessage"
```

---

### Task 3: 对话 API —— 上传端点 + ChatRequest.images + 对话透传

**Files:**
- Modify: `app/models/chat.py`（`ChatRequest` 加 `images`）
- Modify: `app/api/v1/chat.py`（import、上传端点、对话端点透传）
- Test: `tests/test_chat.py`（末尾追加 3 个测试）

**Interfaces:**
- Consumes: Task 1 的 `image_service.save_upload` + Task 2 的 `chat_service.{stream,sync}_chat(images=...)`
- Produces:
  - `POST /api/v1/chat/images`（multipart `file`，继承父路由 `X-API-Key` 鉴权）→ `Result.success(ImageRef)` / `Result.error(400)`
  - `ChatRequest.images: list[str] = []`
  - `chat_completions` 把 `body.images` 透传给 `chat_service`

- [ ] **Step 1: 在 `tests/test_chat.py` 末尾追加失败测试**

```python
@pytest.mark.asyncio
async def test_upload_image_returns_url(client, auth_headers, tmp_path, monkeypatch):
    """上传图片 → 200，返回 url，文件落到 storage_root_dir。"""
    from app.services import image_service
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")

    png = b"\x89PNG\r\n\x1a\n"
    resp = await client.post(
        "/api/v1/chat/images",
        files={"file": ("cat.png", png, "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    url = body["data"]["url"]
    assert url.startswith("http://x/up/")
    fname = url.rsplit("/", 1)[-1]
    assert (tmp_path / fname).read_bytes() == png


@pytest.mark.asyncio
async def test_upload_image_rejects_non_image(client, auth_headers, tmp_path, monkeypatch):
    """非图片 mime → 400。"""
    from app.services import image_service
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    resp = await client.post(
        "/api/v1/chat/images",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400


@pytest.mark.asyncio
async def test_chat_threads_images_to_model(client, auth_headers, tmp_path, monkeypatch):
    """意图：对话请求带 images 时，模型端收到多模态消息（端到端透传）。conversation_id 留空以规避 ChromaDB。"""
    from app.services import image_service
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", b"\x89PNG", "image/png")

    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages):
            captured["messages"] = messages

            class _R:
                content = "it's a cat"
            return _R()

    monkeypatch.setattr("app.services.chat_service.create_chat_model", lambda cfg: _FakeLLM())

    resp = await client.post("/api/v1/agents?validate=false", json={
        "name": "Vision Agent",
        "llm_config": {
            "provider": "qwen",
            "model": "qwen-vl-max",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-test",
            "temperature": 0.7,
        },
    }, headers=auth_headers)
    agent_id = resp.json()["data"]["id"]

    resp = await client.post(f"/api/v1/chat/{agent_id}/completions", json={
        "message": "describe",
        "images": [ref.url],
        "stream": False,
    }, headers=auth_headers)
    assert resp.json()["code"] == 200
    last = captured["messages"][-1]
    assert isinstance(last.content, list)
    assert last.content[1]["type"] == "image_url"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_chat.py::test_upload_image_returns_url -v`
Expected: FAIL —— `404`（端点 `/api/v1/chat/images` 还不存在）

- [ ] **Step 3: 改 `app/models/chat.py` —— ChatRequest 加 images**

把 `ChatRequest` 改为：

```python
class ChatRequest(BaseModel):
    conversation_id: str = ""
    message: str
    images: list[str] = []
    stream: bool = True
    options: Optional[ChatOptions] = None
```

- [ ] **Step 4: 改 `app/api/v1/chat.py` —— import**

把文件顶部 import 段改为：

```python
from fastapi import APIRouter, Header, UploadFile, File
from fastapi.responses import StreamingResponse

from app.core.llm import resolve_api_key
from app.models.chat import ChatRequest
from app.models.common import Result
from app.services import image_service
from app.services.chat_service import chat_service
from app.services.agent_service import agent_service
```

（新增 `UploadFile, File` 与 `from app.services import image_service`。）

- [ ] **Step 5: 改 `app/api/v1/chat.py` —— 新增上传端点**

在 `router = APIRouter(tags=["chat"])` 之后、`chat_completions` 之前插入：

```python
@router.post("/chat/images")
async def upload_image(file: UploadFile = File(...)):
    """上传图片，存盘后返回 url（供对话请求的 images 字段引用）。

    非 image/* 或超限 → Result.error(400)。鉴权由父路由 /api/v1 的 verify_api_key 提供。
    """
    content = await file.read()
    try:
        ref = image_service.save_upload(file.filename, content, file.content_type)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    return Result.success(data=ref)
```

- [ ] **Step 6: 改 `chat_completions` —— 透传 body.images**

把分流处（原第 40-63 行）改为透传 `images=body.images`：

```python
    if body.stream:
        # SSE 流式响应：禁用缓冲确保实时推送
        return StreamingResponse(
            chat_service.stream_chat(
                agent_config=agent_config,
                message=body.message,
                conversation_id=body.conversation_id,
                user_id=x_user_id,
                images=body.images,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await chat_service.sync_chat(
            agent_config=agent_config,
            message=body.message,
            conversation_id=body.conversation_id,
            user_id=x_user_id,
            images=body.images,
        )
        return Result.success(data=result)
```

- [ ] **Step 7: 跑新增 API 测试确认通过**

Run: `pytest tests/test_chat.py -v`
Expected: PASS（含原有 + 3 个新测试）

- [ ] **Step 8: 全量回归**

Run: `pytest -q`
Expected: PASS（全部测试，含 image_service / chat_service / chat API）

- [ ] **Step 9: Commit**

```bash
git add app/models/chat.py app/api/v1/chat.py tests/test_chat.py
git commit -m "feat(chat): 新增图片上传端点 /chat/images，对话接口透传 images"
```

---

### Task 4: 全量验证 + /code-review + 变更记录 + 手动联调

**Files:**
- Create: `docs/changelogs/2026-06-28-image-to-text.zh.md`
- Verify: 全量测试 + 当前 diff 的 code-review

**Interfaces:** 无新接口；本任务为收尾验证与文档。

- [ ] **Step 1: 全量测试**

Run: `pytest -q`
Expected: 全绿。

- [ ] **Step 2: 跑 /code-review（项目规矩：改动后必跑，针对当前 diff）**

调用 `/code-review` 审查 Task 1-3 的全部改动；按反馈修复（若有），修复后重跑 `pytest -q`。

- [ ] **Step 3: 写变更记录 `docs/changelogs/2026-06-28-image-to-text.zh.md`**

```markdown
# 图生文（Image-to-Text）接入 Agent 对话链路

- 日期：2026-06-28
- 分支：aiagent_dev

## 背景
对话链路原仅支持纯文本。需让 Agent（配置视觉模型后）能看图回答：上传图片 → 存盘 → 对话引用 → 模型看图。

## 改动
- 新增 `app/services/image_service.py`：图片存储（`save_upload`）、发送时转 base64（`to_data_urls`）、
  消息 content 组装（`build_message_content`，无图零回归/有图多模态）。
- `app/config.py` + `.env.example`：新增 `storage_root_dir`（默认 `D:/acgagent-ai/uploads`）、
  `storage_base_url`，均可 `.env` 覆盖。
- `app/services/chat_service.py`：`_build_messages`（plain + tool_use 共同 chokepoint）改为按需构造多模态
  `HumanMessage`；`stream_chat`/`sync_chat` 透传 `images`。
- `app/api/v1/chat.py` + `app/models/chat.py`：新增 `POST /api/v1/chat/images` 上传端点；
  `ChatRequest` 加 `images: list[str]`；对话接口透传。

## 关键决策
- 发送时 base64 内联（云端模型无法访问本机 URL）；DB 存 URL 仅作引用。
- 图片输入可选，无 vision capability 标志；能否看图取决于 Agent 配置的模型。
- 图片单轮，不入记忆。
- workflow/RAG 路径本轮不支持图。

## 验证
- 单测：`tests/test_image_service.py`、`tests/test_chat_service_images.py`、`tests/test_chat.py`（新增 3 例）。
- 全量 `pytest` 通过；改动经 `/code-review`。
```

- [ ] **Step 4: Commit 文档**

```bash
git add docs/changelogs/2026-06-28-image-to-text.zh.md
git commit -m "docs: 图生文接入变更记录"
```

- [ ] **Step 5: 手动联调（可选，需真实视觉模型 key）**

仅在已配置某视觉模型 key（如 `ACG_AI_LLM_KEY_QWEN`）时执行：
1. 启动服务（`/run` 或 `uvicorn app.main:app`）。
2. `POST /api/v1/chat/images`（带 `X-API-Key`，multipart 上传一张图）→ 记下返回 `data.url`。
3. 创建一个 `llm_config.model=qwen-vl-max`（或对应视觉模型）的 Agent。
4. `POST /api/v1/chat/{agent_id}/completions`，body 含 `message` + `images:[<上一步 url>]`。
5. 预期：返回对该图片的文字描述。

---

## Self-Review（plan vs spec 覆盖核对）

- spec §3.1 image_service（save_upload/to_data_urls/build_message_content）→ Task 1 ✓
- spec §3.2 Settings 两字段 + .env.example → Task 1 Step 1-2 ✓
- spec §3.3 chat_service 透传 + _build_messages → Task 2 ✓
- spec §3.4 ChatRequest.images + 上传端点 + 对话透传 → Task 3 ✓
- spec §5/§5.1 通用 & 可选（无图零回归）→ Task 1 `build_message_content` + Task 2 测试锁定 ✓
- spec §6 错误处理（非图/超限/文件缺失/provider 透出）→ Task 1 实现 + 测试 ✓
- spec §7 范围（workflow 不支持图、不挂 StaticFiles、不改 Agent 模型）→ Global Constraints + Task 2 workflow 注释 ✓
- spec §8 测试意图 → 各 Task 测试均锁定业务意图 ✓
- spec §9 实施顺序 → Task 1→2→3→4 ✓
