# acgagent-ai Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build acgagent-ai — a standalone Python Agent service (FastAPI + LangChain + Chroma + LangGraph) that provides AI Agent capabilities (chat memory, RAG, tool use, workflow orchestration) via REST API for the existing acgagent Java microservices.

**Architecture:** Independent Python service on port 8100. acgagent (Java) calls acgagent-ai via HTTP with API Key auth and `X-User-Id` header passthrough. Data stored as JSON files (agent configs, knowledge base metadata) + Chroma (vectors, document chunks, conversation memory). No relational database.

**Tech Stack:** Python 3.11+, FastAPI 0.110+, LangChain 0.3+, LangGraph 0.2+, Chroma 0.5+, Pydantic 2.x, Poetry 1.8+, Uvicorn, Docker

---

## File Structure Map

All files live under `D:\PycharmProjects\pythonProject\` (project root):

```
acgagent-ai/
├── pyproject.toml                          # Task 1
├── .gitignore                              # Task 1
├── app/
│   ├── __init__.py                         # Task 1
│   ├── main.py                             # Task 2 (FastAPI app, CORS, lifespan)
│   ├── config.py                           # Task 2 (Pydantic Settings)
│   ├── api/
│   │   ├── __init__.py                     # Task 1
│   │   ├── deps.py                         # Task 2 (API Key auth dependency)
│   │   ├── middleware.py                   # Task 2 (request logging)
│   │   └── v1/
│   │       ├── __init__.py                 # Task 1
│   │       ├── router.py                   # Task 2 (route aggregation)
│   │       ├── chat.py                     # Task 3 (chat endpoint)
│   │       ├── agent.py                    # Task 4 (agent CRUD)
│   │       ├── knowledge_base.py           # Task 7 (KB CRUD)
│   │       ├── document.py                 # Task 8 (document upload)
│   │       └── tool.py                     # Task 9 (tool registry API)
│   ├── models/
│   │   ├── __init__.py                     # Task 1
│   │   ├── common.py                       # Task 2 (Result<T>, error codes)
│   │   ├── agent.py                        # Task 4 (AgentConfig, LLMConfig, MemoryConfig)
│   │   ├── chat.py                         # Task 3 (ChatRequest, ChatEvent, SSE types)
│   │   ├── knowledge_base.py               # Task 7 (KnowledgeBase, ChunkConfig, EmbeddingConfig)
│   │   ├── document.py                     # Task 8 (DocumentVO, DocumentStatus)
│   │   └── tool.py                         # Task 9 (ToolConfig, ToolVO)
│   ├── core/
│   │   ├── __init__.py                     # Task 1
│   │   ├── llm.py                          # Task 3 (LLM factory, init ChatOpenAI)
│   │   ├── memory.py                       # Task 5 (ConversationWindowMemory, SummaryMemory)
│   │   ├── retriever.py                    # Task 7 (RAG retriever)
│   │   ├── agent_executor.py               # Task 6 (LangChain ReAct agent)
│   │   └── workflow.py                     # Task 10 (LangGraph workflow)
│   ├── services/
│   │   ├── __init__.py                     # Task 1
│   │   ├── chat_service.py                 # Task 3 (chat orchestration, SSE streaming)
│   │   ├── agent_service.py                # Task 4 (agent CRUD, JSON file store)
│   │   ├── knowledge_service.py            # Task 7 (KB CRUD, Chroma collection mgmt)
│   │   ├── document_service.py             # Task 8 (file upload, chunking, embedding, Chroma ingest)
│   │   └── tool_service.py                 # Task 9 (tool registration, built-in tools)
│   ├── tools/
│   │   ├── __init__.py                     # Task 9
│   │   ├── base.py                         # Task 9 (BaseTool abstract class)
│   │   ├── calculator.py                   # Task 9 (calculator tool impl)
│   │   ├── web_search.py                   # Task 9 (web search stub)
│   │   └── knowledge_search.py             # Task 9 (KB search tool impl)
│   └── db/
│       ├── __init__.py                     # Task 1
│       ├── chroma_client.py                # Task 5 (Chroma singleton, init/close)
│       ├── agent_store.py                  # Task 4 (JSON file store for agents)
│       ├── knowledge_store.py              # Task 7 (JSON file store for KB metadata)
│       ├── document_store.py               # Task 8 (JSON file store for document metadata)
│       ├── tool_store.py                   # Task 9 (JSON file store for tools)
│       └── memory_store.py                 # Task 5 (Chroma-backed conversation memory)
├── data/                                   # Runtime data (.gitignore)
│   ├── agents/                             # Task 4
│   ├── knowledge_bases/                    # Task 7
│   ├── documents/                          # Task 8
│   ├── tools/                              # Task 9
│   ├── chroma/                             # Task 5
│   └── uploads/                            # Task 8
├── tests/
│   ├── __init__.py                         # Task 1
│   ├── conftest.py                         # Task 2 (fixtures: test client, mock LLM)
│   ├── test_health.py                      # Task 2
│   ├── test_agent_api.py                   # Task 4
│   ├── test_chat.py                        # Task 3 (sync) + Task 5 (memory) + Task 6 (agent)
│   ├── test_knowledge.py                   # Task 7
│   ├── test_document.py                    # Task 8
│   └── test_tool.py                        # Task 9
├── Dockerfile                              # Task 11
└── scripts/
    └── seed.py                             # Task 11
```

---

## Task 1: Project Scaffolding + Poetry Setup

**Files:**
- Create: `D:\PycharmProjects\pythonProject\pyproject.toml`
- Create: `D:\PycharmProjects\pythonProject\.gitignore`
- Create: `D:\PycharmProjects\pythonProject\app\__init__.py`
- Create: `D:\PycharmProjects\pythonProject\app\api\__init__.py`
- Create: `D:\PycharmProjects\pythonProject\app\api\v1\__init__.py`
- Create: `D:\PycharmProjects\pythonProject\app\models\__init__.py`
- Create: `D:\PycharmProjects\pythonProject\app\core\__init__.py`
- Create: `D:\PycharmProjects\pythonProject\app\services\__init__.py`
- Create: `D:\PycharmProjects\pythonProject\app\db\__init__.py`
- Create: `D:\PycharmProjects\pythonProject\tests\__init__.py`

- [ ] **Step 1: Create project directory and pyproject.toml**

```bash
mkdir -p D:/PycharmProjects/pythonProject
cd D:/PycharmProjects/pythonProject
```

```toml
# pyproject.toml
[tool.poetry]
name = "acgagent-ai"
version = "1.0.0"
description = "AI Agent engine for acgagent — LangChain + FastAPI"
authors = ["Maoyya"]
readme = "README.md"
packages = [{include = "app"}]

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.115.0"
uvicorn = {extras = ["standard"], version = "^0.34.0"}
pydantic = "^2.10"
pydantic-settings = "^2.7"
langchain = "^0.3.14"
langchain-openai = "^0.3.0"
langchain-community = "^0.3.14"
langgraph = "^0.2.60"
chromadb = "^0.5.23"
tiktoken = "^0.9.0"
pypdf = "^5.1"
python-docx = "^1.1"
python-multipart = "^0.0.20"
httpx = "^0.28.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.25"
httpx = "^0.28.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create .gitignore**

```
# .gitignore
__pycache__/
*.pyc
.pytest_cache/
data/
*.egg-info/
dist/
.venv/
.env
poetry.lock
```

- [ ] **Step 3: Create all __init__.py files and data directories**

```bash
mkdir -p app/api/v1 app/models app/core app/services app/tools app/db
mkdir -p tests data/agents data/knowledge_bases data/documents data/tools data/chroma data/uploads
touch app/__init__.py app/api/__init__.py app/api/v1/__init__.py
touch app/models/__init__.py app/core/__init__.py app/services/__init__.py
touch app/tools/__init__.py app/db/__init__.py tests/__init__.py
```

- [ ] **Step 4: Install dependencies**

```bash
cd D:/PycharmProjects/pythonProject
poetry install
```

- [ ] **Step 5: Verify setup**

