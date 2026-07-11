# 结构化知识库（风格/角色/故事）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增结构化知识条目（style/character/story × public/private）的 CRUD + ChromaDB 语义检索 + 核心设定自动注入 Agent system_prompt + 工具按需查公共库。

**Architecture:** 完全对称现有 `knowledge_base` 五件套（model/store/service/api/tool）+ 一个注入器 helper。条目存 JSON（`data/knowledge_entries/{id}.json`）+ 向量化进独立 collection `kb_structured_entries`（cosine）。Agent 新增 `active_entry_ids`，注入挂载在 `chat_service._build_messages` 与 `workflow.stream_workflow` 两处，共用 `build_system_content`。

**Tech Stack:** Python 3 / FastAPI / pydantic 2.13 / langchain / ChromaDB(PersistentClient) / pytest

## Global Constraints

- **提交规矩（项目硬约束，覆盖 skill 默认）**：① commit message 用中文；② 每个 commit 前先向用户展示当前 diff 待放行，**不得自动提交**；③ 全部任务完成后跑 `/code-review`（当前 diff），修复项单独提交；④ 完成后在 `docs/changelogs/`（复数目录）写变更记录。
- **TDD**：每个任务先写失败测试 → 跑确认失败 → 最小实现 → 跑确认通过 → 提交。
- **信封**：所有 API 用 `Result.success(data=)` / `Result.error(code=, message=)`；路径 kebab-case 复数；`X-API-Key` 认证。
- **存储约定**：Store = JSON 文件 + 模块级单例；Service = 模块级单例。本特性的 `KnowledgeEntryStore._dir()` 采用 **lazy 读取 `settings.data_dir`**（与 `knowledge_store` 的 `__init__` eager 略有偏差，仅为便于测试 monkeypatch；已记录）。
- **pydantic 行为（已实测 pydantic 2.13.4）**：构造函数传入未声明字段会被静默丢弃；对未声明字段 `setattr` 会抛 `ValueError`。因此 `active_entry_ids` 必须先在 Task 3 加进 `AgentConfig`，Task 4 的注入器测试才能正常构造带该字段的对象。
- **复用 ChromaDB 基础设施**：collection `kb_structured_entries`，`metadata={"hnsw:space":"cosine"}`；embedding 文本 = `name+summary+tags`；调用 `col.query(query_texts=[...])` 走 ChromaDB 默认 embedding（与现有 `knowledge_search` 一致）。
- **测试不触发真实 embedding 下载**：service/tool/API 测试用 `fake_chroma` fixture（内存版）。纯 store/injector 测试不接触 Chroma。

---

## File Structure

**新增：**
- `app/models/knowledge_entry.py` — `KnowledgeEntry` + `EntryType`/`EntryScope` Enum + Create/Update 请求体
- `app/db/knowledge_entry_store.py` — JSON 文件存储（模块单例 `knowledge_entry_store`）
- `app/services/knowledge_entry_service.py` — CRUD + ChromaDB 同步（模块单例 `knowledge_entry_service`）
- `app/core/knowledge_injector.py` — `build_system_content(agent_config)`
- `app/tools/knowledge_entry_lookup.py` — `KnowledgeEntryLookupTool`（注册进 `BUILTIN_TOOLS`）
- `app/api/v1/knowledge_entry.py` — REST 路由
- `tests/test_knowledge_entry.py` — store/service/injector/tool 单测
- `tests/test_knowledge_entry_api.py` — API 集成测试
- `tests/test_knowledge_entry_injection.py` — 注入挂载集成测试

**修改：**
- `app/models/agent.py` — `AgentConfig`/Create/Update 加 `active_entry_ids`
- `app/services/agent_service.py` — `_validate_references`/`_validate` 扩展 entry 校验；create 透传字段
- `app/tools/__init__.py` — `BUILTIN_TOOLS` 注册新工具
- `app/api/v1/router.py` — 挂载 knowledge_entry 路由
- `app/services/chat_service.py` — `_build_messages` 改用 `build_system_content`
- `app/core/workflow.py` — `stream_workflow` 改用 `build_system_content`
- `tests/conftest.py` — 加 opt-in `fake_chroma` fixture
- `tests/test_agent_validation.py` — 扩展 entry 引用校验测试

---

## Task 1: 数据层 — 模型 + Store

**Files:**
- Create: `app/models/knowledge_entry.py`
- Create: `app/db/knowledge_entry_store.py`
- Test: `tests/test_knowledge_entry.py`

**Interfaces:**
- Consumes: `app.config.settings.data_dir`
- Produces: `KnowledgeEntry`, `EntryType`, `EntryScope`, `KnowledgeEntryCreateRequest`, `KnowledgeEntryUpdateRequest`；`knowledge_entry_store` 单例，方法 `list_all() -> list[KnowledgeEntry]`、`get(id) -> KnowledgeEntry|None`、`save(entry) -> KnowledgeEntry`、`delete(id) -> bool`

- [ ] **Step 1: 写失败测试（模型 + store 往返）**

创建 `tests/test_knowledge_entry.py`：

```python
"""结构化知识条目：模型 + store 单测。"""
from app.models.knowledge_entry import (
    KnowledgeEntry, EntryType, EntryScope,
)


def _make_entry(**over):
    base = dict(
        id="abc123",
        type=EntryType.character,
        scope=EntryScope.public,
        user_id=None,
        name="初音",
        summary="双马尾歌姬",
        tags=["vocaloid", "元气"],
        details={"series": "Vocaloid", "personality": "元气"},
    )
    base.update(over)
    return KnowledgeEntry(**base)


def test_entry_model_defaults_and_enums():
    e = _make_entry()
    assert e.type == EntryType.character
    assert e.scope == EntryScope.public
    assert e.details["personality"] == "元气"
    assert e.created_at == e.updated_at


def test_store_save_get_roundtrip(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.db.knowledge_entry_store import knowledge_entry_store
    saved = knowledge_entry_store.save(_make_entry())
    assert saved.id == "abc123"

    got = knowledge_entry_store.get("abc123")
    assert got is not None
    assert got.name == "初音"
    assert got.type == EntryType.character
    assert got.tags == ["vocaloid", "元气"]


def test_store_list_all_and_delete(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.db.knowledge_entry_store import knowledge_entry_store
    knowledge_entry_store.save(_make_entry(id="e1", name="A"))
    knowledge_entry_store.save(_make_entry(id="e2", name="B", type=EntryType.style))

    assert {e.id for e in knowledge_entry_store.list_all()} == {"e1", "e2"}

    assert knowledge_entry_store.delete("e1") is True
    assert knowledge_entry_store.get("e1") is None
    assert knowledge_entry_store.delete("nope") is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_knowledge_entry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.knowledge_entry'`

