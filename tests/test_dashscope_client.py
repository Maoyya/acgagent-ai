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
