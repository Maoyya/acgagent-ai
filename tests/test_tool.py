import pytest


@pytest.mark.asyncio
async def test_list_tools_includes_builtins(client, auth_headers):
    resp = await client.get("/api/v1/tools", headers=auth_headers)
    assert resp.json()["code"] == 200
    data = resp.json()["data"]
    ids = [t["id"] for t in data]
    assert "calculator" in ids
    assert "web_search" in ids


@pytest.mark.asyncio
async def test_create_and_delete_custom_tool(client, auth_headers):
    resp = await client.post("/api/v1/tools", json={
        "name": "天气查询",
        "description": "查询天气",
        "type": "api",
        "config": {"url": "https://api.weather.com/v1", "method": "GET"},
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    }, headers=auth_headers)
    assert resp.json()["code"] == 200
    tool_id = resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/tools/{tool_id}", headers=auth_headers)
    assert resp.json()["data"]["name"] == "天气查询"

    resp = await client.delete(f"/api/v1/tools/{tool_id}", headers=auth_headers)
    assert resp.json()["code"] == 200


@pytest.mark.asyncio
async def test_cannot_delete_builtin(client, auth_headers):
    resp = await client.delete("/api/v1/tools/calculator", headers=auth_headers)
    assert resp.json()["code"] == 404