- [ ] **Step 3: 实现模型**

创建 `app/models/knowledge_entry.py`：

```python
"""
结构化知识条目数据模型。

条目分 3 种 type（style/character/story），2 种 scope（public/private）。
type 决定 details 字段内容（见 spec §3.3）；scope=private 时 user_id 必填。
存储为 JSON（data/knowledge_entries/{id}.json），向量化进 ChromaDB collection kb_structured_entries。
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class EntryType(str, Enum):
    style = "style"
    character = "character"
    story = "story"


class EntryScope(str, Enum):
    public = "public"
    private = "private"


class KnowledgeEntry(BaseModel):
    id: str = Field(default="", description="Auto-generated ID")
    type: EntryType
    scope: EntryScope
    user_id: Optional[str] = Field(default=None, description="private 必填；public 为 None")
    name: str
    summary: str = Field(description="一句话概述，同时作为 embedding 文本")
    tags: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict, description="类型特有字段（spec §3.3）")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class KnowledgeEntryCreateRequest(BaseModel):
    type: EntryType
    scope: EntryScope
    user_id: Optional[str] = None
    name: str
    summary: str
    tags: list[str] = []
    details: dict = {}


class KnowledgeEntryUpdateRequest(BaseModel):
    # type 不在此 → 不可变；extra=forbid 使传 type（或任何未知字段）→ 422（spec §6）
    model_config = ConfigDict(extra="forbid")
    scope: Optional[EntryScope] = None
    user_id: Optional[str] = None
    name: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    details: Optional[dict] = None
```

- [ ] **Step 4: 实现 store**

创建 `app/db/knowledge_entry_store.py`：

```python
"""
结构化知识条目 JSON 文件存储。

每个条目保存为 data/knowledge_entries/{id}.json。
_dir() 每次按需读取 settings.data_dir（lazy），便于测试 monkeypatch。
"""
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.knowledge_entry import KnowledgeEntry


class KnowledgeEntryStore:
    def _dir(self) -> Path:
        d = settings.data_dir / "knowledge_entries"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, entry_id: str) -> Path:
        return self._dir() / f"{entry_id}.json"

    def list_all(self) -> list[KnowledgeEntry]:
        result = []
        for f in sorted(self._dir().glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(KnowledgeEntry(**data))
            except Exception:
                pass
        return result

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        path = self._path(entry_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return KnowledgeEntry(**data)

    def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        path = self._path(entry.id)
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        return entry

    def delete(self, entry_id: str) -> bool:
        path = self._path(entry_id)
        if path.exists():
            path.unlink()
            return True
        return False


knowledge_entry_store = KnowledgeEntryStore()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_knowledge_entry.py -v`
Expected: PASS（3 tests）

- [ ] **Step 6: 提交**（先向用户展示 diff 待放行）

```bash
git add app/models/knowledge_entry.py app/db/knowledge_entry_store.py tests/test_knowledge_entry.py
git commit -m "feat(kb-entry): 结构化知识条目模型 + JSON store"
```

---

## Task 2: 服务层 — Service + ChromaDB 同步

**Files:**
- Create: `app/services/knowledge_entry_service.py`
- Modify: `tests/conftest.py`（加 `FakeChroma` 类与 `fake_chroma` fixture，此任务只 patch service 行）
- Test: `tests/test_knowledge_entry.py`（追加 service 测试）

**Interfaces:**
- Consumes: `knowledge_entry_store`（Task 1）；`app.db.chroma_client.get_chroma`
- Produces: `knowledge_entry_service` 单例，方法 `list(type,scope,user_id,q) -> list[KnowledgeEntry]`、`get(id)`、`create(req) -> KnowledgeEntry`（private 缺 user_id 抛 `ValueError`）、`update(id, req)`（不存在返回 None；合并后 private 缺 user_id 抛 `ValueError`）、`delete(id) -> bool`；模块常量 `_COLLECTION = "kb_structured_entries"`

- [ ] **Step 1: 加 `fake_chroma` fixture 到 conftest（仅 service 行）**

在 `tests/conftest.py` 末尾追加：

```python
class _FakeCollection:
    def __init__(self):
        self.docs = {}  # id -> {"document":..., "metadata":...}

    def upsert(self, ids, documents, metadatas):
        for i, d, m in zip(ids, documents, metadatas):
            self.docs[i] = {"document": d, "metadata": m}

    def delete(self, ids):
        for i in ids:
            self.docs.pop(i, None)

    def query(self, query_texts, n_results=3, where=None):
        items = list(self.docs.values())
        if where:
            items = [it for it in items
                     if all(it["metadata"].get(k) == v for k, v in where.items())]
        items = items[:n_results]
        return {
            "documents": [[it["document"] for it in items]],
            "metadatas": [[it["metadata"] for it in items]],
        }


class FakeChroma:
    """内存版 ChromaDB，避免测试触发真实 ONNX embedding 下载。"""
    def __init__(self):
        self.collections = {}

    def get_or_create_collection(self, name, metadata=None):
        return self.collections.setdefault(name, _FakeCollection())

    def get_collection(self, name):
        if name not in self.collections:
            raise Exception(f"collection {name} not found")
        return self.collections[name]


@pytest.fixture
def fake_chroma(monkeypatch):
    """patch 各消费模块已绑定的 get_chroma 名字，返回共享 FakeChroma。"""
    fake = FakeChroma()
    monkeypatch.setattr("app.services.knowledge_entry_service.get_chroma", lambda: fake)
    # Task 5 在此追加：monkeypatch.setattr("app.tools.knowledge_entry_lookup.get_chroma", lambda: fake)
    return fake
```

