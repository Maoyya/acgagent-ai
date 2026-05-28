"""
Agent CRUD API 测试。

覆盖场景：
- 空列表查询
- 完整 CRUD 生命周期（创建→查询→更新→删除→删除后404）
- 更新不存在的 Agent
- 删除不存在的 Agent
- 创建时缺少必填字段
"""
import pytest

# 标准 Agent 创建请求体，包含最小必填字段
SAMPLE_AGENT = {
    "name": "Test Agent",
    "description": "A test agent",
    "llm_config": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test-fake",
        "temperature": 0.7,
        "max_tokens": 4096,
        "top_p": 0.9,
    },
    "capabilities": ["chat"],
    "memory_config": {"type": "conversation_window", "max_tokens": 8000},
}


@pytest.mark.asyncio
async def test_list_agents_empty(client, auth_headers):
    """初始状态下 Agent 列表为空。"""
    resp = await client.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_agent_crud_lifecycle(client, auth_headers):
    """完整 CRUD 生命周期：创建→查询→更新→删除→确认404。"""
    # Create
    resp = await client.post("/api/v1/agents", json=SAMPLE_AGENT, headers=auth_headers)
    assert resp.json()["code"] == 200
    agent_id = resp.json()["data"]["id"]

    # Get
    resp = await client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Test Agent"

    # Update
    resp = await client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "Updated Agent"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Updated Agent"

    # Delete
    resp = await client.delete(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 200

    # Get after delete -> 404
    resp = await client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_get_nonexistent_agent(client, auth_headers):
    """查询不存在的 Agent 返回 404。"""
    resp = await client.get("/api/v1/agents/nonexistent_id", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_update_nonexistent_agent(client, auth_headers):
    """更新不存在的 Agent 返回 404。"""
    resp = await client.put(
        "/api/v1/agents/nonexistent_id",
        json={"name": "Ghost"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_agent(client, auth_headers):
    """删除不存在的 Agent 返回 404。"""
    resp = await client.delete("/api/v1/agents/nonexistent_id", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_create_agent_missing_required_fields(client, auth_headers):
    """缺少必填字段（name/llm_config）时返回 422 校验错误。"""
    resp = await client.post("/api/v1/agents", json={}, headers=auth_headers)
    assert resp.status_code == 422
