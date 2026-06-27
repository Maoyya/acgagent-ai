"""Agent 创建/更新可用性校验端到端测试（经 HTTP，mock ping_llm）。

锁定意图（Rule 9）：
- ping 失败 → 400 且 Agent 未落库（不可用不入库）。
- validate=false 豁免 ping（逃生口），但引用校验不豁免。
- 更新=完整复检：即使只改 name 也触发 ping；失败则旧值不变（原子）。
"""
import pytest

VALID_LLM = {
    "provider": "deepseek", "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "sk-test", "temperature": 0.7,
}


def _ping_raises(monkeypatch, msg="Agent LLM 不可用: API Key 鉴权失败"):
    """让 agent_service 内的 ping_llm 抛 ValueError。"""
    def _fail(*a, **kw):
        raise ValueError(msg)
    monkeypatch.setattr("app.services.agent_service.ping_llm", _fail)


def _ping_succeeds_counting(monkeypatch):
    """让 ping_llm 成功并计数（验证是否被调用）。"""
    counter = {"n": 0}

    def _ok(*a, **kw):
        counter["n"] += 1
    monkeypatch.setattr("app.services.agent_service.ping_llm", _ok)
    return counter


@pytest.mark.asyncio
async def test_create_rejected_when_ping_fails(client, auth_headers, monkeypatch):
    """ping 失败 → 400 且 Agent 未落库。"""
    _ping_raises(monkeypatch)
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "NoSave", "llm_config": VALID_LLM},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400
    assert "鉴权失败" in resp.json()["message"]
    listing = (await client.get("/api/v1/agents", headers=auth_headers)).json()["data"]
    assert all(a["name"] != "NoSave" for a in listing)


@pytest.mark.asyncio
async def test_create_skips_ping_when_validate_false(client, auth_headers, monkeypatch):
    """validate=false → ping 不被调用：把 ping mock 成必抛，validate=false 下仍应创建成功。"""
    _ping_raises(monkeypatch)  # 若 ping 被调，必抛 → 创建会 400
    resp = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "Skipped", "llm_config": VALID_LLM},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200  # ping 没被调，所以没抛


@pytest.mark.asyncio
async def test_create_rejected_when_kb_not_found_even_with_validate_false(client, auth_headers, monkeypatch):
    """validate=false 也不豁免引用校验：不存在的 kb → 400。"""
    resp = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "BadRef", "llm_config": VALID_LLM, "knowledge_base_ids": ["no-such-kb"]},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400
    assert "no-such-kb" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_accepts_builtin_tool(client, auth_headers, monkeypatch):
    """内置 tool_id 合法 → 创建成功（validate=false）。"""
    resp = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "Builtin", "llm_config": VALID_LLM, "tool_ids": ["calculator"]},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200


@pytest.mark.asyncio
async def test_update_full_revalidate_triggers_ping(client, auth_headers, monkeypatch):
    """更新即使只改 name 也触发完整复检（ping 被调用一次）。"""
    create = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "Old", "llm_config": VALID_LLM},
        headers=auth_headers,
    )
    agent_id = create.json()["data"]["id"]
    counter = _ping_succeeds_counting(monkeypatch)
    resp = await client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "New"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200
    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_update_rejected_when_ping_fails_keeps_old(client, auth_headers, monkeypatch):
    """更新 ping 失败 → 400 且 Agent 配置仍是旧值（未 save）。"""
    create = await client.post(
        "/api/v1/agents?validate=false",
        json={"name": "Keep", "llm_config": VALID_LLM},
        headers=auth_headers,
    )
    agent_id = create.json()["data"]["id"]
    _ping_raises(monkeypatch)
    resp = await client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "Changed"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400
    got = (await client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)).json()["data"]
    assert got["name"] == "Keep"  # 旧值未变
