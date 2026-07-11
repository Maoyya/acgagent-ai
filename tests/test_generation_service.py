# tests/test_generation_service.py
from datetime import datetime

from app.core.dashscope_client import QueryResult
from app.db.generation_store import GenerationStore
from app.models.common import Result
from app.models.generation import (
    GenerationStatus,
    GenerationTask,
    GenerationType,
    ImageGenerationRequest,
)


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
