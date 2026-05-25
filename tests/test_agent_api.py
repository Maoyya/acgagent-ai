import pytest

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
    resp = await client.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_agent_crud_lifecycle(client, auth_headers):
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
