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
