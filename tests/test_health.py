"""
健康检查和认证测试。

验证：
- /health 端点无需认证即可访问
- v1 路由未携带 API Key 时返回 401
- 无效 API Key 返回 401
"""
import pytest


@pytest.mark.asyncio
async def test_health_no_auth(client):
    """健康检查端点无需 API Key，返回 healthy 状态和版本号。"""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_api_key_required_for_v1(client):
    """v1 路由不携带 X-API-Key Header 时应被拒绝。"""
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_api_key(client):
    """携带错误 API Key 时返回 401。"""
    resp = await client.get(
        "/api/v1/agents",
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401
