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


@pytest.mark.asyncio
async def test_chat_missing_llm_key_returns_500_envelope(client, auth_headers, monkeypatch):
    """Agent 的 LLM key 无法解析时（api_key 空 + Settings 无对应 key），返回 Result.error(500) 信封，
    而不是让 ValueError 裸奔成无信封 500、或流式中途崩溃。

    为什么重要：resolve_api_key 的 fail-loud ValueError 必须被 chat 层在分流前转成受控错误，
    覆盖流式/同步（及 workflow）路径（C1/C2）。
    """
    from app.config import settings
    monkeypatch.setattr(settings, "llm_key_deepseek", "")  # 确保无可解析 key

    resp = await client.post("/api/v1/agents", json={
        "name": "No-Key Agent",
        "llm_config": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "",            # 留空 → 依赖 Settings（也为空）→ resolve_api_key 必抛
            "temperature": 0.7,
        },
    }, headers=auth_headers)
    agent_id = resp.json()["data"]["id"]

    # 同步：应返回 code=500 信封（而非裸 500）
    resp = await client.post(
        f"/api/v1/chat/{agent_id}/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 500

    # 流式：同样应在分流前预检，返回 code=500 信封（而非 SSE 中途崩溃）
    resp = await client.post(
        f"/api/v1/chat/{agent_id}/completions",
        json={"message": "hello", "stream": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 500
    # C2 意图：必须是 JSON 信封（application/json），而非 SSE 流（text/event-stream）。
    # 预检若被移除，stream 分支会返回 StreamingResponse（恒 200），失败要到 SSE 中途才暴露——
    # 此断言把"在分流前拦下"这一意图锁定下来（Rule 9：业务逻辑变了测试要能失败）。
    assert resp.headers["content-type"].startswith("application/json")
