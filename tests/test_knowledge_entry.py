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


import pytest
from pydantic import ValidationError
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
    docs = fake_chroma.collections[_COLLECTION].docs
    assert entry.id in docs
    # 证明向量内容随 update 刷新（name A→B → embedding 文本含 B），而非仅靠 create 写入兜过
    assert "B" in docs[entry.id]["document"]

    assert knowledge_entry_service.delete(entry.id) is True
    assert entry.id not in fake_chroma.collections[_COLLECTION].docs
    # 合法格式但不存在的 entry_id → update 返回 None（非法格式已由 _validate_entry_id 拦截 → ValueError）
    assert knowledge_entry_service.update("000000000000", KnowledgeEntryUpdateRequest(name="x")) is None


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


# --- 安全硬化：path traversal 纵深防御 + entry_id 格式校验 + user_id 不可变 ---


def test_store_path_sanitizes_traversal(tmp_path, monkeypatch):
    """_path 必须剥掉任何目录/`..` 组件，解析后父目录仍是 _dir()（无逃逸、无子目录）。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.db.knowledge_entry_store import knowledge_entry_store
    base = knowledge_entry_store._dir().resolve()

    # 各类恶意/异常 entry_id：解析后父目录必须仍是 _dir()
    for bad in ("../evil", "a/b", "..%2fevil"):
        p = knowledge_entry_store._path(bad)
        assert ".." not in p.parts
        assert p.resolve().parent == base

    # 明确坍缩为纯文件名
    assert knowledge_entry_store._path("../evil").name == "evil.json"
    assert knowledge_entry_store._path("a/b").name == "b.json"


def test_service_rejects_invalid_entry_id(tmp_path, monkeypatch, fake_chroma):
    """entry_id 必须是 12 位小写 hex；非法格式在 get/update/delete 入口 raise ValueError。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service
    req = KnowledgeEntryUpdateRequest(name="x")
    # 覆盖：含路径 / 过短 / 非hex字符 / 过长
    bad_ids = ["../x", "bad", "ZZZZZZZZZZZZ", "1234567890", "1234567890abc"]
    for bid in bad_ids:
        with pytest.raises(ValueError):
            knowledge_entry_service.get(bid)
        with pytest.raises(ValueError):
            knowledge_entry_service.update(bid, req)
        with pytest.raises(ValueError):
            knowledge_entry_service.delete(bid)


def test_service_accepts_valid_entry_id(tmp_path, monkeypatch, fake_chroma):
    """合法 12 位 hex id 不应因校验抛错（条目不存在则返回 None/False）。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service
    assert knowledge_entry_service.get("1234567890ab") is None
    assert knowledge_entry_service.update("1234567890ab", KnowledgeEntryUpdateRequest(name="x")) is None
    assert knowledge_entry_service.delete("1234567890ab") is False


def test_update_request_forbids_user_id():
    """user_id 不可经 update 修改：传该字段 → ValidationError（extra=forbid）。"""
    with pytest.raises(ValidationError):
        KnowledgeEntryUpdateRequest(user_id="attacker")


def test_service_update_does_not_mutate_user_id(tmp_path, monkeypatch, fake_chroma):
    """update 其他字段不会重置 user_id（所有权不可篡改）。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services.knowledge_entry_service import knowledge_entry_service
    entry = knowledge_entry_service.create(_req(scope=EntryScope.private, user_id="user1"))
    updated = knowledge_entry_service.update(entry.id, KnowledgeEntryUpdateRequest(name="new"))
    assert updated is not None
    assert updated.user_id == "user1"


# --- Task 4: 注入器 build_system_content ---

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


# --- Task 5: 公共库按需检索工具 ---

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
