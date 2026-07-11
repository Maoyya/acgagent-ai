"""
测试公共 fixtures。

- client: 基于 httpx.AsyncClient + ASGITransport 的 FastAPI 测试客户端
- api_key: 从配置读取的 API Key
- auth_headers: 携带 X-API-Key 的认证请求头
"""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.config import settings


@pytest.fixture
def api_key() -> str:
    return settings.api_key


@pytest.fixture
def auth_headers(api_key: str) -> dict:
    return {"X-API-Key": api_key}


@pytest.fixture
async def client():
    """创建异步测试客户端，直接调用 FastAPI 应用（不走网络）。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class _FakeCollection:
    def __init__(self):
        self.docs = {}  # id -> {"document":..., "metadata":...}

    def upsert(self, ids, documents, metadatas):
        for i, d, m in zip(ids, documents, metadatas):
            self.docs[i] = {"document": d, "metadata": m}

    def delete(self, ids):
        for i in ids:
            self.docs.pop(i, None)

    def query(self, query_texts, n_results=3, where=None):
        items = list(self.docs.values())
        if where:
            items = [it for it in items
                     if all(it["metadata"].get(k) == v for k, v in where.items())]
        items = items[:n_results]
        return {
            "documents": [[it["document"] for it in items]],
            "metadatas": [[it["metadata"] for it in items]],
        }


class FakeChroma:
    """内存版 ChromaDB，避免测试触发真实 ONNX embedding 下载。"""
    def __init__(self):
        self.collections = {}

    def get_or_create_collection(self, name, metadata=None):
        return self.collections.setdefault(name, _FakeCollection())

    def get_collection(self, name):
        if name not in self.collections:
            raise Exception(f"collection {name} not found")
        return self.collections[name]


@pytest.fixture
def fake_chroma(monkeypatch):
    """patch 各消费模块已绑定的 get_chroma 名字，返回共享 FakeChroma。"""
    fake = FakeChroma()
    monkeypatch.setattr("app.services.knowledge_entry_service.get_chroma", lambda: fake)
    # Task 5 在此追加：monkeypatch.setattr("app.tools.knowledge_entry_lookup.get_chroma", lambda: fake)
    return fake
