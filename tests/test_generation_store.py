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