> 注：Task 5 创建 tool 模块后，再在 `fake_chroma` 里补 tool 那一行 patch（提前写会因模块不存在而 AttributeError）。

- [ ] **Step 2: 写失败测试（service CRUD + ChromaDB 同步 + private 校验）**

在 `tests/test_knowledge_entry.py` 末尾追加：

```python
import pytest
from app.models.knowledge_entry import (
    KnowledgeEntryCreateRequest, KnowledgeEntryUpdateRequest,
    EntryType, EntryScope,
)


def _req(**over):
    base = dict(type=EntryType.character, scope=EntryScope.public, name="初音",
                summary="双马尾歌姬", tags=["vocaloid"], details={"personality": "元气"})
    base.update(over)
    return KnowledgeEntryCreateRequest(**base)


def test_service_create_syncs_vector(tmp_path, monkeypatch, fake_chroma):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service, _COLLECTION
    entry = knowledge_entry_service.create(_req(name="A"))
    docs = fake_chroma.collections[_COLLECTION].docs
    assert entry.id in docs
    assert docs[entry.id]["metadata"]["type"] == "character"
    assert docs[entry.id]["metadata"]["scope"] == "public"


def test_service_private_without_user_id_raises(tmp_path, monkeypatch, fake_chroma):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service
    with pytest.raises(ValueError):
        knowledge_entry_service.create(_req(scope=EntryScope.private))


def test_service_update_and_delete_sync(tmp_path, monkeypatch, fake_chroma):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service, _COLLECTION
    entry = knowledge_entry_service.create(_req(name="A"))
    updated = knowledge_entry_service.update(entry.id, KnowledgeEntryUpdateRequest(name="B"))
    assert updated.name == "B"
    assert entry.id in fake_chroma.collections[_COLLECTION].docs

    assert knowledge_entry_service.delete(entry.id) is True
    assert entry.id not in fake_chroma.collections[_COLLECTION].docs
    assert knowledge_entry_service.update("nope", KnowledgeEntryUpdateRequest(name="x")) is None


def test_service_update_scope_to_private_requires_user_id(tmp_path, monkeypatch, fake_chroma):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service
    entry = knowledge_entry_service.create(_req(scope=EntryScope.public))
    with pytest.raises(ValueError):
        knowledge_entry_service.update(entry.id, KnowledgeEntryUpdateRequest(scope=EntryScope.private))


def test_service_list_filters(tmp_path, monkeypatch, fake_chroma):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service
    knowledge_entry_service.create(_req(name="初音", type=EntryType.character))
    knowledge_entry_service.create(_req(name="赛博朋克", type=EntryType.style))
    chars = knowledge_entry_service.list(type="character")
    assert len(chars) == 1 and chars[0].name == "初音"
    styles = knowledge_entry_service.list(type="style")
    assert len(styles) == 1 and styles[0].name == "赛博朋克"
    q = knowledge_entry_service.list(q="赛博")
    assert len(q) == 1
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/test_knowledge_entry.py -v -k service`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.knowledge_entry_service'`

- [ ] **Step 4: 实现 service**

创建 `app/services/knowledge_entry_service.py`：

```python
"""
结构化知识条目管理服务。

CRUD + ChromaDB 同步：create/update → upsert 向量；delete → 移除向量。
collection = kb_structured_entries（cosine），embedding 文本 = name+summary+tags。
private 条目必须有 user_id，否则 raise ValueError（路由转 400）。
ChromaDB 同步失败 best-effort（log warning，不阻断 CRUD）。
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from app.db.knowledge_entry_store import knowledge_entry_store
from app.db.chroma_client import get_chroma
from app.models.knowledge_entry import (
    KnowledgeEntry, KnowledgeEntryCreateRequest, KnowledgeEntryUpdateRequest,
    EntryScope,
)

logger = logging.getLogger("acgagent-ai")

_COLLECTION = "kb_structured_entries"


class KnowledgeEntryService:
    def _collection(self):
        return get_chroma().get_or_create_collection(
            name=_COLLECTION, metadata={"hnsw:space": "cosine"},
        )

    def _embed_text(self, entry: KnowledgeEntry) -> str:
        return f"{entry.name}\n{entry.summary}\n" + ",".join(entry.tags)

    def _meta(self, entry: KnowledgeEntry) -> dict:
        return {
            "entry_id": entry.id,
            "type": entry.type.value,
            "scope": entry.scope.value,
            "user_id": entry.user_id or "",
        }

    def _sync_upsert(self, entry: KnowledgeEntry) -> None:
        try:
            self._collection().upsert(
                ids=[entry.id],
                documents=[self._embed_text(entry)],
                metadatas=[self._meta(entry)],
            )
        except Exception as e:
            logger.warning("KB entry vector upsert failed for %s: %s", entry.id, e)

    def _sync_delete(self, entry_id: str) -> None:
        try:
            self._collection().delete(ids=[entry_id])
        except Exception as e:
            logger.warning("KB entry vector delete failed for %s: %s", entry_id, e)

    def _ensure_private_user_id(self, scope: EntryScope, user_id: Optional[str]) -> None:
        if scope == EntryScope.private and not user_id:
            raise ValueError("private 条目必须提供 user_id")

    def list(self, type: Optional[str] = None, scope: Optional[str] = None,
             user_id: Optional[str] = None, q: Optional[str] = None) -> list[KnowledgeEntry]:
        result = []
        for e in knowledge_entry_store.list_all():
            if type and e.type.value != type:
                continue
            if scope and e.scope.value != scope:
                continue
            if user_id and e.user_id != user_id:
                continue
            if q and q.lower() not in (e.name + e.summary).lower():
                continue
            result.append(e)
        return result

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        return knowledge_entry_store.get(entry_id)

    def create(self, req: KnowledgeEntryCreateRequest) -> KnowledgeEntry:
        self._ensure_private_user_id(req.scope, req.user_id)
        entry = KnowledgeEntry(
            id=uuid.uuid4().hex[:12],
            type=req.type, scope=req.scope, user_id=req.user_id,
            name=req.name, summary=req.summary, tags=req.tags, details=req.details,
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        saved = knowledge_entry_store.save(entry)
        self._sync_upsert(saved)
        return saved

    def update(self, entry_id: str, req: KnowledgeEntryUpdateRequest) -> Optional[KnowledgeEntry]:
        entry = knowledge_entry_store.get(entry_id)
        if entry is None:
            return None
        for field, value in req.model_dump(exclude_unset=True).items():
            setattr(entry, field, value)
        self._ensure_private_user_id(entry.scope, entry.user_id)  # 合并后校验
        entry.updated_at = datetime.now()
        saved = knowledge_entry_store.save(entry)
        self._sync_upsert(saved)
        return saved

    def delete(self, entry_id: str) -> bool:
        ok = knowledge_entry_store.delete(entry_id)
        if ok:
            self._sync_delete(entry_id)
        return ok


knowledge_entry_service = KnowledgeEntryService()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_knowledge_entry.py -v`
Expected: PASS（全部，含 5 个 service 测试）

