from app.models.common import Result


async def test_create_image_returns_task_id(client, auth_headers, monkeypatch):
    async def fake_submit(req, user_id):
        return Result.success({"task_id": "t-1"})

    monkeypatch.setattr(
        "app.api.v1.generation.generation_service.submit_image", fake_submit
    )
    resp = await client.post(
        "/api/v1/generations/images",
        json={"prompt": "cat"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["task_id"] == "t-1"


async def test_create_video_missing_image_url_returns_422(client, auth_headers):
    resp = await client.post(
        "/api/v1/generations/videos",
        json={"prompt": "pan"},  # 缺 image_url
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_get_task_returns_envelope(client, auth_headers, monkeypatch):
    async def fake_get(task_id):
        return Result.success(
            {"id": task_id, "type": "text_to_image", "status": "running",
             "prompt": "...", "output_url": None}
        )

    monkeypatch.setattr("app.api.v1.generation.generation_service.get_task", fake_get)
    resp = await client.get(
        "/api/v1/generations/tasks/t-1", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "running"


async def test_get_task_not_found_body_code_404(client, auth_headers, monkeypatch):
    async def fake_get(task_id):
        return Result.error(404, f"task not found: {task_id}")

    monkeypatch.setattr("app.api.v1.generation.generation_service.get_task", fake_get)
    resp = await client.get(
        "/api/v1/generations/tasks/nope", headers=auth_headers
    )
    assert resp.status_code == 200  # 业务错误走 body code
    assert resp.json()["code"] == 404


async def test_endpoints_require_api_key(client):
    resp = await client.post(
        "/api/v1/generations/images", json={"prompt": "cat"}
    )
    assert resp.status_code == 401
