"""
API 鉴权边界测试：合法 key / 缺失 key / 错误 key。
"""
import pytest


@pytest.mark.asyncio
async def test_protected_with_valid_key(client, auth_headers):
    """合法 key 访问受保护端点返回 200。"""
    resp = await client.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_without_key_returns_401(client):
    """缺失 X-API-Key 返回 401（加固前为 422）。"""
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_with_wrong_key_returns_401(client):
    """错误的 X-API-Key 返回 401。"""
    resp = await client.get("/api/v1/agents", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401
