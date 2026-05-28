"""
对话 API 测试。

覆盖场景：
- 缺少 message 字段的请求体校验
- 对话不存在的 Agent 返回 404
- 对话已禁用的 Agent 返回 400
- 同步/流式模式切换
"""
import pytest


@pytest.mark.asyncio
async def test_chat_missing_message(client, auth_headers):
    """请求体缺少 message 字段时返回 422 校验错误。"""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_sync_agent_not_found(client, auth_headers):
    """同步对话不存在的 Agent 返回业务层 404。"""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404


@pytest.mark.asyncio
async def test_chat_stream_agent_not_found(client, auth_headers):
    """流式对话不存在的 Agent 也返回 404（非 SSE）。"""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={"message": "hello", "stream": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404


@pytest.mark.asyncio
async def test_chat_disabled_agent(client, auth_headers):
    """对话已禁用的 Agent（status=0）返回 400。"""
    # 创建 Agent
    resp = await client.post("/api/v1/agents", json={
        "name": "Disabled Agent",
        "llm_config": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-test",
            "temperature": 0.7,
        },
    }, headers=auth_headers)
    agent_id = resp.json()["data"]["id"]

    # 禁用 Agent
    await client.put(
        f"/api/v1/agents/{agent_id}",
        json={"status": 0},
        headers=auth_headers,
    )

    # 尝试对话
    resp = await client.post(
        f"/api/v1/chat/{agent_id}/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400
