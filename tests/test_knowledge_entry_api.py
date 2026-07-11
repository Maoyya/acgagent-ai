"""结构化知识条目 API 测试（用 fake_chroma 避免真实 embedding）。"""
import pytest
from app.db.chroma_client import init_chroma, close_chroma


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path, monkeypatch, fake_chroma):
    """每个 API 测试：data_dir 指向临时目录 + 内存 chroma。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_chroma()
    yield
    close_chroma()


@pytest.mark.asyncio
async def test_entry_crud_lifecycle(client, auth_headers):
    resp = await client.post("/api/v1/knowledge-entries", json={
        "type": "character", "scope": "public", "name": "初音",
        "summary": "双马尾歌姬", "tags": ["vocaloid"],
        "details": {"personality": "元气"}}, headers=auth_headers)
    assert resp.json()["code"] == 200
    eid = resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/knowledge-entries/{eid}", headers=auth_headers)
    assert resp.json()["data"]["name"] == "初音"

    resp = await client.get("/api/v1/knowledge-entries?type=character", headers=auth_headers)
    assert len(resp.json()["data"]) == 1
    resp = await client.get("/api/v1/knowledge-entries?type=style", headers=auth_headers)
    assert len(resp.json()["data"]) == 0

    resp = await client.put(f"/api/v1/knowledge-entries/{eid}", json={"name": "Miku"}, headers=auth_headers)
    assert resp.json()["data"]["name"] == "Miku"

    resp = await client.delete(f"/api/v1/knowledge-entries/{eid}", headers=auth_headers)
    assert resp.json()["code"] == 200
    resp = await client.get(f"/api/v1/knowledge-entries/{eid}", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_create_private_without_user_id_400(client, auth_headers):
    resp = await client.post("/api/v1/knowledge-entries", json={
        "type": "style", "scope": "private", "name": "x", "summary": "y"}, headers=auth_headers)
    assert resp.json()["code"] == 400


@pytest.mark.asyncio
async def test_update_with_type_field_rejected(client, auth_headers):
    create = await client.post("/api/v1/knowledge-entries", json={
        "type": "character", "scope": "public", "name": "a", "summary": "b"}, headers=auth_headers)
    eid = create.json()["data"]["id"]
    # type 不在 UpdateRequest + extra=forbid → 422（FastAPI body 校验默认状态码）
    resp = await client.put(f"/api/v1/knowledge-entries/{eid}", json={"type": "story"}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_nonexistent_404(client, auth_headers):
    # 使用合法格式（12 位 hex）但不存在的 id，命中 service.update 的 None 分支 → 404。
    # 注：brief 原文用 "ghost"，但 service._validate_entry_id 严格匹配 [0-9a-f]{12}，
    # "ghost" 会 raise ValueError → 路由返回 400 而非 404（brief 测试与 route 代码自相矛盾）。
    # 按 controller 注解的意图（"update 不存在 → None → 404"）改用合法 hex id。
    resp = await client.put("/api/v1/knowledge-entries/deadbeef0000", json={"name": "x"}, headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_get_invalid_id_format_400(client, auth_headers):
    """非法 entry_id 格式 → service._validate_entry_id 抛 ValueError → 路由 400（信封一致，非裸 500）。"""
    resp = await client.get("/api/v1/knowledge-entries/ghost", headers=auth_headers)
    assert resp.json()["code"] == 400


@pytest.mark.asyncio
async def test_update_invalid_id_format_400(client, auth_headers):
    """update 非法 id → 400（区别于合法但不存在 id 的 404）。"""
    resp = await client.put("/api/v1/knowledge-entries/ghost", json={"name": "x"}, headers=auth_headers)
    assert resp.json()["code"] == 400


@pytest.mark.asyncio
async def test_delete_invalid_id_format_400(client, auth_headers):
    """delete 非法 id → 400（信封一致，非裸 500）。"""
    resp = await client.delete("/api/v1/knowledge-entries/ghost", headers=auth_headers)
    assert resp.json()["code"] == 400
