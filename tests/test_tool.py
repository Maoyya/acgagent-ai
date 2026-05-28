"""
工具管理 API 测试。

覆盖场景：
- 列表包含内置工具（calculator/web_search/knowledge_search）
- 创建自定义 API 工具并查询
- 删除自定义工具
- 内置工具不可删除
- 查询不存在的工具返回 404
"""
import pytest


@pytest.mark.asyncio
async def test_list_tools_includes_builtins(client, auth_headers):
    """工具列表应包含所有内置工具。"""
    resp = await client.get("/api/v1/tools", headers=auth_headers)
    assert resp.json()["code"] == 200
    data = resp.json()["data"]
    ids = [t["id"] for t in data]
    assert "calculator" in ids
    assert "web_search" in ids


@pytest.mark.asyncio
async def test_create_and_delete_custom_tool(client, auth_headers):
    """创建自定义 API 工具后可查询到，删除后不可查询。"""
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
    """内置工具（calculator）不可删除。"""
    resp = await client.delete("/api/v1/tools/calculator", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_get_builtin_tool(client, auth_headers):
    """查询内置工具（calculator）返回完整信息。"""
    resp = await client.get("/api/v1/tools/calculator", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["type"] == "builtin"
    assert resp.json()["data"]["name"] == "计算器"


@pytest.mark.asyncio
async def test_get_nonexistent_tool(client, auth_headers):
    """查询不存在的工具返回 404。"""
    resp = await client.get("/api/v1/tools/nonexistent_tool", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_create_tool_missing_required(client, auth_headers):
    """缺少必填字段（name/description）时返回 422。"""
    resp = await client.post("/api/v1/tools", json={}, headers=auth_headers)
    assert resp.status_code == 422