- [ ] **Step 6: 提交**（先展示 diff 待放行）

```bash
git add app/services/knowledge_entry_service.py tests/conftest.py tests/test_knowledge_entry.py
git commit -m "feat(kb-entry): 条目服务层 CRUD + ChromaDB 向量同步"
```

---

## Task 3: Agent 集成（上）— active_entry_ids 模型 + 引用校验

> 必须在注入器（Task 4）之前完成：注入器测试要构造带 `active_entry_ids` 的 `AgentConfig`（pydantic 不允许构造/setattr 未声明字段）。

**Files:**
- Modify: `app/models/agent.py`
- Modify: `app/services/agent_service.py`
- Test: `tests/test_agent_validation.py`（扩展）

**Interfaces:**
- Consumes: `knowledge_entry_store.get(id)`（Task 1）
- Produces: `AgentConfig.active_entry_ids: list[str]`（默认 `[]`）；`_validate_references(kb_ids, tool_ids, entry_ids=None)`（第 3 参可选，向后兼容现有 2 参调用）；`_validate(llm_config, kb_ids, tool_ids, entry_ids, validate)`

- [ ] **Step 1: 写失败测试**

在 `tests/test_agent_validation.py` 末尾追加：

```python
def test_rejects_missing_entry_id():
    """active_entry_ids 引用不存在的条目 → ValueError。"""
    with pytest.raises(ValueError) as exc:
        agent_service._validate_references([], [], entry_ids=["ghost"])
    assert "ghost" in str(exc.value)


def test_accepts_builtin_tools_when_entry_ids_empty():
    """entry_ids 默认 None/空时不影响既有校验。"""
    agent_service._validate_references([], ["calculator"], entry_ids=[])
    agent_service._validate_references([], ["calculator"])  # 第 3 参可省
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_agent_validation.py::test_rejects_missing_entry_id -v`
Expected: FAIL — `_validate_references() got an unexpected keyword argument 'entry_ids'`

- [ ] **Step 3: 改 Agent 模型**

修改 `app/models/agent.py`：
- `AgentConfig` 加字段（置于 `tool_ids` 之后）：
  ```python
  active_entry_ids: list[str] = Field(default_factory=list, description="激活自动注入的结构化知识条目 ID")
  ```
- `AgentCreateRequest` 加：`active_entry_ids: list[str] = []`
- `AgentUpdateRequest` 加：`active_entry_ids: Optional[list[str]] = None`

- [ ] **Step 4: 扩展 agent_service 校验**

修改 `app/services/agent_service.py`：
- 顶部 import 加 `from app.db.knowledge_entry_store import knowledge_entry_store`
- `_validate_references` 改签名与实现：
  ```python
  def _validate_references(self, kb_ids, tool_ids, entry_ids=None) -> None:
      missing_kb = [kb for kb in kb_ids if knowledge_store.get(kb) is None]
      missing_tool = [
          tid for tid in tool_ids
          if tid not in BUILTIN_TOOL_IDS and tool_store.get(tid) is None
      ]
      entry_ids = entry_ids or []
      missing_entry = [eid for eid in entry_ids if knowledge_entry_store.get(eid) is None]
      if missing_kb or missing_tool or missing_entry:
          raise ValueError(
              f"引用资源不存在: knowledge_base_ids={missing_kb}, "
              f"tool_ids={missing_tool}, active_entry_ids={missing_entry}"
          )
  ```
- `_validate` 改签名，新增 `entry_ids` 形参并透传：
  ```python
  def _validate(self, llm_config, kb_ids, tool_ids, entry_ids, validate: bool) -> None:
      self._validate_references(kb_ids, tool_ids, entry_ids)
      if validate:
          ping_llm(llm_config)
  ```
- `create`：把 `self._validate(req.llm_config, req.knowledge_base_ids, req.tool_ids, validate)` 改为
  `self._validate(req.llm_config, req.knowledge_base_ids, req.tool_ids, req.active_entry_ids, validate)`；
  构造 `AgentConfig(...)` 时加 `active_entry_ids=req.active_entry_ids`
- `update`：把 `self._validate(agent.llm_config, agent.knowledge_base_ids, agent.tool_ids, validate)` 改为
  `self._validate(agent.llm_config, agent.knowledge_base_ids, agent.tool_ids, agent.active_entry_ids, validate)`
  （update_data 已含 active_entry_ids，setattr 自动落地）

