"""
知识库 CRUD API 测试。

覆盖场景：
- 完整 CRUD 生命周期（创建→查询→列表→更新→删除→确认404）
- 查询/更新/删除不存在的知识库
- 创建时使用自定义 Embedding 和分块配置
"""
import pytest
from app.db.chroma_client import init_chroma, close_chroma


@pytest.fixture(autouse=True)
def setup_chroma():
    """每个测试前后初始化和清理 ChromaDB。"""
    init_chroma()
    yield
    close_chroma()


SAMPLE_KB = {
    "name": "Test KB",
    "description": "A test knowledge base",
}


@pytest.mark.asyncio
async def test_kb_crud_lifecycle(client, auth_headers):
    """完整 CRUD 生命周期。"""
    # Create
    resp = await client.post("/api/v1/knowledge-bases", json=SAMPLE_KB, headers=auth_headers)
    assert resp.json()["code"] == 200
    kb_id = resp.json()["data"]["id"]
    assert kb_id

    # Get
    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Test KB"

    # List
    resp = await client.get("/api/v1/knowledge-bases", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert len(resp.json()["data"]) >= 1

    # Update
    resp = await client.put(f"/api/v1/knowledge-bases/{kb_id}", json={"name": "Updated KB"}, headers=auth_headers)
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Updated KB"

    # Delete
    resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}", headers=auth_headers)
    assert resp.json()["code"] == 200

    # Get after delete
    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_get_nonexistent_kb(client, auth_headers):
    """查询不存在的知识库返回 404。"""
    resp = await client.get("/api/v1/knowledge-bases/nonexistent", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_update_nonexistent_kb(client, auth_headers):
    """更新不存在的知识库返回 404。"""
    resp = await client.put(
        "/api/v1/knowledge-bases/nonexistent",
        json={"name": "Ghost KB"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_kb(client, auth_headers):
    """删除不存在的知识库返回 404。"""
    resp = await client.delete("/api/v1/knowledge-bases/nonexistent", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_create_kb_with_custom_config(client, auth_headers):
    """创建知识库时使用自定义 Embedding 和分块配置。"""
    resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "Custom KB",
        "description": "With custom config",
        "embedding_config": {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
        },
        "chunk_config": {
            "chunk_size": 1000,
            "chunk_overlap": 100,
            "separators": ["\n\n", "\n"],
        },
    }, headers=auth_headers)
    assert resp.json()["code"] == 200
    kb = resp.json()["data"]
    assert kb["embedding_config"]["model"] == "text-embedding-3-small"
    assert kb["chunk_config"]["chunk_size"] == 1000
