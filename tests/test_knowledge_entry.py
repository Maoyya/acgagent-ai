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
