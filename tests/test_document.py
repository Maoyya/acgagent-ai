import pytest
from app.db.chroma_client import init_chroma, close_chroma


@pytest.fixture(autouse=True)
def setup_chroma():
    init_chroma()
    yield
    close_chroma()


@pytest.mark.asyncio
async def test_upload_and_list_documents(client, auth_headers):
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
    resp = await client.post(
        "/api/v1/knowledge-bases/nonexistent/documents",
        files={"file": ("test.txt", b"content", "text/plain")},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 404
