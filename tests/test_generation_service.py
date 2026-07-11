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