- [ ] **Step 5: 跑相关测试确认通过且不回归**

Run: `pytest tests/test_agent_validation.py tests/test_agent_validation_api.py tests/test_agent_config.py tests/test_agent_api.py -v`
Expected: PASS（新测试通过；现有 2 参调用不回归）

- [ ] **Step 6: 提交**（先展示 diff 待放行）

```bash
git add app/models/agent.py app/services/agent_service.py tests/test_agent_validation.py
git commit -m "feat(agent): active_entry_ids 字段 + 引用完整性校验"
```

---

## Task 4: 注入器 — knowledge_injector

**Files:**
- Create: `app/core/knowledge_injector.py`
- Test: `tests/test_knowledge_entry.py`（追加 injector 测试）

**Interfaces:**
- Consumes: `knowledge_entry_store.get(id)`；`AgentConfig`（`system_prompt`、`active_entry_ids`，已在 Task 3 声明）
- Produces: `build_system_content(agent_config) -> str`（无内容返回 `""`；仅 system_prompt 返回原文；有激活条目返回 `system_prompt + "\n\n【参考设定】\n..."`）

- [ ] **Step 1: 写失败测试**

在 `tests/test_knowledge_entry.py` 末尾追加：

```python
def _llm_cfg():
    return {"provider": "p", "model": "m", "base_url": "u", "api_key": "k"}


def test_injector_no_active_returns_base(monkeypatch):
    from app.core.knowledge_injector import build_system_content
    from app.models.agent import AgentConfig
    from app.db.knowledge_entry_store import knowledge_entry_store
    monkeypatch.setattr(knowledge_entry_store, "get", lambda eid: None)
    cfg = AgentConfig(id="a1", name="A", system_prompt="你是助手", llm_config=_llm_cfg())
    assert build_system_content(cfg) == "你是助手"


def test_injector_empty_when_no_prompt_no_entries(monkeypatch):
    from app.core.knowledge_injector import build_system_content
    from app.models.agent import AgentConfig
    from app.db.knowledge_entry_store import knowledge_entry_store
    monkeypatch.setattr(knowledge_entry_store, "get", lambda eid: None)
    cfg = AgentConfig(id="a1", name="A", system_prompt=None, llm_config=_llm_cfg())
    assert build_system_content(cfg) == ""


def test_injector_renders_block_and_skips_missing(monkeypatch):
    from app.core.knowledge_injector import build_system_content
    from app.models.agent import AgentConfig
    from app.models.knowledge_entry import KnowledgeEntry, EntryType, EntryScope
    from app.db.knowledge_entry_store import knowledge_entry_store

    char = KnowledgeEntry(id="e1", type=EntryType.character, scope=EntryScope.public,
                          name="初音", summary="双马尾歌姬",
                          details={"series": "Vocaloid", "personality": "元气"})
    style = KnowledgeEntry(id="e2", type=EntryType.style, scope=EntryScope.public,
                           name="赛博朋克", summary="霓虹机械",
                           details={"tone": "冷峻"})  # visual_elements 缺失应跳过
    monkeypatch.setattr(knowledge_entry_store, "get",
                        lambda eid: {"e1": char, "e2": style}.get(eid))

    cfg = AgentConfig(id="a1", name="A", system_prompt="你是助手",
                      active_entry_ids=["e1", "e2", "ghost"], llm_config=_llm_cfg())
    out = build_system_content(cfg)
    assert out.startswith("你是助手\n\n【参考设定】")
    assert "[角色] 初音(Vocaloid)：双马尾歌姬 | 性格:元气" in out
    assert "[风格] 赛博朋克：霓虹机械 | 调性:冷峻" in out
    assert "视觉" not in out   # 缺失字段跳过
    assert "ghost" not in out  # 已删条目跳过
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_knowledge_entry.py -v -k injector`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.knowledge_injector'`

- [ ] **Step 3: 实现注入器**

创建 `app/core/knowledge_injector.py`：

```python
"""
结构化条目自动注入器。

把 Agent 的 active_entry_ids 对应条目渲染成【参考设定】块拼到 system_prompt 后。
注入挂载点：chat_service._build_messages 与 workflow.stream_workflow（两处共用）。
- 无激活条目 → 返回原 system_prompt（零回归）
- 激活条目已删 → 跳过 + log warning，不中断
- 仅渲染 details 中非空字段（省 token）
"""
import logging

from app.db.knowledge_entry_store import knowledge_entry_store

logger = logging.getLogger("acgagent-ai")

# 各 type 渲染时从 details 取的字段（key, 展示标签），顺序即展示顺序
_FIELD_LABELS = {
    "style": [("visual_elements", "视觉"), ("tone", "调性")],
    "character": [("series", "出处"), ("appearance", "外貌"),
                  ("personality", "性格"), ("speech_style", "口吻")],
    "story": [("setting", "世界观"), ("plot_points", "情节"), ("tone", "基调")],
}
_TYPE_LABEL = {"style": "风格", "character": "角色", "story": "故事"}


def _render_entry(entry) -> str:
    type_key = entry.type.value if hasattr(entry.type, "value") else str(entry.type)
    extra = f"({entry.details['series']})" if entry.details.get("series") else ""
    parts = [f"[{_TYPE_LABEL.get(type_key, type_key)}] {entry.name}{extra}：{entry.summary}"]
    for key, label in _FIELD_LABELS.get(type_key, []):
        val = entry.details.get(key)
        if not val:
            continue
        if isinstance(val, list):
            val = "/".join(str(v) for v in val)
        parts.append(f"{label}:{val}")
    return " | ".join(parts)


def build_system_content(agent_config) -> str:
    """构建最终 system 内容 = system_prompt + 【参考设定】块；均无则返回 ''。"""
    base = agent_config.system_prompt or ""
    active_ids = getattr(agent_config, "active_entry_ids", None) or []
    if not active_ids:
        return base
    lines = []
    for eid in active_ids:
        entry = knowledge_entry_store.get(eid)
        if entry is None:
            logger.warning("active_entry_id not found, skipped: %s", eid)
            continue
        lines.append(_render_entry(entry))
    if not lines:
        return base
    block = "【参考设定】\n" + "\n".join(lines)
    return f"{base}\n\n{block}" if base else block
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_knowledge_entry.py -v -k injector`
Expected: PASS（3 tests）

