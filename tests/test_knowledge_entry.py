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