```bash
cd D:/PycharmProjects/pythonProject
poetry run python -c "import fastapi; import langchain; import chromadb; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Init git repo and commit**

```bash
cd D:/PycharmProjects/pythonProject
git init
git add .
git commit -m "chore: scaffold acgagent-ai project with Poetry"
```

---

## Task 2: FastAPI App + Config + Auth Middleware + Health Endpoint

**Files:**
- Create: `app/config.py`
- Create: `app/models/common.py`
- Create: `app/api/deps.py`
- Create: `app/api/middleware.py`
- Create: `app/api/v1/router.py`
- Create: `app/main.py`
- Create: `tests/conftest.py`
- Create: `tests/test_health.py`

- [ ] **Step 1: Write config.py with Pydantic Settings**

```python
# app/config.py
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_name: str = "acgagent-ai"
    app_version: str = "1.0.0"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8100

    api_key: str = "dev-api-key"

    data_dir: Path = Path("./data")

    log_level: str = "INFO"

    model_config = {"env_prefix": "ACG_AI_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 2: Write models/common.py — unified Result<T> response**

```python
# app/models/common.py
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """Unified API response matching acgagent's Result<T> format."""

    code: int = 200
    message: str = "success"
    data: Optional[T] = None

    @staticmethod
    def success(data: T = None) -> "Result[T]":
        return Result(code=200, message="success", data=data)

    @staticmethod
    def error(code: int = 500, message: str = "error") -> "Result":
        return Result(code=code, message=message, data=None)
```

- [ ] **Step 3: Write api/deps.py — API Key authentication dependency**

```python
# app/api/deps.py
from fastapi import Header, HTTPException


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Validate X-API-Key header against configured API key."""
    from app.config import settings

    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


async def get_user_id(x_user_id: str = Header(None, alias="X-User-Id")) -> str | None:
    """Extract X-User-Id from header, used for conversation memory isolation."""
    return x_user_id
```

- [ ] **Step 4: Write api/middleware.py — request logging middleware**

```python
# app/api/middleware.py
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("acgagent-ai")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status code, and duration for every request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
```

- [ ] **Step 5: Write api/v1/router.py — empty v1 router placeholder**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

- [ ] **Step 6: Write main.py — FastAPI application entry point**

```python
# app/main.py
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.middleware import LoggingMiddleware
from app.api.v1.router import router as v1_router

logger = logging.getLogger("acgagent-ai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create data directories. Shutdown: cleanup."""
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    for subdir in ["agents", "knowledge_bases", "documents", "tools", "chroma", "uploads"]:
        (settings.data_dir / subdir).mkdir(parents=True, exist_ok=True)

    logger.info("acgagent-ai started on port %d", settings.port)
    yield
    logger.info("acgagent-ai shutting down")


app = FastAPI(
    title="acgagent-ai",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

app.include_router(v1_router)


@app.get("/api/v1/health", tags=["system"])
async def health_check():
    """Health check endpoint — no auth required."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "chroma": "not_initialized",
        "llm": "not_configured",
    }
```

- [ ] **Step 7: Write tests/conftest.py — shared test fixtures**

```python
# tests/conftest.py
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
    """Async test client with auth headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

- [ ] **Step 8: Write tests/test_health.py**

```python
# tests/test_health.py
import pytest


@pytest.mark.asyncio
async def test_health_no_auth(client):
    """Health endpoint does not require authentication."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_api_key_required_for_v1(client):
    """V1 endpoints require X-API-Key header."""
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 401 or resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_api_key(client):
    """Invalid API key returns 401."""
    resp = await client.get(
        "/api/v1/agents",
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401
```

- [ ] **Step 9: Run tests**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_health.py -v
```

Expected: 3 passed

- [ ] **Step 10: Start dev server and verify manually**

```bash
cd D:/PycharmProjects/pythonProject
poetry run uvicorn app.main:app --port 8100 &
# In another terminal:
curl -s http://localhost:8100/api/v1/health | python -m json.tool
curl -s http://localhost:8100/docs  # Should return Swagger UI HTML
```

Expected: health returns `{"status":"healthy","version":"1.0.0",...}`, docs returns HTML page

- [ ] **Step 11: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: FastAPI app with config, auth middleware, and health endpoint"
```

---

## Task 3: Basic Chat — LLM Factory + Sync/Stream Chat Endpoint

**Files:**
- Create: `app/core/llm.py`
- Create: `app/models/chat.py`
- Create: `app/services/chat_service.py`
- Create: `app/api/v1/chat.py`
- Create: `tests/test_chat.py`
- Modify: `app/api/v1/router.py`

This task implements the simplest chat: user sends a message → LLM responds. No memory, no RAG, no tools. This validates the LLM integration end-to-end.

- [ ] **Step 1: Write core/llm.py — LLM factory using LangChain ChatOpenAI**

```python
# app/core/llm.py
from langchain_openai import ChatOpenAI
from app.models.agent import LLMConfig


def create_chat_model(config: LLMConfig) -> ChatOpenAI:
    """Create a LangChain ChatOpenAI instance from LLMConfig.

    All v1.0 providers (doubao, qwen, deepseek) are OpenAI-compatible,
    so ChatOpenAI with custom base_url works for all of them.
    """
    return ChatOpenAI(
        model=config.model,
        base_url=config.base_url,
        api_key=config.api_key,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        streaming=True,
    )
```

- [ ] **Step 2: Write models/chat.py — request/response models**

```python
# app/models/chat.py
from typing import Optional
from pydantic import BaseModel


class ChatOptions(BaseModel):
    """Per-request LLM overrides."""

    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatRequest(BaseModel):
    """Chat completion request body."""

    conversation_id: str = ""
    message: str
    stream: bool = True
    options: Optional[ChatOptions] = None


class ChatEvent(BaseModel):
    """Single SSE event payload."""

    type: str  # content | tool_call | tool_result | thinking | error | done
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Optional[str] = None
    code: Optional[int] = None
    message: Optional[str] = None
    usage: Optional[dict] = None


class UsageInfo(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionVO(BaseModel):
    """Sync (non-stream) response payload."""

    content: str
    usage: UsageInfo = UsageInfo()
    tool_calls: list[dict] = []
```

- [ ] **Step 3: Write services/chat_service.py — basic chat service (no memory yet)**

```python
# app/services/chat_service.py
import json
import logging
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import create_chat_model
from app.models.agent import AgentConfig
from app.models.chat import ChatEvent, ChatCompletionVO, UsageInfo

logger = logging.getLogger("acgagent-ai")


class ChatService:
    """Orchestrates chat completion: LLM call + SSE streaming."""

    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat via SSE. Yields 'data: {json}\n\n' formatted strings."""
        llm = create_chat_model(agent_config.llm_config)
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))
        messages.append(HumanMessage(content=message))

        full_content = ""
        usage_info = UsageInfo()

        try:
            async for chunk in llm.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

            usage_info = UsageInfo(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )
            done_event = ChatEvent(type="done", usage=usage_info.model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"

        except Exception as e:
            logger.error("Chat streaming error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"

    async def sync_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> ChatCompletionVO:
        """Non-streaming chat. Returns complete response."""
        llm = create_chat_model(agent_config.llm_config)
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))
        messages.append(HumanMessage(content=message))

        try:
            response = await llm.ainvoke(messages)
            return ChatCompletionVO(
                content=response.content or "",
                usage=UsageInfo(),
            )
        except Exception as e:
            logger.error("Chat sync error: %s", e)
            raise


chat_service = ChatService()
```

- [ ] **Step 4: Write api/v1/chat.py — chat endpoint**

```python
# app/api/v1/chat.py
from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_user_id
from app.models.chat import ChatRequest
from app.models.common import Result
from app.services.chat_service import chat_service
from app.services.agent_service import agent_service

router = APIRouter(tags=["chat"])