- [ ] **Step 5: 提交**（先展示 diff 待放行）

```bash
git add app/core/knowledge_injector.py tests/test_knowledge_entry.py
git commit -m "feat(kb-entry): 设定自动注入器 build_system_content"
```

---

## Task 5: 工具 — knowledge_entry_lookup + 注册

**Files:**
- Create: `app/tools/knowledge_entry_lookup.py`
- Modify: `app/tools/__init__.py`
- Modify: `tests/conftest.py`（`fake_chroma` 补 tool patch 行）
- Test: `tests/test_knowledge_entry.py`（追加 tool 测试）

**Interfaces:**
- Consumes: `BaseAgentTool`；`get_chroma`；collection `kb_structured_entries`
- Produces: `KnowledgeEntryLookupTool`（无参构造）；`BUILTIN_TOOLS["knowledge_entry_lookup"]`；`execute(query="", entry_type="") -> str`，仅返回 scope=public 条目

- [ ] **Step 1: conftest `fake_chroma` 补 tool patch 行**

把 `tests/conftest.py` 中 `fake_chroma` fixture 内注释那行启用（此时 tool 模块已存在）：

```python
@pytest.fixture
def fake_chroma(monkeypatch):
    fake = FakeChroma()
    monkeypatch.setattr("app.services.knowledge_entry_service.get_chroma", lambda: fake)
    monkeypatch.setattr("app.tools.knowledge_entry_lookup.get_chroma", lambda: fake)
    return fake
```

- [ ] **Step 2: 写失败测试**

在 `tests/test_knowledge_entry.py` 末尾追加：

```python
def test_tool_returns_only_public(tmp_path, monkeypatch, fake_chroma):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service
    from app.tools.knowledge_entry_lookup import KnowledgeEntryLookupTool

    knowledge_entry_service.create(  # public
        KnowledgeEntryCreateRequest(type=EntryType.character, scope=EntryScope.public,
                                    name="初音", summary="双马尾歌姬"))
    knowledge_entry_service.create(  # private，工具不应返回
        KnowledgeEntryCreateRequest(type=EntryType.character, scope=EntryScope.private,
                                    user_id="u1", name="我的偏好", summary="私人风格"))

    out = KnowledgeEntryLookupTool().execute(query="歌姬")
    assert "初音" in out
    assert "我的偏好" not in out  # 决策⑦：工具只搜公共库


def test_tool_entry_type_filter(tmp_path, monkeypatch, fake_chroma):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service
    from app.tools.knowledge_entry_lookup import KnowledgeEntryLookupTool
    knowledge_entry_service.create(
        KnowledgeEntryCreateRequest(type=EntryType.style, scope=EntryScope.public,
                                    name="赛博", summary="霓虹"))
    knowledge_entry_service.create(
        KnowledgeEntryCreateRequest(type=EntryType.character, scope=EntryScope.public,
                                    name="初音", summary="歌姬"))
    out = KnowledgeEntryLookupTool().execute(query="x", entry_type="style")
    assert "赛博" in out and "初音" not in out


def test_tool_empty_query_hint():
    from app.tools.knowledge_entry_lookup import KnowledgeEntryLookupTool
    assert KnowledgeEntryLookupTool().execute(query="") == "请提供搜索关键词"


def test_tool_registered_in_builtin():
    from app.tools import BUILTIN_TOOLS
    assert "knowledge_entry_lookup" in BUILTIN_TOOLS
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/test_knowledge_entry.py -v -k "tool or registered"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tools.knowledge_entry_lookup'`（registered 断言也失败）

- [ ] **Step 4: 实现工具**

创建 `app/tools/knowledge_entry_lookup.py`：

```python
"""
结构化条目按需检索工具。

仅检索公共库（scope=public）；私有条目经 Agent.active_entry_ids 自动注入触达（spec §4.3 v1 边界）。
作为 Tool 被 LLM 自主调用；无构造参数（chat_service._get_tools 走 else 分支实例化）。
"""
import logging
from app.tools.base import BaseAgentTool
from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")

_COLLECTION = "kb_structured_entries"
_TYPE_LABEL = {"style": "风格", "character": "角色", "story": "故事"}


class KnowledgeEntryLookupTool(BaseAgentTool):
    def __init__(self):
        super().__init__(
            tool_id="knowledge_entry_lookup",
            name="knowledge_entry_lookup",
            description="在公共设定库中搜索风格/角色/故事等参考设定。"
                        "输入 query 关键词（可选 entry_type: style/character/story），返回最相关条目。",
        )

    def execute(self, query: str = "", entry_type: str = "", **kwargs) -> str:
        query = query or kwargs.get("question", "")
        if not query:
            return "请提供搜索关键词"
        where = {"scope": "public"}
        if entry_type:
            where["type"] = entry_type
        try:
            col = get_chroma().get_collection(name=_COLLECTION)
            res = col.query(query_texts=[query], n_results=3, where=where)
        except Exception as e:
            logger.warning("knowledge_entry_lookup failed: %s", e)
            return "未找到相关信息"
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        if not docs:
            return "未找到相关信息"
        lines = []
        for doc, meta in zip(docs, metas):
            t = _TYPE_LABEL.get(meta.get("type", ""), meta.get("type", ""))
            lines.append(f"[{t}] {doc}")
        return "\n\n---\n\n".join(lines)
```

- [ ] **Step 5: 注册到 BUILTIN_TOOLS**

修改 `app/tools/__init__.py`：imports 加一行、字典加一项：

