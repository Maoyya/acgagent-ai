import pytest
from app.db.chroma_client import init_chroma, close_chroma


@pytest.fixture(autouse=True)
def setup_chroma():
    init_chroma()
    yield
    close_chroma()


SAMPLE_KB = {
    "name": "Test KB",
    "description": "A test knowledge base",
}


@pytest.mark.asyncio
async def test_kb_crud_lifecycle(client, auth_headers):
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
