"""
文档管理 API 测试。

覆盖场景：
- 上传文档并验证初始状态为 processing
- 文档列表查询
- 文档删除
- 上传到不存在的知识库返回 404
- 查询/删除不存在的文档
"""
import pytest
from app.db.chroma_client import init_chroma, close_chroma


@pytest.fixture(autouse=True)
def setup_chroma():
    """每个测试前后初始化和清理 ChromaDB。"""
    init_chroma()
    yield
    close_chroma()


@pytest.mark.asyncio
async def test_upload_and_list_documents(client, auth_headers):
    """上传文档后列表中应出现该文档，初始状态为 processing。"""
    resp = await client.post("/api/v1/knowledge-bases", json={"name": "Doc Test KB"}, headers=auth_headers)
    kb_id = resp.json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        files={"file": ("test.txt", b"Hello world.\n\nThis is a test document with some content for chunking.", "text/plain")},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200
    doc_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "processing"
    assert resp.json()["data"]["file_name"] == "test.txt"

    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert len(resp.json()["data"]) >= 1

    resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}", headers=auth_headers)
    assert resp.json()["code"] == 200


@pytest.mark.asyncio
async def test_upload_to_nonexistent_kb(client, auth_headers):
    """上传文档到不存在的知识库返回 404。"""
    resp = await client.post(
        "/api/v1/knowledge-bases/nonexistent/documents",
        files={"file": ("test.txt", b"content", "text/plain")},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_get_nonexistent_document(client, auth_headers):
    """查询不存在的文档返回 404。"""
    # 先创建知识库
    resp = await client.post("/api/v1/knowledge-bases", json={"name": "KB for doc 404"}, headers=auth_headers)
    kb_id = resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents/nonexistent_doc", headers=auth_headers)
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_document(client, auth_headers):
    """删除不存在的文档返回 404。"""
    resp = await client.post("/api/v1/knowledge-bases", json={"name": "KB for del doc"}, headers=auth_headers)
    kb_id = resp.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}/documents/nonexistent_doc", headers=auth_headers)
    assert resp.json()["code"] == 404