```python
from app.tools.knowledge_entry_lookup import KnowledgeEntryLookupTool

# 内置工具 id → 实现类
BUILTIN_TOOLS = {
    "calculator": CalculatorTool,
    "web_search": WebSearchTool,
    "knowledge_search": KnowledgeSearchTool,
    "knowledge_entry_lookup": KnowledgeEntryLookupTool,
}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `pytest tests/test_knowledge_entry.py -v`
Expected: PASS（全部，含 4 个 tool 测试）

- [ ] **Step 7: 提交**（先展示 diff 待放行）

```bash
git add app/tools/knowledge_entry_lookup.py app/tools/__init__.py tests/conftest.py tests/test_knowledge_entry.py
git commit -m "feat(kb-entry): 公共库按需检索工具 knowledge_entry_lookup + 注册"
```

---

## Task 6: API — REST + 路由注册

**Files:**
- Create: `app/api/v1/knowledge_entry.py`
- Modify: `app/api/v1/router.py`
- Test: `tests/test_knowledge_entry_api.py`

**Interfaces:**
- Consumes: `knowledge_entry_service`（Task 2）；`Result`
- Produces: 路由 `/api/v1/knowledge-entries`（GET 列表带 `type/scope/user_id/q`、GET/{id}、POST、PUT/{id}、DELETE/{id}）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_knowledge_entry_api.py`：

```python
"""结构化知识条目 API 测试（用 fake_chroma 避免真实 embedding）。"""
import pytest
from app.db.chroma_client import init_chroma, close_chroma


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path, monkeypatch, fake_chroma):
    """每个 API 测试：data_dir 指向临时目录 + 内存 chroma。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_chroma()
    yield
    close_chroma()


@pytest.mark.asyncio
async def test_entry_crud_lifecycle(client, auth_headers):
    resp = await client.post("/api/v1/knowledge-entries", json={
        "type": "character", "scope": "public", "name": "初音",
        "summary": "双马尾歌姬", "tags": ["vocaloid"],
        "details": {"personality": "元气"}}, headers=auth_headers)
    assert resp.json()["code"] == 200
    eid = resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/knowledge-entries/{eid}", headers=auth_headers)
    assert resp.json()["data"]["name"] == "初音"

    resp = await client.get("/api/v1/knowledge-entries?type=character", headers=auth_headers)
    assert len(resp.json()["data"]) == 1
    resp = await client.get("/api/v1/knowledge-entries?type=style", headers=auth_headers)
    assert len(resp.json()["data"]) == 0

    resp = await client.put(f"/api/v1/knowledge-entries/{eid}", json={"name": "Miku"}, headers=auth_headers)
    assert resp.json()["data"]["name"] == "Miku"

    resp = await client.delete(f"/api/v1/knowledge-entries/{eid}", headers=auth_headers)
    assert resp.json()["code"] == 200
    resp = await client.get(f"/api/v1/knowledge-entries/{eid}", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_create_private_without_user_id_400(client, auth_headers):
    resp = await client.post("/api/v1/knowledge-entries", json={
        "type": "style", "scope": "private", "name": "x", "summary": "y"}, headers=auth_headers)
    assert resp.json()["code"] == 400


@pytest.mark.asyncio
async def test_update_with_type_field_rejected(client, auth_headers):
    create = await client.post("/api/v1/knowledge-entries", json={
        "type": "character", "scope": "public", "name": "a", "summary": "b"}, headers=auth_headers)
    eid = create.json()["data"]["id"]
    # type 不在 UpdateRequest + extra=forbid → 422（FastAPI body 校验默认状态码）
    resp = await client.put(f"/api/v1/knowledge-entries/{eid}", json={"type": "story"}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_nonexistent_404(client, auth_headers):
    resp = await client.put("/api/v1/knowledge-entries/ghost", json={"name": "x"}, headers=auth_headers)
    assert resp.json()["code"] == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_knowledge_entry_api.py -v`
Expected: FAIL — 404（路由未注册）

- [ ] **Step 3: 实现路由**

创建 `app/api/v1/knowledge_entry.py`：

```python
"""结构化知识条目 REST API。"""
from typing import Optional
from fastapi import APIRouter

from app.models.common import Result
from app.models.knowledge_entry import (
    KnowledgeEntryCreateRequest, KnowledgeEntryUpdateRequest,
)
from app.services.knowledge_entry_service import knowledge_entry_service

router = APIRouter(tags=["knowledge-entry"])


@router.get("/knowledge-entries")
async def list_knowledge_entries(
    type: Optional[str] = None, scope: Optional[str] = None,
    user_id: Optional[str] = None, q: Optional[str] = None,
):
    return Result.success(data=knowledge_entry_service.list(type, scope, user_id, q))


@router.get("/knowledge-entries/{entry_id}")
async def get_knowledge_entry(entry_id: str):
    entry = knowledge_entry_service.get(entry_id)
    if entry is None:
        return Result.error(code=404, message=f"Knowledge entry not found: {entry_id}")
    return Result.success(data=entry)


@router.post("/knowledge-entries")
async def create_knowledge_entry(body: KnowledgeEntryCreateRequest):
    try:
        entry = knowledge_entry_service.create(body)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    return Result.success(data=entry)


@router.put("/knowledge-entries/{entry_id}")
async def update_knowledge_entry(entry_id: str, body: KnowledgeEntryUpdateRequest):
    try:
        entry = knowledge_entry_service.update(entry_id, body)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    if entry is None:
        return Result.error(code=404, message=f"Knowledge entry not found: {entry_id}")
    return Result.success(data=entry)


@router.delete("/knowledge-entries/{entry_id}")
async def delete_knowledge_entry(entry_id: str):
    if not knowledge_entry_service.delete(entry_id):
        return Result.error(code=404, message=f"Knowledge entry not found: {entry_id}")
    return Result.success()
```

- [ ] **Step 4: 注册路由**