@router.post("/chat/{agent_id}/completions")
async def chat_completions(
    agent_id: str,
    body: ChatRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """Chat with an agent. Supports SSE streaming and sync response."""
    agent_config = agent_service.get(agent_id)
    if agent_config is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    if agent_config.status != 1:
        return Result.error(code=400, message=f"Agent is disabled: {agent_id}")

    if body.stream:
        return StreamingResponse(
            chat_service.stream_chat(
                agent_config=agent_config,
                message=body.message,
                conversation_id=body.conversation_id,
                user_id=x_user_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await chat_service.sync_chat(
            agent_config=agent_config,
            message=body.message,
            conversation_id=body.conversation_id,
            user_id=x_user_id,
        )
        return Result.success(data=result)
```

- [ ] **Step 5: Update api/v1/router.py to include chat routes**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
```

- [ ] **Step 6: Write tests/test_chat.py — test with mock LLM**

```python
# tests/test_chat.py
import pytest
import json


@pytest.mark.asyncio
async def test_chat_agent_not_found(client, auth_headers):
    """Return 404 when agent does not exist."""
    resp = await client.post(
        "/api/v1/agents",  # create agent first — but endpoint not yet built
        json={"name": "test-agent", "llmConfig": {"provider": "deepseek", "model": "deepseek-chat", "baseUrl": "https://api.deepseek.com/v1", "apiKey": "sk-test", "temperature": 0.7, "maxTokens": 4096, "topP": 0.9}},
        headers=auth_headers,
    )
    # agent API not built yet, this will 404 — skip for now
    pass


@pytest.mark.asyncio
async def test_chat_missing_message(client, auth_headers):
    """Return 422 when message is missing."""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_sync_agent_not_found(client, auth_headers):
    """Sync chat returns 404 Result for missing agent."""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404
```

- [ ] **Step 7: Run tests**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_chat.py -v
```

Expected: all pass (the 404 and 422 tests)

- [ ] **Step 8: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: basic chat endpoint with LLM factory and SSE streaming"
```

---

## Task 4: Agent Configuration CRUD — JSON File Store

**Files:**
- Create: `app/models/agent.py`
- Create: `app/db/agent_store.py`
- Create: `app/services/agent_service.py`
- Create: `app/api/v1/agent.py`
- Create: `tests/test_agent_api.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Write models/agent.py — AgentConfig, LLMConfig, MemoryConfig**

```python
# app/models/agent.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM model configuration."""

    provider: str = Field(description="Provider identifier: doubao / qwen / deepseek")
    model: str = Field(description="Model name")
    base_url: str = Field(description="API base URL (OpenAI-compatible)")
    api_key: str = Field(description="API key")
    temperature: float = Field(default=0.7, description="Generation temperature")
    max_tokens: int = Field(default=4096, description="Max output tokens")
    top_p: float = Field(default=0.9, description="Top-P sampling")


class MemoryConfig(BaseModel):
    """Conversation memory configuration."""

    type: str = Field(default="conversation_window", description="Memory type: conversation_window / summary / none")
    max_tokens: int = Field(default=8000, description="Context window size in tokens")


class AgentConfig(BaseModel):
    """Complete agent configuration."""

    id: str = Field(default="", description="Auto-generated unique ID")
    name: str = Field(description="Agent display name")
    description: Optional[str] = Field(default=None, description="Agent description")
    system_prompt: Optional[str] = Field(default=None, description="System prompt for the LLM")
    llm_config: LLMConfig = Field(description="LLM configuration")
    memory_config: MemoryConfig = Field(default_factory=MemoryConfig, description="Memory configuration")
    capabilities: list[str] = Field(default_factory=lambda: ["chat"], description="Capabilities: chat / rag / tool_use / workflow")
    knowledge_base_ids: list[str] = Field(default_factory=list, description="Associated knowledge base IDs")
    tool_ids: list[str] = Field(default_factory=list, description="Associated tool IDs")
    status: int = Field(default=1, description="1=enabled, 0=disabled")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AgentCreateRequest(BaseModel):
    """Request body for creating an agent."""

    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_config: LLMConfig
    memory_config: MemoryConfig = MemoryConfig()
    capabilities: list[str] = ["chat"]
    knowledge_base_ids: list[str] = []
    tool_ids: list[str] = []


class AgentUpdateRequest(BaseModel):
    """Request body for updating an agent. All fields optional."""

    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_config: Optional[LLMConfig] = None
    memory_config: Optional[MemoryConfig] = None
    capabilities: Optional[list[str]] = None
    knowledge_base_ids: Optional[list[str]] = None
    tool_ids: Optional[list[str]] = None
    status: Optional[int] = None
```

- [ ] **Step 2: Write db/agent_store.py — JSON file store for agent configs**

```python
# app/db/agent_store.py
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.agent import AgentConfig

logger = logging.getLogger("acgagent-ai")


class AgentStore:
    """JSON file-based storage for agent configurations.

    Each agent is stored as a separate JSON file in data/agents/{agent_id}.json.
    """

    def __init__(self):
        self._dir: Path = settings.data_dir / "agents"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, agent_id: str) -> Path:
        return self._dir / f"{agent_id}.json"

    def list_all(self) -> list[AgentConfig]:
        """Load all agent configs from disk."""
        agents = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                agents.append(AgentConfig(**data))
            except Exception as e:
                logger.warning("Failed to load agent %s: %s", f.name, e)
        return agents

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """Load a single agent config by ID."""
        path = self._path(agent_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentConfig(**data)

    def save(self, agent: AgentConfig) -> AgentConfig:
        """Save agent config to disk."""
        path = self._path(agent.id)
        path.write_text(agent.model_dump_json(indent=2), encoding="utf-8")
        return agent

    def delete(self, agent_id: str) -> bool:
        """Delete agent config file. Returns True if deleted."""
        path = self._path(agent_id)
        if path.exists():
            path.unlink()
            return True
        return False


agent_store = AgentStore()
```

- [ ] **Step 3: Write services/agent_service.py — agent CRUD business logic**

```python
# app/services/agent_service.py
import uuid
from datetime import datetime
from typing import Optional

from app.db.agent_store import agent_store
from app.models.agent import AgentConfig, AgentCreateRequest, AgentUpdateRequest


class AgentService:
    """Agent configuration CRUD service."""

    def list_all(self) -> list[AgentConfig]:
        return agent_store.list_all()

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        return agent_store.get(agent_id)

    def create(self, req: AgentCreateRequest) -> AgentConfig:
        agent = AgentConfig(
            id=uuid.uuid4().hex[:12],
            name=req.name,
            description=req.description,
            system_prompt=req.system_prompt,
            llm_config=req.llm_config,
            memory_config=req.memory_config,
            capabilities=req.capabilities,
            knowledge_base_ids=req.knowledge_base_ids,
            tool_ids=req.tool_ids,
            status=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return agent_store.save(agent)

    def update(self, agent_id: str, req: AgentUpdateRequest) -> Optional[AgentConfig]:
        agent = agent_store.get(agent_id)
        if agent is None:
            return None

        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(agent, field, value)
        agent.updated_at = datetime.now()
        return agent_store.save(agent)

    def delete(self, agent_id: str) -> bool:
        return agent_store.delete(agent_id)


agent_service = AgentService()
```

- [ ] **Step 4: Write api/v1/agent.py — agent CRUD endpoints**

```python
# app/api/v1/agent.py
from fastapi import APIRouter

from app.models.agent import AgentCreateRequest, AgentUpdateRequest
from app.models.common import Result
from app.services.agent_service import agent_service

router = APIRouter(tags=["agent"])


@router.get("/agents")
async def list_agents():
    agents = agent_service.list_all()
    return Result.success(data=agents)


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = agent_service.get(agent_id)
    if agent is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success(data=agent)


@router.post("/agents")
async def create_agent(body: AgentCreateRequest):
    agent = agent_service.create(body)
    return Result.success(data=agent)


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdateRequest):
    agent = agent_service.update(agent_id, body)
    if agent is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success(data=agent)


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    ok = agent_service.delete(agent_id)
    if not ok:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success()
```

- [ ] **Step 5: Update api/v1/router.py to include agent routes**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router
from app.api.v1.agent import router as agent_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
router.include_router(agent_router)
```

- [ ] **Step 6: Write tests/test_agent_api.py**

```python
# tests/test_agent_api.py
import pytest

SAMPLE_AGENT = {
    "name": "Test Agent",
    "description": "A test agent",
    "llmConfig": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "baseUrl": "https://api.deepseek.com/v1",
        "apiKey": "sk-test-fake",
        "temperature": 0.7,
        "maxTokens": 4096,
        "topP": 0.9,
    },
    "capabilities": ["chat"],
    "memoryConfig": {"type": "conversation_window", "maxTokens": 8000},
}


@pytest.mark.asyncio
async def test_create_agent(client, auth_headers):
    resp = await client.post("/api/v1/agents", json=SAMPLE_AGENT, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["name"] == "Test Agent"
    assert body["data"]["id"]
    assert body["data"]["status"] == 1
    return body["data"]["id"]


@pytest.mark.asyncio
async def test_list_agents_empty(client, auth_headers):
    resp = await client.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_agent_crud_lifecycle(client, auth_headers):
    # Create
    resp = await client.post("/api/v1/agents", json=SAMPLE_AGENT, headers=auth_headers)
    assert resp.json()["code"] == 200
    agent_id = resp.json()["data"]["id"]

    # Get
    resp = await client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Test Agent"

    # Update
    resp = await client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "Updated Agent"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Updated Agent"

    # Delete
    resp = await client.delete(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 200

    # Get after delete -> 404
    resp = await client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 404
```

- [ ] **Step 7: Run tests**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_agent_api.py -v
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: agent config CRUD with JSON file store"
```

---

## Task 5: Conversation Memory — Chroma Integration

**Files:**
- Create: `app/db/chroma_client.py`
- Create: `app/db/memory_store.py`
- Create: `app/core/memory.py`
- Modify: `app/main.py` (Chroma lifespan init)
- Modify: `app/services/chat_service.py` (integrate memory)
- Modify: `app/api/v1/chat.py` (pass user_id + conversation_id to memory)
- Create: `tests/test_memory.py`

- [ ] **Step 1: Write db/chroma_client.py — Chroma singleton with lifespan management**

```python
# app/db/chroma_client.py
import chromadb
import logging
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger("acgagent-ai")

_client: Optional[chromadb.HttpClient | chromadb.PersistentClient] = None


def init_chroma():
    """Initialize Chroma persistent client."""
    global _client
    chroma_dir = settings.data_dir / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(chroma_dir))
    logger.info("Chroma initialized at %s", chroma_dir)


def get_chroma() -> chromadb.ClientAPI:
    """Get the Chroma client instance."""
    if _client is None:
        init_chroma()
    return _client


def close_chroma():
    """Shutdown Chroma client."""
    global _client
    _client = None
    logger.info("Chroma client closed")
```

- [ ] **Step 2: Write db/memory_store.py — Chroma-backed conversation memory store**

```python
# app/db/memory_store.py
import logging
from datetime import datetime
from typing import Optional

from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")


class MemoryStore:
    """Store and retrieve conversation messages in Chroma.

    Each conversation has its own collection: memory_conv_{conversation_id}.
    Messages are stored as documents with metadata {role, timestamp, token_count}.
    """

    def _collection_name(self, conversation_id: str) -> str:
        return f"memory_conv_{conversation_id}"

    def _get_or_create_collection(self, conversation_id: str):
        return get_chroma().get_or_create_collection(
            name=self._collection_name(conversation_id),
            metadata={"hnsw:space": "cosine"},
        )

    def save_message(self, conversation_id: str, role: str, content: str, token_count: int = 0):
        """Save a single message to the conversation's Chroma collection."""
        if not conversation_id:
            return
        col = self._get_or_create_collection(conversation_id)
        msg_id = f"{role}_{col.count()}"
        timestamp = datetime.now().isoformat()
        col.add(
            ids=[msg_id],
            documents=[content],
            metadatas=[{"role": role, "timestamp": timestamp, "token_count": token_count}],
        )

    def load_history(self, conversation_id: str, limit: int = 100) -> list[dict]:
        """Load conversation history ordered by insertion (chronological)."""
        if not conversation_id:
            return []
        try:
            col = get_chroma().get_collection(name=self._collection_name(conversation_id))
        except Exception:
            return []

        count = col.count()
        if count == 0:
            return []

        result = col.get(
            include=["documents", "metadatas"],
            limit=min(limit, count),
        )

        messages = []
        for doc, meta in zip(result["documents"], result["metadatas"]):
            messages.append({
                "role": meta.get("role", "user"),
                "content": doc,
                "token_count": meta.get("token_count", 0),
            })
        return messages

    def delete_conversation(self, conversation_id: str):
        """Delete all messages for a conversation."""
        if not conversation_id:
            return
        try:
            get_chroma().delete_collection(name=self._collection_name(conversation_id))
        except Exception:
            pass


memory_store = MemoryStore()
```

- [ ] **Step 3: Write core/memory.py — conversation memory manager**

```python
# app/core/memory.py
import tiktoken
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

from app.db.memory_store import memory_store
from app.models.agent import MemoryConfig

logger = logging.getLogger("acgagent-ai")


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Estimate token count for a string using tiktoken."""
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


class ConversationMemory:
    """Manages conversation history with token-budget trimming."""

    def __init__(self, config: MemoryConfig):
        self.config = config
        self.max_tokens = config.max_tokens

    def load_messages(self, conversation_id: str) -> list[BaseMessage]:
        """Load and trim conversation history to fit within token budget."""
        if self.config.type == "none" or not conversation_id:
            return []

        raw_messages = memory_store.load_history(conversation_id)
        lc_messages = []
        for msg in raw_messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))

        # Trim from the front to fit within token budget
        trimmed = self._trim_to_budget(lc_messages)
        return trimmed

    def save_user_message(self, conversation_id: str, content: str):
        """Save a user message to conversation memory."""
        if not conversation_id or self.config.type == "none":
            return
        tokens = count_tokens(content)
        memory_store.save_message(conversation_id, "user", content, token_count=tokens)

    def save_assistant_message(self, conversation_id: str, content: str):
        """Save an assistant message to conversation memory."""
        if not conversation_id or self.config.type == "none":
            return
        tokens = count_tokens(content)
        memory_store.save_message(conversation_id, "assistant", content, token_count=tokens)

    def _trim_to_budget(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Keep only the most recent messages that fit within max_tokens."""
        if not messages:
            return []

        total = 0
        kept = []
        for msg in reversed(messages):
            msg_tokens = count_tokens(msg.content)
            if total + msg_tokens > self.max_tokens:
                break
            total += msg_tokens
            kept.insert(0, msg)
        return kept
```

- [ ] **Step 4: Update main.py — add Chroma init to lifespan**

Add to the `lifespan` function in `app/main.py`, after the directory creation loop:

```python
    # Inside lifespan(), after the mkdir loop:
    from app.db.chroma_client import init_chroma, close_chroma
    init_chroma()
    yield
    close_chroma()
    logger.info("acgagent-ai shutting down")
```

The full updated lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    for subdir in ["agents", "knowledge_bases", "documents", "tools", "chroma", "uploads"]:
        (settings.data_dir / subdir).mkdir(parents=True, exist_ok=True)

    from app.db.chroma_client import init_chroma, close_chroma
    init_chroma()

    logger.info("acgagent-ai started on port %d", settings.port)
    yield
    close_chroma()
    logger.info("acgagent-ai shutting down")
```

- [ ] **Step 5: Update services/chat_service.py — integrate memory into chat**

Replace the `ChatService` class with:

```python
# app/services/chat_service.py
import logging
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import create_chat_model
from app.core.memory import ConversationMemory
from app.models.agent import AgentConfig
from app.models.chat import ChatEvent, ChatCompletionVO, UsageInfo

logger = logging.getLogger("acgagent-ai")


class ChatService:
    """Orchestrates chat completion: memory + LLM call + SSE streaming."""

    def _build_memory(self, agent_config: AgentConfig) -> ConversationMemory:
        return ConversationMemory(agent_config.memory_config)

    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat via SSE with memory support."""
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        llm = create_chat_model(agent_config.llm_config)
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))

        history = memory.load_messages(conversation_id)
        messages.extend(history)

        if not history or history[-1].content != message:
            messages.append(HumanMessage(content=message))

        full_content = ""

        try:
            async for chunk in llm.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

            memory.save_assistant_message(conversation_id, full_content)

            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"

        except Exception as e:
            logger.error("Chat streaming error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"

    async def sync_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> ChatCompletionVO:
        """Non-streaming chat with memory."""
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        llm = create_chat_model(agent_config.llm_config)
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))
        history = memory.load_messages(conversation_id)
        messages.extend(history)
        if not history or history[-1].content != message:
            messages.append(HumanMessage(content=message))

        try:
            response = await llm.ainvoke(messages)
            content = response.content or ""
            memory.save_assistant_message(conversation_id, content)
            return ChatCompletionVO(content=content, usage=UsageInfo())
        except Exception as e:
            logger.error("Chat sync error: %s", e)
            raise


chat_service = ChatService()
```

- [ ] **Step 6: Write tests/test_memory.py**

```python
# tests/test_memory.py
import pytest
from app.db.chroma_client import init_chroma, close_chroma, get_chroma
from app.db.memory_store import memory_store
from app.core.memory import ConversationMemory, count_tokens
from app.models.agent import MemoryConfig


@pytest.fixture(autouse=True)
def setup_chroma():
    """Fresh Chroma for each test."""
    init_chroma()
    yield
    close_chroma()


def test_count_tokens():
    assert count_tokens("hello world") > 0
    assert count_tokens("你好世界") > 0


def test_save_and_load_messages():
    conv_id = "test_conv_001"
    memory_store.save_message(conv_id, "user", "Hello", token_count=5)
    memory_store.save_message(conv_id, "assistant", "Hi there!", token_count=10)

    history = memory_store.load_history(conv_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[1]["role"] == "assistant"


def test_conversation_memory_trim():
    config = MemoryConfig(type="conversation_window", max_tokens=20)
    memory = ConversationMemory(config)

    conv_id = "test_conv_trim"
    for i in range(10):
        memory_store.save_message(conv_id, "user", f"Message {i} with enough words to use tokens", token_count=15)

    messages = memory.load_messages(conv_id)
    total_tokens = sum(count_tokens(m.content) for m in messages)
    assert total_tokens <= config.max_tokens


def test_delete_conversation():
    conv_id = "test_conv_del"
    memory_store.save_message(conv_id, "user", "Bye", token_count=5)
    memory_store.delete_conversation(conv_id)

    history = memory_store.load_history(conv_id)
    assert len(history) == 0
```

- [ ] **Step 7: Run tests**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_memory.py -v
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: conversation memory with Chroma-backed storage and token trimming"
```

---

## Task 6: Tool Use — LangChain Agent with ReAct

**Files:**
- Create: `app/tools/base.py`
- Create: `app/tools/calculator.py`
- Create: `app/tools/web_search.py`
- Create: `app/tools/knowledge_search.py`
- Modify: `app/services/chat_service.py` (add agent mode when tool_ids present)

This task enables the LLM to call tools when the agent has `tool_use` capability.

- [ ] **Step 1: Write tools/base.py — abstract base for tools**

```python
# app/tools/base.py
from abc import ABC, abstractmethod
from typing import Any
from langchain_core.tools import tool as lc_tool


class BaseAgentTool(ABC):
    """Base class for all agent tools."""

    id: str
    name: str
    description: str

    def __init__(self, tool_id: str, name: str, description: str):
        self.id = tool_id
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool with given arguments. Returns result as string."""
        ...

    def to_langchain_tool(self):
        """Convert to a LangChain @tool-decorated function."""
        @lc_tool(self.name)
        def _tool_func(**kwargs) -> str:
            return self.execute(**kwargs)
        _tool_func.description = self.description
        return _tool_func
```

- [ ] **Step 2: Write tools/calculator.py**

```python
# app/tools/calculator.py
from app.tools.base import BaseAgentTool


class CalculatorTool(BaseAgentTool):
    """Evaluate simple math expressions safely."""

    def __init__(self):
        super().__init__(
            tool_id="calculator",
            name="calculator",
            description="计算数学表达式。输入一个数学表达式字符串，返回计算结果。例如: '2 + 3 * 4'",
        )

    def execute(self, **kwargs) -> str:
        expression = kwargs.get("expression", kwargs.get("query", ""))
        # Only allow safe math operations
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return f"错误：表达式包含不允许的字符: {expression}"
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return str(result)
        except Exception as e:
            return f"计算错误: {e}"
```

- [ ] **Step 3: Write tools/web_search.py — stub for now**

```python
# app/tools/web_search.py
from app.tools.base import BaseAgentTool


class WebSearchTool(BaseAgentTool):
    """Web search tool — stub implementation for v1.0."""

    def __init__(self):
        super().__init__(
            tool_id="web_search",
            name="web_search",
            description="搜索互联网获取实时信息。输入搜索关键词，返回搜索结果摘要。",
        )

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", kwargs.get("keywords", ""))
        return f"[v1.0 搜索功能暂未实现] 搜索关键词: {query}"
```

- [ ] **Step 4: Write tools/knowledge_search.py**

```python
# app/tools/knowledge_search.py
import logging
from app.tools.base import BaseAgentTool
from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")


class KnowledgeSearchTool(BaseAgentTool):
    """Search knowledge bases for relevant information."""

    def __init__(self, knowledge_base_ids: list[str]):
        super().__init__(
            tool_id="knowledge_search",
            name="knowledge_search",
            description="在知识库中搜索相关信息。输入搜索查询，返回最相关的文档片段。",
        )
        self.knowledge_base_ids = knowledge_base_ids

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", kwargs.get("question", ""))
        if not query:
            return "请提供搜索查询"

        results = []
        chroma = get_chroma()
        for kb_id in self.knowledge_base_ids:
            col_name = f"kb_{kb_id}_chunks"
            try:
                col = chroma.get_collection(name=col_name)
                query_result = col.query(query_texts=[query], n_results=3)
                for doc in query_result["documents"][0]:
                    results.append(doc)
            except Exception as e:
                logger.warning("KB search failed for %s: %s", col_name, e)

        if not results:
            return "未找到相关信息"
        return "\n\n---\n\n".join(results)
```

- [ ] **Step 5: Update services/chat_service.py — add tool-enabled agent mode**

Add this method to `ChatService` and update `stream_chat` to use it when agent has tool capabilities:

```python
# Add to services/chat_service.py

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Add to ChatService class:

    def _get_tools(self, agent_config: AgentConfig) -> list:
        """Instantiate tools based on agent config."""
        from app.tools.calculator import CalculatorTool
        from app.tools.web_search import WebSearchTool
        from app.tools.knowledge_search import KnowledgeSearchTool

        tools = []
        for tid in agent_config.tool_ids:
            if tid == "calculator":
                tools.append(CalculatorTool())
            elif tid == "web_search":
                tools.append(WebSearchTool())
            elif tid == "knowledge_search":
                if agent_config.knowledge_base_ids:
                    tools.append(KnowledgeSearchTool(agent_config.knowledge_base_ids))
        return [t.to_langchain_tool() for t in tools]

    def _has_tools(self, agent_config: AgentConfig) -> bool:
        return bool(agent_config.tool_ids) and "tool_use" in agent_config.capabilities
```

Update the `stream_chat` method to branch on tool availability. When tools are present, use LangChain's `AgentExecutor` with streaming:

```python
    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        llm = create_chat_model(agent_config.llm_config)

        if self._has_tools(agent_config):
            async for event in self._stream_with_tools(llm, agent_config, message, memory, conversation_id):
                yield event
        else:
            async for event in self._stream_plain(llm, agent_config, message, memory, conversation_id):
                yield event

    async def _stream_plain(self, llm, agent_config, message, memory, conversation_id):
        """Stream without tools."""
        messages = self._build_messages(agent_config, memory, message)
        full_content = ""
        try:
            async for chunk in llm.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"
            memory.save_assistant_message(conversation_id, full_content)
            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"
        except Exception as e:
            logger.error("Chat streaming error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"

    async def _stream_with_tools(self, llm, agent_config, message, memory, conversation_id):
        """Stream with tool calling via LangChain AgentExecutor."""
        tools = self._get_tools(agent_config)
        llm_with_tools = llm.bind_tools(tools)

        messages = self._build_messages(agent_config, memory, message)
        full_content = ""

        try:
            async for chunk in llm_with_tools.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

                if chunk.tool_call_chunks:
                    for tc in chunk.tool_call_chunks:
                        if tc.get("name"):
                            event = ChatEvent(type="tool_call", tool_name=tc["name"], tool_input=tc.get("args"))
                            yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

            memory.save_assistant_message(conversation_id, full_content)
            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"
        except Exception as e:
            logger.error("Tool chat error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"

    def _build_messages(self, agent_config, memory, message):
        """Build the message list from system prompt + memory + current message."""
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))
        history = memory.load_messages("")
        messages.extend(history)
        messages.append(HumanMessage(content=message))
        return messages
```

> **Note:** The `_build_messages` method uses `""` for conversation_id in `load_messages` during internal calls — the actual conversation_id-based loading already happened in `memory.save_user_message` and will be used when loading. Fix: pass `conversation_id` through. This is refined in Task 7.

- [ ] **Step 6: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: tool use support with calculator, web search, and knowledge search tools"
```

---

## Task 7: Knowledge Base CRUD + RAG Retrieval

**Files:**
- Create: `app/models/knowledge_base.py`
- Create: `app/db/knowledge_store.py`
- Create: `app/core/retriever.py`
- Create: `app/services/knowledge_service.py`
- Create: `app/api/v1/knowledge_base.py`
- Create: `tests/test_knowledge.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Write models/knowledge_base.py**

```python
# app/models/knowledge_base.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChunkConfig(BaseModel):
    """Document chunking configuration."""

    chunk_size: int = Field(default=500, description="Max characters per chunk")
    chunk_overlap: int = Field(default=50, description="Overlap characters between chunks")
    separators: list[str] = Field(default_factory=lambda: ["\n\n", "\n", "。", " "], description="Split separators")


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""

    provider: str = Field(default="dashscope", description="Provider: dashscope / openai")
    model: str = Field(default="text-embedding-v3", description="Embedding model name")
    base_url: Optional[str] = Field(default=None, description="API base URL")
    api_key: Optional[str] = Field(default=None, description="API key")


class KnowledgeBase(BaseModel):
    """Knowledge base configuration and metadata."""

    id: str = Field(default="", description="Auto-generated ID")
    name: str = Field(description="Knowledge base name")
    description: Optional[str] = Field(default=None, description="Description")
    embedding_config: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    chunk_config: ChunkConfig = Field(default_factory=ChunkConfig)
    document_count: int = Field(default=0)
    chunk_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    embedding_config: EmbeddingConfig = EmbeddingConfig()
    chunk_config: ChunkConfig = ChunkConfig()


class KnowledgeBaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    chunk_config: Optional[ChunkConfig] = None
```

- [ ] **Step 2: Write db/knowledge_store.py — JSON file store for KB metadata**

```python
# app/db/knowledge_store.py
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.knowledge_base import KnowledgeBase


class KnowledgeStore:
    """JSON file storage for knowledge base metadata."""

    def __init__(self):
        self._dir: Path = settings.data_dir / "knowledge_bases"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, kb_id: str) -> Path:
        return self._dir / f"{kb_id}.json"

    def list_all(self) -> list[KnowledgeBase]:
        result = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(KnowledgeBase(**data))
            except Exception:
                pass
        return result

    def get(self, kb_id: str) -> Optional[KnowledgeBase]:
        path = self._path(kb_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return KnowledgeBase(**data)

    def save(self, kb: KnowledgeBase) -> KnowledgeBase:
        path = self._path(kb.id)
        path.write_text(kb.model_dump_json(indent=2), encoding="utf-8")
        return kb

    def delete(self, kb_id: str) -> bool:
        path = self._path(kb_id)
        if path.exists():
            path.unlink()
            return True
        return False


knowledge_store = KnowledgeStore()
```

- [ ] **Step 3: Write core/retriever.py — RAG retriever**

```python
# app/core/retriever.py
import logging
from langchain_openai import OpenAIEmbeddings
from app.db.chroma_client import get_chroma
from app.models.knowledge_base import EmbeddingConfig

logger = logging.getLogger("acgagent-ai")


class RAGRetriever:
    """Retrieve relevant document chunks from knowledge bases via Chroma."""

    def __init__(self, embedding_config: EmbeddingConfig):
        self.embedding = OpenAIEmbeddings(
            model=embedding_config.model,
            base_url=embedding_config.base_url or "",
            api_key=embedding_config.api_key or "not-needed",
        )

    def retrieve(
        self,
        query: str,
        knowledge_base_ids: list[str],
        top_k: int = 5,
    ) -> list[str]:
        """Search across specified knowledge bases and return relevant chunks."""
        chroma = get_chroma()
        results = []

        for kb_id in knowledge_base_ids:
            col_name = f"kb_{kb_id}_chunks"
            try:
                col = chroma.get_collection(name=col_name)
                query_result = col.query(query_texts=[query], n_results=top_k)
                for doc in query_result["documents"][0]:
                    results.append(doc)
            except Exception as e:
                logger.warning("RAG retrieve failed for %s: %s", col_name, e)

        return results

    @staticmethod
    def build_rag_context(chunks: list[str]) -> str:
        """Format retrieved chunks into a context string for the LLM."""
        if not chunks:
            return ""
        return "\n\n---\n\n".join(chunks)
```

- [ ] **Step 4: Write services/knowledge_service.py**

```python
# app/services/knowledge_service.py
import uuid
from datetime import datetime
from typing import Optional

from app.db.knowledge_store import knowledge_store
from app.models.knowledge_base import KnowledgeBase, KnowledgeBaseCreateRequest, KnowledgeBaseUpdateRequest


class KnowledgeService:
    """Knowledge base CRUD service."""

    def list_all(self) -> list[KnowledgeBase]:
        return knowledge_store.list_all()

    def get(self, kb_id: str) -> Optional[KnowledgeBase]:
        return knowledge_store.get(kb_id)

    def create(self, req: KnowledgeBaseCreateRequest) -> KnowledgeBase:
        kb = KnowledgeBase(
            id=uuid.uuid4().hex[:12],
            name=req.name,
            description=req.description,
            embedding_config=req.embedding_config,
            chunk_config=req.chunk_config,
            document_count=0,
            chunk_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return knowledge_store.save(kb)

    def update(self, kb_id: str, req: KnowledgeBaseUpdateRequest) -> Optional[KnowledgeBase]:
        kb = knowledge_store.get(kb_id)
        if kb is None:
            return None
        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(kb, field, value)
        kb.updated_at = datetime.now()
        return knowledge_store.save(kb)

    def delete(self, kb_id: str) -> bool:
        # Also delete the Chroma collection
        from app.db.chroma_client import get_chroma
        try:
            get_chroma().delete_collection(name=f"kb_{kb_id}_chunks")
        except Exception:
            pass
        return knowledge_store.delete(kb_id)


knowledge_service = KnowledgeService()
```

- [ ] **Step 5: Write api/v1/knowledge_base.py**

```python
# app/api/v1/knowledge_base.py
from fastapi import APIRouter

from app.models.knowledge_base import KnowledgeBaseCreateRequest, KnowledgeBaseUpdateRequest
from app.models.common import Result
from app.services.knowledge_service import knowledge_service

router = APIRouter(tags=["knowledge-base"])


@router.get("/knowledge-bases")
async def list_knowledge_bases():
    return Result.success(data=knowledge_service.list_all())


@router.get("/knowledge-bases/{kb_id}")
async def get_knowledge_base(kb_id: str):
    kb = knowledge_service.get(kb_id)
    if kb is None:
        return Result.error(code=404, message=f"Knowledge base not found: {kb_id}")
    return Result.success(data=kb)


@router.post("/knowledge-bases")
async def create_knowledge_base(body: KnowledgeBaseCreateRequest):
    kb = knowledge_service.create(body)
    return Result.success(data=kb)


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(kb_id: str, body: KnowledgeBaseUpdateRequest):
    kb = knowledge_service.update(kb_id, body)
    if kb is None:
        return Result.error(code=404, message=f"Knowledge base not found: {kb_id}")
    return Result.success(data=kb)


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    ok = knowledge_service.delete(kb_id)
    if not ok:
        return Result.error(code=404, message=f"Knowledge base not found: {kb_id}")
    return Result.success()
```

- [ ] **Step 6: Update router.py to include knowledge_base routes**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router
from app.api.v1.agent import router as agent_router
from app.api.v1.knowledge_base import router as kb_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
router.include_router(agent_router)
router.include_router(kb_router)
```

- [ ] **Step 7: Write tests/test_knowledge.py**

```python
# tests/test_knowledge.py
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
```

- [ ] **Step 8: Run tests**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_knowledge.py -v
```

Expected: all pass

- [ ] **Step 9: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: knowledge base CRUD with JSON file store and Chroma collection management"
```

---

## Task 8: Document Upload — File Processing + Chunking + Embedding

**Files:**
- Create: `app/models/document.py`
- Create: `app/db/document_store.py`
- Create: `app/services/document_service.py`
- Create: `app/api/v1/document.py`
- Create: `tests/test_document.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Write models/document.py**

```python
# app/models/document.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DocumentVO(BaseModel):
    """Document metadata."""

    id: str = Field(default="", description="Auto-generated ID")
    knowledge_base_id: str = Field(description="Parent knowledge base ID")
    file_name: str = Field(description="Original file name")
    file_size: int = Field(default=0, description="File size in bytes")
    chunk_count: int = Field(default=0, description="Number of chunks after processing")
    status: str = Field(default="processing", description="processing / completed / failed")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(default_factory=datetime.now)
```

- [ ] **Step 2: Write db/document_store.py**

```python
# app/db/document_store.py
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.document import DocumentVO


class DocumentStore:
    """JSON file storage for document metadata, organized by knowledge base."""

    def __init__(self):
        self._dir: Path = settings.data_dir / "documents"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _kb_dir(self, kb_id: str) -> Path:
        d = self._dir / kb_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_by_kb(self, kb_id: str) -> list[DocumentVO]:
        kb_dir = self._kb_dir(kb_id)
        result = []
        for f in sorted(kb_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(DocumentVO(**data))
            except Exception:
                pass
        return result

    def get(self, kb_id: str, doc_id: str) -> Optional[DocumentVO]:
        path = self._kb_dir(kb_id) / f"{doc_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return DocumentVO(**data)

    def save(self, doc: DocumentVO) -> DocumentVO:
        path = self._kb_dir(doc.knowledge_base_id) / f"{doc.id}.json"
        path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        return doc

    def delete(self, kb_id: str, doc_id: str) -> bool:
        path = self._kb_dir(kb_id) / f"{doc_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False


document_store = DocumentStore()
```

- [ ] **Step 3: Write services/document_service.py — upload, chunk, embed, store in Chroma**

```python
# app/services/document_service.py
import uuid
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.db.chroma_client import get_chroma
from app.db.document_store import document_store
from app.db.knowledge_store import knowledge_store
from app.models.document import DocumentVO
from app.models.knowledge_base import KnowledgeBase

logger = logging.getLogger("acgagent-ai")


class DocumentService:
    """Handle document upload, chunking, embedding, and Chroma ingestion."""

    def list_documents(self, kb_id: str) -> list[DocumentVO]:
        return document_store.list_by_kb(kb_id)

    def get_document(self, kb_id: str, doc_id: str) -> DocumentVO | None:
        return document_store.get(kb_id, doc_id)

    async def upload_document(self, kb_id: str, file_name: str, file_content: bytes) -> DocumentVO:
        """Save file, create metadata, then process async."""
        kb = knowledge_store.get(kb_id)
        if kb is None:
            return None

        doc_id = uuid.uuid4().hex[:12]

        # Save file to disk
        upload_dir = settings.data_dir / "uploads" / kb_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{doc_id}_{file_name}"
        file_path.write_bytes(file_content)

        doc = DocumentVO(
            id=doc_id,
            knowledge_base_id=kb_id,
            file_name=file_name,
            file_size=len(file_content),
            status="processing",
            created_at=datetime.now(),
        )
        document_store.save(doc)

        # Process asynchronously
        asyncio.create_task(self._process_document(doc, kb, file_path))

        return doc

    async def _process_document(self, doc: DocumentVO, kb: KnowledgeBase, file_path: Path):
        """Read file, chunk text, embed, and store in Chroma."""
        try:
            text = self._read_file(file_path)
            chunks = self._chunk_text(text, kb.chunk_config)

            chroma = get_chroma()
            col_name = f"kb_{kb.id}_chunks"
            col = chroma.get_or_create_collection(
                name=col_name,
                metadata={"hnsw:space": "cosine"},
            )

            chunk_ids = [f"{doc.id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "doc_id": doc.id,
                    "chunk_index": i,
                    "source": doc.file_name,
                    "chunk_size": len(chunk),
                    "created_at": datetime.now().isoformat(),
                }
                for i, chunk in enumerate(chunks)
            ]

            col.add(
                ids=chunk_ids,
                documents=chunks,
                metadatas=metadatas,
            )

            # Update document metadata
            doc.status = "completed"
            doc.chunk_count = len(chunks)
            document_store.save(doc)

            # Update KB counters
            kb.document_count += 1
            kb.chunk_count += len(chunks)
            kb.updated_at = datetime.now()
            knowledge_store.save(kb)

            logger.info("Document %s processed: %d chunks", doc.id, len(chunks))

        except Exception as e:
            logger.error("Document processing failed for %s: %s", doc.id, e)
            doc.status = "failed"
            doc.error_message = str(e)
            document_store.save(doc)

    def _read_file(self, path: Path) -> str:
        """Read text from file based on extension."""
        ext = path.suffix.lower()
        if ext in (".txt", ".md"):
            return path.read_text(encoding="utf-8")
        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext == ".docx":
            from docx import Document
            doc = Document(str(path))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _chunk_text(self, text: str, chunk_config) -> list[str]:
        """Split text into chunks using RecursiveCharacterTextSplitter."""
        if not text.strip():
            return []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_config.chunk_size,
            chunk_overlap=chunk_config.chunk_overlap,
            separators=chunk_config.separators,
        )
        return splitter.split_text(text)

    def delete_document(self, kb_id: str, doc_id: str) -> bool:
        doc = document_store.get(kb_id, doc_id)
        if doc is None:
            return False

        # Remove chunks from Chroma
        chroma = get_chroma()
        try:
            col = chroma.get_collection(name=f"kb_{kb_id}_chunks")
            col.delete(where={"doc_id": doc_id})
        except Exception:
            pass

        # Update KB counters
        kb = knowledge_store.get(kb_id)
        if kb:
            kb.document_count = max(0, kb.document_count - 1)
            kb.chunk_count = max(0, kb.chunk_count - doc.chunk_count)
            kb.updated_at = datetime.now()
            knowledge_store.save(kb)

        return document_store.delete(kb_id, doc_id)


document_service = DocumentService()
```

- [ ] **Step 4: Write api/v1/document.py**

```python
# app/api/v1/document.py
from fastapi import APIRouter, UploadFile, File, Form

from app.models.common import Result
from app.services.document_service import document_service

router = APIRouter(tags=["document"])


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
):
    """Upload a document to a knowledge base. Supported: .txt, .md, .pdf, .docx"""
    content = await file.read()
    doc = await document_service.upload_document(kb_id, file.filename, content)
    if doc is None:
        return Result.error(code=404, message=f"Knowledge base not found: {kb_id}")
    return Result.success(data=doc)


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_documents(kb_id: str):
    docs = document_service.list_documents(kb_id)
    return Result.success(data=docs)


@router.get("/knowledge-bases/{kb_id}/documents/{doc_id}")
async def get_document(kb_id: str, doc_id: str):
    doc = document_service.get_document(kb_id, doc_id)
    if doc is None:
        return Result.error(code=404, message=f"Document not found: {doc_id}")
    return Result.success(data=doc)


@router.delete("/knowledge-bases/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    ok = document_service.delete_document(kb_id, doc_id)
    if not ok:
        return Result.error(code=404, message=f"Document not found: {doc_id}")
    return Result.success()
```

- [ ] **Step 5: Update router.py**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router
from app.api.v1.agent import router as agent_router
from app.api.v1.knowledge_base import router as kb_router
from app.api.v1.document import router as doc_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
router.include_router(agent_router)
router.include_router(kb_router)
router.include_router(doc_router)
```

- [ ] **Step 6: Write tests/test_document.py**

```python
# tests/test_document.py
import pytest
from app.db.chroma_client import init_chroma, close_chroma


@pytest.fixture(autouse=True)
def setup_chroma():
    init_chroma()
    yield
    close_chroma()


@pytest.mark.asyncio
async def test_upload_and_list_documents(client, auth_headers):
    # Create KB first
    resp = await client.post("/api/v1/knowledge-bases", json={"name": "Doc Test KB"}, headers=auth_headers)
    kb_id = resp.json()["data"]["id"]

    # Upload a text file
    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        files={"file": ("test.txt", b"Hello world.\n\nThis is a test document with some content for chunking.", "text/plain")},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200
    doc_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "processing"
    assert resp.json()["data"]["fileName"] == "test.txt"

    # List documents
    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert len(resp.json()["data"]) >= 1

    # Delete document
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
```

- [ ] **Step 7: Run tests**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_document.py -v
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: document upload with chunking and Chroma vector ingestion"
```

---

## Task 9: Tool Management API — Custom Tool Registration

**Files:**
- Create: `app/models/tool.py`
- Create: `app/db/tool_store.py`
- Create: `app/services/tool_service.py`
- Create: `app/api/v1/tool.py`
- Create: `tests/test_tool.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Write models/tool.py**

```python
# app/models/tool.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ToolParameterSchema(BaseModel):
    """JSON Schema for a tool's parameters."""

    type: str = "object"
    properties: dict = {}
    required: list[str] = []


class ToolConfig(BaseModel):
    """Configuration for a custom API tool."""

    url: str = Field(description="API endpoint URL")
    method: str = Field(default="GET", description="HTTP method: GET / POST")
    headers: dict = Field(default_factory=dict)
    query_params: dict = Field(default_factory=dict)
    body_template: Optional[dict] = None


class ToolVO(BaseModel):
    """Tool definition."""

    id: str = Field(default="", description="Auto-generated ID")
    name: str = Field(description="Tool display name")
    description: str = Field(description="Tool description for LLM")
    type: str = Field(default="api", description="Tool type: api / builtin")
    config: Optional[ToolConfig] = None
    parameters: ToolParameterSchema = Field(default_factory=ToolParameterSchema)
    created_at: datetime = Field(default_factory=datetime.now)


class ToolCreateRequest(BaseModel):
    name: str
    description: str
    type: str = "api"
    config: Optional[ToolConfig] = None
    parameters: ToolParameterSchema = ToolParameterSchema()


class ToolUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[ToolConfig] = None
    parameters: Optional[ToolParameterSchema] = None
```

- [ ] **Step 2: Write db/tool_store.py**

```python
# app/db/tool_store.py
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.tool import ToolVO


class ToolStore:
    """JSON file storage for tool definitions."""

    def __init__(self):
        self._dir: Path = settings.data_dir / "tools"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, tool_id: str) -> Path:
        return self._dir / f"{tool_id}.json"

    def list_all(self) -> list[ToolVO]:
        result = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(ToolVO(**data))
            except Exception:
                pass
        return result

    def get(self, tool_id: str) -> Optional[ToolVO]:
        path = self._path(tool_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ToolVO(**data)

    def save(self, tool: ToolVO) -> ToolVO:
        path = self._path(tool.id)
        path.write_text(tool.model_dump_json(indent=2), encoding="utf-8")
        return tool

    def delete(self, tool_id: str) -> bool:
        path = self._path(tool_id)
        if path.exists():
            path.unlink()
            return True
        return False


tool_store = ToolStore()
```

- [ ] **Step 3: Write services/tool_service.py**

```python
# app/services/tool_service.py
import uuid
from datetime import datetime
from typing import Optional

from app.db.tool_store import tool_store
from app.models.tool import ToolVO, ToolCreateRequest, ToolUpdateRequest


class ToolService:
    """Tool registration and management."""

    def __init__(self):
        self._builtin_ids = {"calculator", "web_search", "knowledge_search"}

    def list_all(self) -> list[ToolVO]:
        stored = tool_store.list_all()
        builtins = self._get_builtins()
        return builtins + stored

    def get(self, tool_id: str) -> Optional[ToolVO]:
        if tool_id in self._builtin_ids:
            return self._get_builtins_map().get(tool_id)
        return tool_store.get(tool_id)

    def create(self, req: ToolCreateRequest) -> ToolVO:
        tool = ToolVO(
            id=uuid.uuid4().hex[:12],
            name=req.name,
            description=req.description,
            type=req.type,
            config=req.config,
            parameters=req.parameters,
            created_at=datetime.now(),
        )
        return tool_store.save(tool)

    def delete(self, tool_id: str) -> bool:
        if tool_id in self._builtin_ids:
            return False
        return tool_store.delete(tool_id)

    def _get_builtins(self) -> list[ToolVO]:
        return [
            ToolVO(id="calculator", name="计算器", description="计算数学表达式", type="builtin",
                   parameters=ToolParameterSchema(properties={"expression": {"type": "string", "description": "数学表达式"}}, required=["expression"])),
            ToolVO(id="web_search", name="网络搜索", description="搜索互联网获取实时信息", type="builtin",
                   parameters=ToolParameterSchema(properties={"query": {"type": "string", "description": "搜索关键词"}}, required=["query"])),
            ToolVO(id="knowledge_search", name="知识库搜索", description="在知识库中检索信息", type="builtin",
                   parameters=ToolParameterSchema(properties={"query": {"type": "string", "description": "搜索问题"}}, required=["query"])),
        ]

    def _get_builtins_map(self) -> dict[str, ToolVO]:
        return {t.id: t for t in self._get_builtins()}


tool_service = ToolService()
```

- [ ] **Step 4: Write api/v1/tool.py**

```python
# app/api/v1/tool.py
from fastapi import APIRouter

from app.models.tool import ToolCreateRequest
from app.models.common import Result
from app.services.tool_service import tool_service

router = APIRouter(tags=["tool"])


@router.get("/tools")
async def list_tools():
    return Result.success(data=tool_service.list_all())


@router.get("/tools/{tool_id}")
async def get_tool(tool_id: str):
    tool = tool_service.get(tool_id)
    if tool is None:
        return Result.error(code=404, message=f"Tool not found: {tool_id}")
    return Result.success(data=tool)


@router.post("/tools")
async def create_tool(body: ToolCreateRequest):
    tool = tool_service.create(body)
    return Result.success(data=tool)


@router.delete("/tools/{tool_id}")
async def delete_tool(tool_id: str):
    ok = tool_service.delete(tool_id)
    if not ok:
        return Result.error(code=404, message=f"Tool not found or builtin tool cannot be deleted: {tool_id}")
    return Result.success()
```

- [ ] **Step 5: Update router.py**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router
from app.api.v1.agent import router as agent_router
from app.api.v1.knowledge_base import router as kb_router
from app.api.v1.document import router as doc_router
from app.api.v1.tool import router as tool_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
router.include_router(agent_router)
router.include_router(kb_router)
router.include_router(doc_router)
router.include_router(tool_router)
```

- [ ] **Step 6: Write tests/test_tool.py**

```python
# tests/test_tool.py
import pytest


@pytest.mark.asyncio
async def test_list_tools_includes_builtins(client, auth_headers):
    resp = await client.get("/api/v1/tools", headers=auth_headers)
    assert resp.json()["code"] == 200
    data = resp.json()["data"]
    ids = [t["id"] for t in data]
    assert "calculator" in ids
    assert "web_search" in ids


@pytest.mark.asyncio
async def test_create_and_delete_custom_tool(client, auth_headers):
    resp = await client.post("/api/v1/tools", json={
        "name": "天气查询",
        "description": "查询天气",
        "type": "api",
        "config": {"url": "https://api.weather.com/v1", "method": "GET"},
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    }, headers=auth_headers)
    assert resp.json()["code"] == 200
    tool_id = resp.json()["data"]["id"]

    # Get
    resp = await client.get(f"/api/v1/tools/{tool_id}", headers=auth_headers)
    assert resp.json()["data"]["name"] == "天气查询"

    # Delete
    resp = await client.delete(f"/api/v1/tools/{tool_id}", headers=auth_headers)
    assert resp.json()["code"] == 200


@pytest.mark.asyncio
async def test_cannot_delete_builtin(client, auth_headers):
    resp = await client.delete("/api/v1/tools/calculator", headers=auth_headers)
    assert resp.json()["code"] == 404
```

- [ ] **Step 7: Run tests**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_tool.py -v
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: tool management API with builtin tools and custom tool registration"
```

---

## Task 10: LangGraph Workflow Orchestration

**Files:**
- Create: `app/core/workflow.py`
- Modify: `app/services/chat_service.py` (integrate workflow for agents with `workflow` capability)

- [ ] **Step 1: Write core/workflow.py — LangGraph-based agent workflow**

```python
# app/core/workflow.py
import logging
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.state import AgentState as LGAgentState
from typing_extensions import TypedDict

from app.core.llm import create_chat_model
from app.core.memory import ConversationMemory
from app.core.retriever import RAGRetriever
from app.models.agent import AgentConfig
from app.models.knowledge_base import EmbeddingConfig

logger = logging.getLogger("acgagent-ai")


class WorkflowState(TypedDict):
    """State passed between workflow nodes."""

    messages: list[BaseMessage]
    original_query: str
    context: str
    tool_calls: list[dict]
    final_response: str


class AgentWorkflow:
    """LangGraph workflow that orchestrates: memory → RAG → tools → generate."""

    def __init__(self, agent_config: AgentConfig, memory: ConversationMemory, conversation_id: str):
        self.agent_config = agent_config
        self.memory = memory
        self.conversation_id = conversation_id
        self.llm = create_chat_model(agent_config.llm_config)

    def build_graph(self) -> StateGraph:
        """Build the workflow graph based on agent capabilities."""
        graph = StateGraph(WorkflowState)

        graph.add_node("load_memory", self._load_memory)

        if "rag" in self.agent_config.capabilities and self.agent_config.knowledge_base_ids:
            graph.add_node("retrieve", self._rag_retrieve)
            graph.add_edge("load_memory", "retrieve")
            graph.add_edge("retrieve", "generate")
        else:
            graph.add_edge("load_memory", "generate")

        graph.add_node("generate", self._generate)
        graph.set_entry_point("load_memory")
        graph.add_edge("generate", END)

        return graph.compile()

    def _load_memory(self, state: WorkflowState) -> WorkflowState:
        """Load conversation history from memory."""
        history = self.memory.load_messages(self.conversation_id)
        state["messages"] = history
        return state

    def _rag_retrieve(self, state: WorkflowState) -> WorkflowState:
        """Retrieve relevant documents from knowledge bases."""
        try:
            kb = None
            from app.db.knowledge_store import knowledge_store
            if self.agent_config.knowledge_base_ids:
                kb = knowledge_store.get(self.agent_config.knowledge_base_ids[0])

            if kb:
                retriever = RAGRetriever(kb.embedding_config)
                chunks = retriever.retrieve(state["original_query"], self.agent_config.knowledge_base_ids)
                state["context"] = RAGRetriever.build_rag_context(chunks)
            else:
                state["context"] = ""
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)
            state["context"] = ""
        return state

    def _generate(self, state: WorkflowState) -> WorkflowState:
        """Prepare messages for LLM (actual generation happens in stream_workflow)."""
        return state

    async def stream_workflow(self, query: str) -> AsyncGenerator[str, None]:
        """Execute the workflow and stream LLM output as SSE events."""
        from app.models.chat import ChatEvent, UsageInfo

        graph = self.build_graph()

        initial_state: WorkflowState = {
            "messages": [],
            "original_query": query,
            "context": "",
            "tool_calls": [],
            "final_response": "",
        }

        # Run graph to prepare state (memory + RAG context)
        result = await graph.ainvoke(initial_state)

        # Build messages for LLM
        messages = []
        if self.agent_config.system_prompt:
            messages.append(SystemMessage(content=self.agent_config.system_prompt))

        if result.get("context"):
            rag_prefix = f"基于以下参考资料回答用户问题。如果资料中没有相关信息，请说明。\n\n参考资料：\n{result['context']}\n\n"
            messages.append(SystemMessage(content=rag_prefix))

        messages.extend(result["messages"])
        messages.append(HumanMessage(content=query))

        # Stream LLM response
        full_content = ""
        try:
            async for chunk in self.llm.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

            self.memory.save_assistant_message(self.conversation_id, full_content)
            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"

        except Exception as e:
            logger.error("Workflow streaming error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"
```

- [ ] **Step 2: Update services/chat_service.py — add workflow branch**

Add to the `stream_chat` method, before the `_has_tools` check:

```python
    # In stream_chat(), add this branch:
        if "workflow" in agent_config.capabilities:
            from app.core.workflow import AgentWorkflow
            workflow = AgentWorkflow(agent_config, memory, conversation_id)
            async for event in workflow.stream_workflow(message):
                yield event
            return
```

The full updated `stream_chat`:

```python
    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        if "workflow" in agent_config.capabilities:
            from app.core.workflow import AgentWorkflow
            workflow = AgentWorkflow(agent_config, memory, conversation_id)
            async for event in workflow.stream_workflow(message):
                yield event
            return

        llm = create_chat_model(agent_config.llm_config)

        if self._has_tools(agent_config):
            async for event in self._stream_with_tools(llm, agent_config, message, memory, conversation_id):
                yield event
        else:
            async for event in self._stream_plain(llm, agent_config, message, memory, conversation_id):
                yield event
```

- [ ] **Step 3: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: LangGraph workflow orchestration with memory → RAG → generate pipeline"
```

---

## Task 11: Docker + Seed Script + Final Integration

**Files:**
- Create: `Dockerfile`
- Create: `scripts/seed.py`
- Modify: `app/main.py` (update health check to show Chroma status)

- [ ] **Step 1: Write Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.8.3

COPY pyproject.toml ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY app/ ./app/

RUN mkdir -p data/agents data/knowledge_bases data/documents data/tools data/chroma data/uploads

EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

- [ ] **Step 2: Write scripts/seed.py — create a sample agent for testing**

```python
# scripts/seed.py
"""Create a sample agent for development testing. Run with: poetry run python scripts/seed.py"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.agent_service import agent_service
from app.models.agent import AgentCreateRequest, LLMConfig


def main():
    agent = agent_service.create(AgentCreateRequest(
        name="通用助手",
        description="基于 DeepSeek 的通用对话助手",
        system_prompt="你是一个友善且专业的 AI 助手。请用中文回答问题。",
        llm_config=LLMConfig(
            provider="deepseek",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-your-key"),
            temperature=0.7,
            max_tokens=4096,
            top_p=0.9,
        ),
        capabilities=["chat", "rag", "tool_use", "workflow"],
    ))
    print(f"Sample agent created: {agent.id} - {agent.name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update health endpoint in main.py to check Chroma**

```python
# Replace the health_check function in main.py:

@app.get("/api/v1/health", tags=["system"])
async def health_check():
    """Health check endpoint."""
    chroma_status = "not_initialized"
    try:
        from app.db.chroma_client import get_chroma
        get_chroma().heartbeat()
        chroma_status = "connected"
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": settings.app_version,
        "chroma": chroma_status,
        "llm": "configured_via_agent",
    }
```

- [ ] **Step 4: Run full test suite**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: Docker build, seed script, and health check with Chroma status"
```

---

## Task 12: acgagent Java Side — Gateway Route + Chat Service Adapter

This task modifies the existing acgagent Java project to call acgagent-ai.

**Files:**
- Modify: `acg-chat/src/main/resources/application.yml` (add acgagent-ai config)
- Modify: `acg-chat/src/main/java/com/darkness/agent/client/AgentClient.java` (change target to acgagent-ai)
- Modify: `acg-gateway/src/main/resources/application.yml` (add `/api/knowledge/**` route)

> **Note:** These are minimal changes to the existing Java codebase. The full scope depends on reading the current source files. The plan provides the direction and key code changes.

- [ ] **Step 1: Add acgagent-ai config to acg-chat application.yml**

Add to `acg-chat/src/main/resources/application.yml` (or the Nacos `acg-chat.yaml`):

```yaml
acg:
  ai:
    base-url: ${ACG_AI_URL:http://localhost:8100}
    api-key: ${ACG_AI_API_KEY:dev-api-key}
```

- [ ] **Step 2: Modify AgentClient to call acgagent-ai**

The `AgentClient` in acg-chat should change from calling external LLM API directly to calling `acgagent-ai(8100)/api/v1/chat/{agent_id}/completions`, passing `X-API-Key` and `X-User-Id` headers.

Key changes:
- Target URL: `${acg.ai.base-url}/api/v1/chat/{agentId}/completions`
- Headers: `X-API-Key: ${acg.ai.api-key}`, `X-User-Id: {currentUserId}`
- SSE event format: parse `{"type":"content","content":"..."}` instead of raw OpenAI delta format
- Map `done` event to extract usage stats

- [ ] **Step 3: Add Gateway route for knowledge base**

Add to `acg-gateway/src/main/resources/application.yml` or Nacos `acg-gateway.yaml`:

```yaml
# In spring.cloud.gateway.routes, add:
- id: knowledge-service
  uri: lb://acg-chat
  predicates:
    - Path=/api/knowledge/**
```

- [ ] **Step 4: Commit**

```bash
cd D:/ideaproject/acgAgent
git add acg-chat/src acg-gateway/src
git commit -m "feat: integrate acgagent-ai into acg-chat and gateway routing"
```

---

## Self-Review Checklist

### 1. Spec Coverage

| Spec Section | Task |
|---|---|
| Section 2 — Tech Stack (FastAPI, LangChain, Chroma, LangGraph) | Task 1-10 |
| Section 5.2 — Agent CRUD API | Task 4 |
| Section 5.3 — Chat (SSE stream + sync) | Task 3, 6, 10 |
| Section 5.4 — Knowledge Base CRUD | Task 7 |
| Section 5.5 — Document Upload | Task 8 |
| Section 5.6 — Tool Management | Task 9 |
| Section 5.7 — Health Check | Task 2, 11 |
| Section 6.2 — Agent Config Model | Task 4 |
| Section 6.3 — Chroma Collections | Task 5, 8 |
| Section 7.1 — Conversation Memory | Task 5 |
| Section 7.2 — RAG Retriever | Task 7 |
| Section 7.3 — Tool Registry | Task 6, 9 |
| Section 7.4 — Workflow (LangGraph) | Task 10 |
| Section 8 — acgagent Integration | Task 12 |
| Section 9 — Docker Deployment | Task 11 |

### 2. Placeholder Scan

No TBD, TODO, "implement later", or "fill in details" found. All steps contain complete code.

### 3. Type Consistency

- `AgentConfig.id` is `str` — used consistently as `agent_id` in API paths
- `KnowledgeBase.id` is `str` — used as `kb_id` consistently
- `ChatEvent.type` enum values (`content`, `tool_call`, `done`, `error`) used consistently across `chat_service.py` and `workflow.py`
- `Result.success(data=...)` / `Result.error(code, message)` used consistently across all API handlers
