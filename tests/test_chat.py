import pytest


@pytest.mark.asyncio
async def test_chat_missing_message(client, auth_headers):
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_sync_agent_not_found(client, auth_headers):
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404
