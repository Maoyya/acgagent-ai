import pytest


@pytest.mark.asyncio
async def test_health_no_auth(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_api_key_required_for_v1(client):
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 401 or resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_api_key(client):
    resp = await client.get(
        "/api/v1/agents",
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401