修改 `app/api/v1/router.py`：imports 加 `from app.api.v1.knowledge_entry import router as knowledge_entry_router`，并在 include_router 段（`kb_router` 之后）加 `router.include_router(knowledge_entry_router)`。

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_knowledge_entry_api.py -v`
Expected: PASS（4 tests）

- [ ] **Step 6: 提交**（先展示 diff 待放行）

```bash
git add app/api/v1/knowledge_entry.py app/api/v1/router.py tests/test_knowledge_entry_api.py
git commit -m "feat(kb-entry): 条目 REST API + 路由注册"
```

---

## Task 7: Agent 集成（下）— 注入挂载 chat_service + workflow + 集成测试

**Files:**
- Modify: `app/services/chat_service.py`（`_build_messages`）
- Modify: `app/core/workflow.py`（`stream_workflow`）
- Test: `tests/test_knowledge_entry_injection.py`（新建）

**Interfaces:**
- Consumes: `build_system_content(agent_config)`（Task 4）
- Produces: 三种对话模式（chat/tool_use/workflow）在 `active_entry_ids` 非空时都注入【参考设定】；空时逐字回归

- [ ] **Step 1: 写失败测试**

创建 `tests/test_knowledge_entry_injection.py`：

```python
"""自动注入集成测试：覆盖 chat/tool 路径(_build_messages)与 workflow 路径。"""
from types import SimpleNamespace
from langchain_core.messages import SystemMessage

from app.models.agent import AgentConfig
from app.models.knowledge_entry import KnowledgeEntry, EntryType, EntryScope
from app.db.knowledge_entry_store import knowledge_entry_store


def _llm_cfg():
    return {"provider": "p", "model": "m", "base_url": "u", "api_key": "k"}


def _entry(eid, name, summary, type=EntryType.character):
    return KnowledgeEntry(id=eid, type=type, scope=EntryScope.public,
                          name=name, summary=summary, details={})


def _fake_memory():
    """_build_messages 会调用 memory.load_messages(...)，给一个空记忆桩。"""
    return SimpleNamespace(load_messages=lambda cid: [])


def test_build_messages_injects_when_active(monkeypatch):
    monkeypatch.setattr(knowledge_entry_store, "get",
                        lambda eid: _entry(eid, "初音", "歌姬") if eid == "e1" else None)
    from app.services.chat_service import ChatService
    cfg = AgentConfig(id="a1", name="A", system_prompt="你是助手",
                      active_entry_ids=["e1"], llm_config=_llm_cfg())
    msgs = ChatService()._build_messages(cfg, memory=_fake_memory(),
                                         message="你好", conversation_id="c1", images=None)
    sys = [m for m in msgs if isinstance(m, SystemMessage)]
    assert any("【参考设定】" in m.content and "初音" in m.content for m in sys)


def test_build_messages_zero_regression_when_empty(monkeypatch):
    monkeypatch.setattr(knowledge_entry_store, "get", lambda eid: None)
    from app.services.chat_service import ChatService
    cfg = AgentConfig(id="a1", name="A", system_prompt="你是助手",
                      active_entry_ids=[], llm_config=_llm_cfg())
    msgs = ChatService()._build_messages(cfg, memory=_fake_memory(),
                                         message="你好", conversation_id="c1", images=None)
    sys = [m for m in msgs if isinstance(m, SystemMessage)]
    assert len(sys) == 1 and sys[0].content == "你是助手"


def test_workflow_injects_when_active(monkeypatch):
    monkeypatch.setattr(knowledge_entry_store, "get",
                        lambda eid: _entry(eid, "初音", "歌姬") if eid == "e1" else None)
    from app.core.knowledge_injector import build_system_content
    cfg = AgentConfig(id="a1", name="A", system_prompt="你是助手",
                      capabilities=["workflow"], active_entry_ids=["e1"], llm_config=_llm_cfg())
    # workflow 路径的注入文本由 build_system_content 决定（避免真实调 LLM）
    content = build_system_content(cfg)
    assert "【参考设定】" in content and "初音" in content
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_knowledge_entry_injection.py -v`
Expected: FAIL — `chat_service._build_messages` 仍用裸 `system_prompt`，无【参考设定】

- [ ] **Step 3: 改 chat_service**

修改 `app/services/chat_service.py`：
- 顶部 import 加 `from app.core.knowledge_injector import build_system_content`
- `_build_messages` 中把
  ```python
  if agent_config.system_prompt:
      messages.append(SystemMessage(content=agent_config.system_prompt))
  ```
  改为
  ```python
  sys_content = build_system_content(agent_config)
  if sys_content:
      messages.append(SystemMessage(content=sys_content))
  ```

- [ ] **Step 4: 改 workflow**

修改 `app/core/workflow.py` `stream_workflow` 中（约 120-121 行）把
```python
if self.agent_config.system_prompt:
    messages.append(SystemMessage(content=self.agent_config.system_prompt))
```
改为
```python
from app.core.knowledge_injector import build_system_content
sys_content = build_system_content(self.agent_config)
if sys_content:
    messages.append(SystemMessage(content=sys_content))
```
（局部 import 与该文件现有 `from app.models.chat import ...` 局部 import 风格一致。）

- [ ] **Step 5: 跑全部测试确认通过且不回归**

Run: `pytest -v`
Expected: PASS（全量，含新增注入测试；现有 chat/workflow/agent 测试不回归）

- [ ] **Step 6: 提交**（先展示 diff 待放行）

```bash
git add app/services/chat_service.py app/core/workflow.py tests/test_knowledge_entry_injection.py
git commit -m "feat(kb-entry): 设定自动注入挂载 chat_service + workflow 两路径"
```

---

## 收尾（全部任务完成后）

1. **跑 `/code-review`**（当前 diff，项目硬规矩），按结果修复并单独提交（中文 message）。
2. **写变更记录**到 `docs/changelogs/2026-07-07-knowledge-base.zh.md`（复数目录，参照同目录既有 changelog 体例），并提交。
3. 向用户汇报：新增文件清单、修改点、测试通过数、code-review 结论。
