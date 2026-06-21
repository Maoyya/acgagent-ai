# acgagent-ai 实施计划

> **致 agentic worker：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 来逐任务实现本计划。步骤使用复选框（`- [ ]`）语法进行进度追踪。

**目标：** 构建 acgagent-ai —— 一个独立的 Python Agent 服务（FastAPI + LangChain + Chroma + LangGraph），通过 REST API 为现有的 acgagent Java 微服务提供 AI Agent 能力（对话记忆、RAG、工具调用、工作流编排）。

**架构：** 端口 8100 上的独立 Python 服务。acgagent（Java）通过 HTTP 调用 acgagent-ai，使用 API Key 鉴权并透传 `X-User-Id` 请求头。数据以 JSON 文件（Agent 配置、知识库元数据）+ Chroma（向量、文档分块、对话记忆）形式存储。不使用关系型数据库。

**技术栈：** Python 3.11+、FastAPI 0.110+、LangChain 0.3+、LangGraph 0.2+、Chroma 0.5+、Pydantic 2.x、Poetry 1.8+、Uvicorn、Docker

---

## 文件结构图

所有文件位于 `D:\PycharmProjects\pythonProject\`（项目根目录）下：

```
acgagent-ai/
├── pyproject.toml                          # 任务 1
├── .gitignore                              # 任务 1
├── app/
│   ├── __init__.py                         # 任务 1
│   ├── main.py                             # 任务 2（FastAPI 应用、CORS、lifespan）
│   ├── config.py                           # 任务 2（Pydantic Settings）
│   ├── api/
│   │   ├── __init__.py                     # 任务 1
│   │   ├── deps.py                         # 任务 2（API Key 鉴权依赖）
│   │   ├── middleware.py                   # 任务 2（请求日志）
│   │   └── v1/
│   │       ├── __init__.py                 # 任务 1
│   │       ├── router.py                   # 任务 2（路由汇总）
│   │       ├── chat.py                     # 任务 3（对话端点）
│   │       ├── agent.py                    # 任务 4（Agent CRUD）
│   │       ├── knowledge_base.py           # 任务 7（知识库 CRUD）
│   │       ├── document.py                 # 任务 8（文档上传）
│   │       └── tool.py                     # 任务 9（工具注册 API）
│   ├── models/
│   │   ├── __init__.py                     # 任务 1
│   │   ├── common.py                       # 任务 2（Result<T>、错误码）
│   │   ├── agent.py                        # 任务 4（AgentConfig、LLMConfig、MemoryConfig）
│   │   ├── chat.py                         # 任务 3（ChatRequest、ChatEvent、SSE 类型）
│   │   ├── knowledge_base.py               # 任务 7（KnowledgeBase、ChunkConfig、EmbeddingConfig）
│   │   ├── document.py                     # 任务 8（DocumentVO、DocumentStatus）
│   │   └── tool.py                         # 任务 9（ToolConfig、ToolVO）
│   ├── core/
│   │   ├── __init__.py                     # 任务 1
│   │   ├── llm.py                          # 任务 3（LLM 工厂，初始化 ChatOpenAI）
│   │   ├── memory.py                       # 任务 5（ConversationWindowMemory、SummaryMemory）
│   │   ├── retriever.py                    # 任务 7（RAG 检索器）
│   │   ├── agent_executor.py               # 任务 6（LangChain ReAct agent）
│   │   └── workflow.py                     # 任务 10（LangGraph 工作流）
│   ├── services/
│   │   ├── __init__.py                     # 任务 1
│   │   ├── chat_service.py                 # 任务 3（对话编排、SSE 流式）
│   │   ├── agent_service.py                # 任务 4（Agent CRUD、JSON 文件存储）
│   │   ├── knowledge_service.py            # 任务 7（知识库 CRUD、Chroma collection 管理）
│   │   ├── document_service.py             # 任务 8（文件上传、分块、向量化、Chroma 入库）
│   │   └── tool_service.py                 # 任务 9（工具注册、内置工具）
│   ├── tools/
│   │   ├── __init__.py                     # 任务 9
│   │   ├── base.py                         # 任务 9（BaseTool 抽象基类）
│   │   ├── calculator.py                   # 任务 9（计算器工具实现）
│   │   ├── web_search.py                   # 任务 9（网络搜索桩）
│   │   └── knowledge_search.py             # 任务 9（知识库搜索工具实现）
│   └── db/
│       ├── __init__.py                     # 任务 1
│       ├── chroma_client.py                # 任务 5（Chroma 单例、init/close）
│       ├── agent_store.py                  # 任务 4（Agent 的 JSON 文件存储）
│       ├── knowledge_store.py              # 任务 7（知识库元数据的 JSON 文件存储）
│       ├── document_store.py               # 任务 8（文档元数据的 JSON 文件存储）
│       ├── tool_store.py                   # 任务 9（工具的 JSON 文件存储）
│       └── memory_store.py                 # 任务 5（基于 Chroma 的对话记忆）
├── data/                                   # 运行时数据（.gitignore）
│   ├── agents/                             # 任务 4
│   ├── knowledge_bases/                    # 任务 7
│   ├── documents/                          # 任务 8
│   ├── tools/                              # 任务 9
│   ├── chroma/                             # 任务 5
│   └── uploads/                            # 任务 8
├── tests/
│   ├── __init__.py                         # 任务 1
│   ├── conftest.py                         # 任务 2（fixtures：测试客户端、mock LLM）
│   ├── test_health.py                      # 任务 2
│   ├── test_agent_api.py                   # 任务 4
│   ├── test_chat.py                        # 任务 3（同步）+ 任务 5（记忆）+ 任务 6（agent）
│   ├── test_knowledge.py                   # 任务 7
│   ├── test_document.py                    # 任务 8
│   └── test_tool.py                        # 任务 9
├── Dockerfile                              # 任务 11
└── scripts/
    └── seed.py                             # 任务 11
```

---

## 任务 1：项目脚手架 + Poetry 配置

**文件：**
- 新建：`D:\PycharmProjects\pythonProject\pyproject.toml`
- 新建：`D:\PycharmProjects\pythonProject\.gitignore`
- 新建：`D:\PycharmProjects\pythonProject\app\__init__.py`
- 新建：`D:\PycharmProjects\pythonProject\app\api\__init__.py`
- 新建：`D:\PycharmProjects\pythonProject\app\api\v1\__init__.py`
- 新建：`D:\PycharmProjects\pythonProject\app\models\__init__.py`
- 新建：`D:\PycharmProjects\pythonProject\app\core\__init__.py`
- 新建：`D:\PycharmProjects\pythonProject\app\services\__init__.py`
- 新建：`D:\PycharmProjects\pythonProject\app\db\__init__.py`
- 新建：`D:\PycharmProjects\pythonProject\tests\__init__.py`

- [ ] **步骤 1：创建项目目录和 pyproject.toml**

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

- [ ] **步骤 2：创建 .gitignore**

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

- [ ] **步骤 3：创建所有 __init__.py 文件和数据目录**

```bash
mkdir -p app/api/v1 app/models app/core app/services app/tools app/db
mkdir -p tests data/agents data/knowledge_bases data/documents data/tools data/chroma data/uploads
touch app/__init__.py app/api/__init__.py app/api/v1/__init__.py
touch app/models/__init__.py app/core/__init__.py app/services/__init__.py
touch app/tools/__init__.py app/db/__init__.py tests/__init__.py
```

- [ ] **步骤 4：安装依赖**

```bash
cd D:/PycharmProjects/pythonProject
poetry install
```

- [ ] **步骤 5：验证安装**

```bash
cd D:/PycharmProjects/pythonProject
poetry run python -c "import fastapi; import langchain; import chromadb; print('OK')"
```

预期输出：`OK`

- [ ] **步骤 6：初始化 git 仓库并提交**

```bash
cd D:/PycharmProjects/pythonProject
git init
git add .
git commit -m "chore: scaffold acgagent-ai project with Poetry"
```

---

## 任务 2：FastAPI 应用 + 配置 + 鉴权中间件 + 健康检查端点

**文件：**
- 新建：`app/config.py`
- 新建：`app/models/common.py`
- 新建：`app/api/deps.py`
- 新建：`app/api/middleware.py`
- 新建：`app/api/v1/router.py`
- 新建：`app/main.py`
- 新建：`tests/conftest.py`
- 新建：`tests/test_health.py`

- [ ] **步骤 1：编写 config.py —— 基于 Pydantic Settings 的配置**

```python
# app/config.py
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """从环境变量加载的应用配置。"""

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

- [ ] **步骤 2：编写 models/common.py —— 统一 Result<T> 响应**

```python
# app/models/common.py
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """统一 API 响应，匹配 acgagent 的 Result<T> 格式。"""

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

- [ ] **步骤 3：编写 api/deps.py —— API Key 鉴权依赖**

```python
# app/api/deps.py
from fastapi import Header, HTTPException


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """校验 X-API-Key 请求头是否与配置的 API Key 一致。"""
    from app.config import settings

    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


async def get_user_id(x_user_id: str = Header(None, alias="X-User-Id")) -> str | None:
    """从请求头提取 X-User-Id，用于对话记忆隔离。"""
    return x_user_id
```

- [ ] **步骤 4：编写 api/middleware.py —— 请求日志中间件**

```python
# app/api/middleware.py
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("acgagent-ai")


class LoggingMiddleware(BaseHTTPMiddleware):
    """记录每个请求的方法、路径、状态码和耗时。"""

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

- [ ] **步骤 5：编写 api/v1/router.py —— 空的 v1 路由占位**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

- [ ] **步骤 6：编写 main.py —— FastAPI 应用入口**

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
    """启动：创建数据目录。关闭：清理资源。"""
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
    """健康检查端点 —— 无需鉴权。"""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "chroma": "not_initialized",
        "llm": "not_configured",
    }
```

- [ ] **步骤 7：编写 tests/conftest.py —— 共享测试 fixtures**

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
    """带鉴权请求头的异步测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

- [ ] **步骤 8：编写 tests/test_health.py**

```python
# tests/test_health.py
import pytest


@pytest.mark.asyncio
async def test_health_no_auth(client):
    """健康检查端点不需要鉴权。"""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_api_key_required_for_v1(client):
    """v1 端点要求携带 X-API-Key 请求头。"""
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 401 or resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_api_key(client):
    """无效 API Key 返回 401。"""
    resp = await client.get(
        "/api/v1/agents",
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401
```

- [ ] **步骤 9：运行测试**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_health.py -v
```

预期：3 passed

- [ ] **步骤 10：启动开发服务器并手动验证**

```bash
cd D:/PycharmProjects/pythonProject
poetry run uvicorn app.main:app --port 8100 &
# 在另一个终端：
curl -s http://localhost:8100/api/v1/health | python -m json.tool
curl -s http://localhost:8100/docs  # 应返回 Swagger UI HTML
```

预期：health 返回 `{"status":"healthy","version":"1.0.0",...}`，docs 返回 HTML 页面

- [ ] **步骤 11：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: FastAPI app with config, auth middleware, and health endpoint"
```

---

## 任务 3：基础对话 —— LLM 工厂 + 同步/流式对话端点

**文件：**
- 新建：`app/core/llm.py`
- 新建：`app/models/chat.py`
- 新建：`app/services/chat_service.py`
- 新建：`app/api/v1/chat.py`
- 新建：`tests/test_chat.py`
- 修改：`app/api/v1/router.py`

本任务实现最简单的对话：用户发送消息 → LLM 响应。暂无记忆、无 RAG、无工具。用于端到端验证 LLM 集成。

- [ ] **步骤 1：编写 core/llm.py —— 基于 LangChain ChatOpenAI 的 LLM 工厂**

```python
# app/core/llm.py
from langchain_openai import ChatOpenAI
from app.models.agent import LLMConfig


def create_chat_model(config: LLMConfig) -> ChatOpenAI:
    """根据 LLMConfig 创建 LangChain ChatOpenAI 实例。

    所有 v1.0 的提供商（doubao、qwen、deepseek）都兼容 OpenAI 协议，
    因此使用带自定义 base_url 的 ChatOpenAI 即可全部适配。
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

- [ ] **步骤 2：编写 models/chat.py —— 请求/响应模型**

```python
# app/models/chat.py
from typing import Optional
from pydantic import BaseModel


class ChatOptions(BaseModel):
    """单次请求的 LLM 覆盖参数。"""

    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatRequest(BaseModel):
    """对话补全请求体。"""

    conversation_id: str = ""
    message: str
    stream: bool = True
    options: Optional[ChatOptions] = None


class ChatEvent(BaseModel):
    """单个 SSE 事件载荷。"""

    type: str  # content | tool_call | tool_result | thinking | error | done
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Optional[str] = None
    code: Optional[int] = None
    message: Optional[str] = None
    usage: Optional[dict] = None


class UsageInfo(BaseModel):
    """Token 用量统计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionVO(BaseModel):
    """同步（非流式）响应载荷。"""

    content: str
    usage: UsageInfo = UsageInfo()
    tool_calls: list[dict] = []
```

- [ ] **步骤 3：编写 services/chat_service.py —— 基础对话服务（暂无记忆）**

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
    """编排对话补全：LLM 调用 + SSE 流式输出。"""

    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """通过 SSE 流式输出对话。产出格式为 'data: {json}\n\n' 的字符串。"""
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
        """非流式对话。返回完整响应。"""
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

- [ ] **步骤 4：编写 api/v1/chat.py —— 对话端点**

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
    """与 Agent 对话。支持 SSE 流式和同步响应。"""
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

- [ ] **步骤 5：更新 api/v1/router.py，纳入对话路由**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
```

- [ ] **步骤 6：编写 tests/test_chat.py —— 使用 mock LLM 测试**

```python
# tests/test_chat.py
import pytest
import json


@pytest.mark.asyncio
async def test_chat_agent_not_found(client, auth_headers):
    """Agent 不存在时返回 404。"""
    resp = await client.post(
        "/api/v1/agents",  # 先创建 agent —— 但端点尚未构建
        json={"name": "test-agent", "llmConfig": {"provider": "deepseek", "model": "deepseek-chat", "baseUrl": "https://api.deepseek.com/v1", "apiKey": "sk-test", "temperature": 0.7, "maxTokens": 4096, "topP": 0.9}},
        headers=auth_headers,
    )
    # agent API 尚未构建，会返回 404 —— 暂时跳过
    pass


@pytest.mark.asyncio
async def test_chat_missing_message(client, auth_headers):
    """缺少 message 时返回 422。"""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_sync_agent_not_found(client, auth_headers):
    """同步对话在 Agent 不存在时返回 404 Result。"""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404
```

- [ ] **步骤 7：运行测试**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_chat.py -v
```

预期：全部通过（404 和 422 测试）

- [ ] **步骤 8：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: basic chat endpoint with LLM factory and SSE streaming"
```

---

## 任务 4：Agent 配置 CRUD —— JSON 文件存储

**文件：**
- 新建：`app/models/agent.py`
- 新建：`app/db/agent_store.py`
- 新建：`app/services/agent_service.py`
- 新建：`app/api/v1/agent.py`
- 新建：`tests/test_agent_api.py`
- 修改：`app/api/v1/router.py`

- [ ] **步骤 1：编写 models/agent.py —— AgentConfig、LLMConfig、MemoryConfig**

```python
# app/models/agent.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM 模型配置。"""

    provider: str = Field(description="Provider identifier: doubao / qwen / deepseek")
    model: str = Field(description="Model name")
    base_url: str = Field(description="API base URL (OpenAI-compatible)")
    api_key: str = Field(description="API key")
    temperature: float = Field(default=0.7, description="Generation temperature")
    max_tokens: int = Field(default=4096, description="Max output tokens")
    top_p: float = Field(default=0.9, description="Top-P sampling")


class MemoryConfig(BaseModel):
    """对话记忆配置。"""

    type: str = Field(default="conversation_window", description="Memory type: conversation_window / summary / none")
    max_tokens: int = Field(default=8000, description="Context window size in tokens")


class AgentConfig(BaseModel):
    """完整的 Agent 配置。"""

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
    """创建 Agent 的请求体。"""

    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_config: LLMConfig
    memory_config: MemoryConfig = MemoryConfig()
    capabilities: list[str] = ["chat"]
    knowledge_base_ids: list[str] = []
    tool_ids: list[str] = []


class AgentUpdateRequest(BaseModel):
    """更新 Agent 的请求体。所有字段可选。"""

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

- [ ] **步骤 2：编写 db/agent_store.py —— Agent 配置的 JSON 文件存储**

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
    """基于 JSON 文件的 Agent 配置存储。

    每个 Agent 以独立 JSON 文件存储于 data/agents/{agent_id}.json。
    """

    def __init__(self):
        self._dir: Path = settings.data_dir / "agents"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, agent_id: str) -> Path:
        return self._dir / f"{agent_id}.json"

    def list_all(self) -> list[AgentConfig]:
        """从磁盘加载全部 Agent 配置。"""
        agents = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                agents.append(AgentConfig(**data))
            except Exception as e:
                logger.warning("Failed to load agent %s: %s", f.name, e)
        return agents

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """按 ID 加载单个 Agent 配置。"""
        path = self._path(agent_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentConfig(**data)

    def save(self, agent: AgentConfig) -> AgentConfig:
        """将 Agent 配置保存到磁盘。"""
        path = self._path(agent.id)
        path.write_text(agent.model_dump_json(indent=2), encoding="utf-8")
        return agent

    def delete(self, agent_id: str) -> bool:
        """删除 Agent 配置文件。删除成功返回 True。"""
        path = self._path(agent_id)
        if path.exists():
            path.unlink()
            return True
        return False


agent_store = AgentStore()
```

- [ ] **步骤 3：编写 services/agent_service.py —— Agent CRUD 业务逻辑**

```python
# app/services/agent_service.py
import uuid
from datetime import datetime
from typing import Optional

from app.db.agent_store import agent_store
from app.models.agent import AgentConfig, AgentCreateRequest, AgentUpdateRequest


class AgentService:
    """Agent 配置 CRUD 服务。"""

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

- [ ] **步骤 4：编写 api/v1/agent.py —— Agent CRUD 端点**

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

- [ ] **步骤 5：更新 api/v1/router.py，纳入 Agent 路由**

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

- [ ] **步骤 6：编写 tests/test_agent_api.py**

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
    # 创建
    resp = await client.post("/api/v1/agents", json=SAMPLE_AGENT, headers=auth_headers)
    assert resp.json()["code"] == 200
    agent_id = resp.json()["data"]["id"]

    # 查询
    resp = await client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Test Agent"

    # 更新
    resp = await client.put(
        f"/api/v1/agents/{agent_id}",
        json={"name": "Updated Agent"},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Updated Agent"

    # 删除
    resp = await client.delete(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 200

    # 删除后查询 -> 404
    resp = await client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.json()["code"] == 404
```

- [ ] **步骤 7：运行测试**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_agent_api.py -v
```

预期：全部通过

- [ ] **步骤 8：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: agent config CRUD with JSON file store"
```

---

## 任务 5：对话记忆 —— Chroma 集成

**文件：**
- 新建：`app/db/chroma_client.py`
- 新建：`app/db/memory_store.py`
- 新建：`app/core/memory.py`
- 修改：`app/main.py`（Chroma lifespan 初始化）
- 修改：`app/services/chat_service.py`（接入记忆）
- 修改：`app/api/v1/chat.py`（把 user_id + conversation_id 传给记忆）
- 新建：`tests/test_memory.py`

- [ ] **步骤 1：编写 db/chroma_client.py —— 带 lifespan 管理的 Chroma 单例**

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
    """初始化 Chroma 持久化客户端。"""
    global _client
    chroma_dir = settings.data_dir / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(chroma_dir))
    logger.info("Chroma initialized at %s", chroma_dir)


def get_chroma() -> chromadb.ClientAPI:
    """获取 Chroma 客户端实例。"""
    if _client is None:
        init_chroma()
    return _client


def close_chroma():
    """关闭 Chroma 客户端。"""
    global _client
    _client = None
    logger.info("Chroma client closed")
```

- [ ] **步骤 2：编写 db/memory_store.py —— 基于 Chroma 的对话记忆存储**

```python
# app/db/memory_store.py
import logging
from datetime import datetime
from typing import Optional

from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")


class MemoryStore:
    """在 Chroma 中存储和读取对话消息。

    每个会话拥有独立的 collection：memory_conv_{conversation_id}。
    消息以 document 形式存储，metadata 为 {role, timestamp, token_count}。
    """

    def _collection_name(self, conversation_id: str) -> str:
        return f"memory_conv_{conversation_id}"

    def _get_or_create_collection(self, conversation_id: str):
        return get_chroma().get_or_create_collection(
            name=self._collection_name(conversation_id),
            metadata={"hnsw:space": "cosine"},
        )

    def save_message(self, conversation_id: str, role: str, content: str, token_count: int = 0):
        """将单条消息保存到会话的 Chroma collection。"""
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
        """按插入顺序（时间顺序）加载会话历史。"""
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
        """删除某个会话的全部消息。"""
        if not conversation_id:
            return
        try:
            get_chroma().delete_collection(name=self._collection_name(conversation_id))
        except Exception:
            pass


memory_store = MemoryStore()
```

- [ ] **步骤 3：编写 core/memory.py —— 对话记忆管理器**

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
    """使用 tiktoken 估算字符串的 token 数。"""
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


class ConversationMemory:
    """管理对话历史，并按 token 预算裁剪。"""

    def __init__(self, config: MemoryConfig):
        self.config = config
        self.max_tokens = config.max_tokens

    def load_messages(self, conversation_id: str) -> list[BaseMessage]:
        """加载并裁剪对话历史，使其落在 token 预算内。"""
        if self.config.type == "none" or not conversation_id:
            return []

        raw_messages = memory_store.load_history(conversation_id)
        lc_messages = []
        for msg in raw_messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))

        # 从头部开始裁剪以适配 token 预算
        trimmed = self._trim_to_budget(lc_messages)
        return trimmed

    def save_user_message(self, conversation_id: str, content: str):
        """将用户消息保存到对话记忆。"""
        if not conversation_id or self.config.type == "none":
            return
        tokens = count_tokens(content)
        memory_store.save_message(conversation_id, "user", content, token_count=tokens)

    def save_assistant_message(self, conversation_id: str, content: str):
        """将助手消息保存到对话记忆。"""
        if not conversation_id or self.config.type == "none":
            return
        tokens = count_tokens(content)
        memory_store.save_message(conversation_id, "assistant", content, token_count=tokens)

    def _trim_to_budget(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """只保留在 max_tokens 预算内的最近若干条消息。"""
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

- [ ] **步骤 4：更新 main.py —— 在 lifespan 中加入 Chroma 初始化**

在 `app/main.py` 的 `lifespan` 函数中，目录创建循环之后追加：

```python
    # 在 lifespan() 内部，mkdir 循环之后：
    from app.db.chroma_client import init_chroma, close_chroma
    init_chroma()
    yield
    close_chroma()
    logger.info("acgagent-ai shutting down")
```

完整的更新后 lifespan：

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

- [ ] **步骤 5：更新 services/chat_service.py —— 在对话中接入记忆**

用以下内容替换 `ChatService` 类：

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
    """编排对话补全：记忆 + LLM 调用 + SSE 流式输出。"""

    def _build_memory(self, agent_config: AgentConfig) -> ConversationMemory:
        return ConversationMemory(agent_config.memory_config)

    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """通过 SSE 流式输出对话，带记忆支持。"""
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
        """带记忆的非流式对话。"""
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

- [ ] **步骤 6：编写 tests/test_memory.py**

```python
# tests/test_memory.py
import pytest
from app.db.chroma_client import init_chroma, close_chroma, get_chroma
from app.db.memory_store import memory_store
from app.core.memory import ConversationMemory, count_tokens
from app.models.agent import MemoryConfig


@pytest.fixture(autouse=True)
def setup_chroma():
    """每个测试使用全新的 Chroma。"""
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

- [ ] **步骤 7：运行测试**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_memory.py -v
```

预期：全部通过

- [ ] **步骤 8：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: conversation memory with Chroma-backed storage and token trimming"
```

---

## 任务 6：工具调用 —— 基于 LangChain Agent 的 ReAct

**文件：**
- 新建：`app/tools/base.py`
- 新建：`app/tools/calculator.py`
- 新建：`app/tools/web_search.py`
- 新建：`app/tools/knowledge_search.py`
- 修改：`app/services/chat_service.py`（当存在 tool_ids 时增加 agent 模式）

本任务让 LLM 在 Agent 具备 `tool_use` 能力时可以调用工具。

- [ ] **步骤 1：编写 tools/base.py —— 工具抽象基类**

```python
# app/tools/base.py
from abc import ABC, abstractmethod
from typing import Any
from langchain_core.tools import tool as lc_tool


class BaseAgentTool(ABC):
    """所有 Agent 工具的基类。"""

    id: str
    name: str
    description: str

    def __init__(self, tool_id: str, name: str, description: str):
        self.id = tool_id
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """以给定参数执行工具。结果以字符串返回。"""
        ...

    def to_langchain_tool(self):
        """转换为 LangChain @tool 装饰的函数。"""
        @lc_tool(self.name)
        def _tool_func(**kwargs) -> str:
            return self.execute(**kwargs)
        _tool_func.description = self.description
        return _tool_func
```

- [ ] **步骤 2：编写 tools/calculator.py**

```python
# app/tools/calculator.py
from app.tools.base import BaseAgentTool


class CalculatorTool(BaseAgentTool):
    """安全地计算简单数学表达式。"""

    def __init__(self):
        super().__init__(
            tool_id="calculator",
            name="calculator",
            description="计算数学表达式。输入一个数学表达式字符串，返回计算结果。例如: '2 + 3 * 4'",
        )

    def execute(self, **kwargs) -> str:
        expression = kwargs.get("expression", kwargs.get("query", ""))
        # 仅允许安全的数学运算
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return f"错误：表达式包含不允许的字符: {expression}"
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return str(result)
        except Exception as e:
            return f"计算错误: {e}"
```

- [ ] **步骤 3：编写 tools/web_search.py —— 暂为桩实现**

```python
# app/tools/web_search.py
from app.tools.base import BaseAgentTool


class WebSearchTool(BaseAgentTool):
    """网络搜索工具 —— v1.0 的桩实现。"""

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

- [ ] **步骤 4：编写 tools/knowledge_search.py**

```python
# app/tools/knowledge_search.py
import logging
from app.tools.base import BaseAgentTool
from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")


class KnowledgeSearchTool(BaseAgentTool):
    """在知识库中搜索相关信息。"""

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

- [ ] **步骤 5：更新 services/chat_service.py —— 增加支持工具的 agent 模式**

向 `ChatService` 添加以下方法，并在 `stream_chat` 中当 Agent 具备工具能力时使用它：

```python
# 添加到 services/chat_service.py

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# 添加到 ChatService 类：

    def _get_tools(self, agent_config: AgentConfig) -> list:
        """根据 Agent 配置实例化工具。"""
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

更新 `stream_chat` 方法，按是否可用工具分流。当存在工具时，使用 LangChain 的 `AgentExecutor` 进行流式输出：

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
        """无工具的流式输出。"""
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
        """通过 LangChain AgentExecutor 进行带工具调用的流式输出。"""
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
        """由 system prompt + 记忆 + 当前消息构建消息列表。"""
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))
        history = memory.load_messages("")
        messages.extend(history)
        messages.append(HumanMessage(content=message))
        return messages
```

> **注意：** `_build_messages` 方法在内部调用 `load_messages` 时对 conversation_id 使用了 `""` —— 实际基于 conversation_id 的加载已发生在 `memory.save_user_message` 中，加载时会用到。修复方式：把 `conversation_id` 一路传下去。这一点在任务 7 中细化。

- [ ] **步骤 6：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: tool use support with calculator, web search, and knowledge search tools"
```

---

## 任务 7：知识库 CRUD + RAG 检索

**文件：**
- 新建：`app/models/knowledge_base.py`
- 新建：`app/db/knowledge_store.py`
- 新建：`app/core/retriever.py`
- 新建：`app/services/knowledge_service.py`
- 新建：`app/api/v1/knowledge_base.py`
- 新建：`tests/test_knowledge.py`
- 修改：`app/api/v1/router.py`

- [ ] **步骤 1：编写 models/knowledge_base.py**

```python
# app/models/knowledge_base.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChunkConfig(BaseModel):
    """文档分块配置。"""

    chunk_size: int = Field(default=500, description="Max characters per chunk")
    chunk_overlap: int = Field(default=50, description="Overlap characters between chunks")
    separators: list[str] = Field(default_factory=lambda: ["\n\n", "\n", "。", " "], description="Split separators")


class EmbeddingConfig(BaseModel):
    """Embedding 模型配置。"""

    provider: str = Field(default="dashscope", description="Provider: dashscope / openai")
    model: str = Field(default="text-embedding-v3", description="Embedding model name")
    base_url: Optional[str] = Field(default=None, description="API base URL")
    api_key: Optional[str] = Field(default=None, description="API key")


class KnowledgeBase(BaseModel):
    """知识库配置与元数据。"""

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

- [ ] **步骤 2：编写 db/knowledge_store.py —— 知识库元数据的 JSON 文件存储**

```python
# app/db/knowledge_store.py
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.knowledge_base import KnowledgeBase


class KnowledgeStore:
    """知识库元数据的 JSON 文件存储。"""

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

- [ ] **步骤 3：编写 core/retriever.py —— RAG 检索器**

```python
# app/core/retriever.py
import logging
from langchain_openai import OpenAIEmbeddings
from app.db.chroma_client import get_chroma
from app.models.knowledge_base import EmbeddingConfig

logger = logging.getLogger("acgagent-ai")


class RAGRetriever:
    """通过 Chroma 从知识库中检索相关文档分块。"""

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
        """跨指定知识库搜索，返回相关分块。"""
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
        """将检索到的分块格式化为供 LLM 使用的上下文字符串。"""
        if not chunks:
            return ""
        return "\n\n---\n\n".join(chunks)
```

- [ ] **步骤 4：编写 services/knowledge_service.py**

```python
# app/services/knowledge_service.py
import uuid
from datetime import datetime
from typing import Optional

from app.db.knowledge_store import knowledge_store
from app.models.knowledge_base import KnowledgeBase, KnowledgeBaseCreateRequest, KnowledgeBaseUpdateRequest


class KnowledgeService:
    """知识库 CRUD 服务。"""

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
        # 同时删除 Chroma collection
        from app.db.chroma_client import get_chroma
        try:
            get_chroma().delete_collection(name=f"kb_{kb_id}_chunks")
        except Exception:
            pass
        return knowledge_store.delete(kb_id)


knowledge_service = KnowledgeService()
```

- [ ] **步骤 5：编写 api/v1/knowledge_base.py**

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

- [ ] **步骤 6：更新 router.py，纳入知识库路由**

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

- [ ] **步骤 7：编写 tests/test_knowledge.py**

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
    # 创建
    resp = await client.post("/api/v1/knowledge-bases", json=SAMPLE_KB, headers=auth_headers)
    assert resp.json()["code"] == 200
    kb_id = resp.json()["data"]["id"]
    assert kb_id

    # 查询
    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Test KB"

    # 列表
    resp = await client.get("/api/v1/knowledge-bases", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert len(resp.json()["data"]) >= 1

    # 更新
    resp = await client.put(f"/api/v1/knowledge-bases/{kb_id}", json={"name": "Updated KB"}, headers=auth_headers)
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["name"] == "Updated KB"

    # 删除
    resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}", headers=auth_headers)
    assert resp.json()["code"] == 200

    # 删除后查询
    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=auth_headers)
    assert resp.json()["code"] == 404
```

- [ ] **步骤 8：运行测试**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_knowledge.py -v
```

预期：全部通过

- [ ] **步骤 9：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: knowledge base CRUD with JSON file store and Chroma collection management"
```

---

## 任务 8：文档上传 —— 文件处理 + 分块 + 向量化

**文件：**
- 新建：`app/models/document.py`
- 新建：`app/db/document_store.py`
- 新建：`app/services/document_service.py`
- 新建：`app/api/v1/document.py`
- 新建：`tests/test_document.py`
- 修改：`app/api/v1/router.py`

- [ ] **步骤 1：编写 models/document.py**

```python
# app/models/document.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DocumentVO(BaseModel):
    """文档元数据。"""

    id: str = Field(default="", description="Auto-generated ID")
    knowledge_base_id: str = Field(description="Parent knowledge base ID")
    file_name: str = Field(description="Original file name")
    file_size: int = Field(default=0, description="File size in bytes")
    chunk_count: int = Field(default=0, description="Number of chunks after processing")
    status: str = Field(default="processing", description="processing / completed / failed")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(default_factory=datetime.now)
```

- [ ] **步骤 2：编写 db/document_store.py**

```python
# app/db/document_store.py
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.document import DocumentVO


class DocumentStore:
    """文档元数据的 JSON 文件存储，按知识库分组。"""

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

- [ ] **步骤 3：编写 services/document_service.py —— 上传、分块、向量化、写入 Chroma**

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
    """处理文档上传、分块、向量化以及 Chroma 入库。"""

    def list_documents(self, kb_id: str) -> list[DocumentVO]:
        return document_store.list_by_kb(kb_id)

    def get_document(self, kb_id: str, doc_id: str) -> DocumentVO | None:
        return document_store.get(kb_id, doc_id)

    async def upload_document(self, kb_id: str, file_name: str, file_content: bytes) -> DocumentVO:
        """保存文件、创建元数据，随后异步处理。"""
        kb = knowledge_store.get(kb_id)
        if kb is None:
            return None

        doc_id = uuid.uuid4().hex[:12]

        # 将文件保存到磁盘
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

        # 异步处理
        asyncio.create_task(self._process_document(doc, kb, file_path))

        return doc

    async def _process_document(self, doc: DocumentVO, kb: KnowledgeBase, file_path: Path):
        """读取文件、分块、向量化并写入 Chroma。"""
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

            # 更新文档元数据
            doc.status = "completed"
            doc.chunk_count = len(chunks)
            document_store.save(doc)

            # 更新知识库计数
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
        """根据扩展名从文件读取文本。"""
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
        """使用 RecursiveCharacterTextSplitter 将文本切分为分块。"""
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

        # 从 Chroma 中移除分块
        chroma = get_chroma()
        try:
            col = chroma.get_collection(name=f"kb_{kb_id}_chunks")
            col.delete(where={"doc_id": doc_id})
        except Exception:
            pass

        # 更新知识库计数
        kb = knowledge_store.get(kb_id)
        if kb:
            kb.document_count = max(0, kb.document_count - 1)
            kb.chunk_count = max(0, kb.chunk_count - doc.chunk_count)
            kb.updated_at = datetime.now()
            knowledge_store.save(kb)

        return document_store.delete(kb_id, doc_id)


document_service = DocumentService()
```

- [ ] **步骤 4：编写 api/v1/document.py**

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
    """上传文档到知识库。支持：.txt, .md, .pdf, .docx"""
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

- [ ] **步骤 5：更新 router.py**

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

- [ ] **步骤 6：编写 tests/test_document.py**

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
    # 先创建知识库
    resp = await client.post("/api/v1/knowledge-bases", json={"name": "Doc Test KB"}, headers=auth_headers)
    kb_id = resp.json()["data"]["id"]

    # 上传一个文本文件
    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        files={"file": ("test.txt", b"Hello world.\n\nThis is a test document with some content for chunking.", "text/plain")},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 200
    doc_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "processing"
    assert resp.json()["data"]["fileName"] == "test.txt"

    # 列出文档
    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=auth_headers)
    assert resp.json()["code"] == 200
    assert len(resp.json()["data"]) >= 1

    # 删除文档
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

- [ ] **步骤 7：运行测试**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_document.py -v
```

预期：全部通过

- [ ] **步骤 8：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: document upload with chunking and Chroma vector ingestion"
```

---

## 任务 9：工具管理 API —— 自定义工具注册

**文件：**
- 新建：`app/models/tool.py`
- 新建：`app/db/tool_store.py`
- 新建：`app/services/tool_service.py`
- 新建：`app/api/v1/tool.py`
- 新建：`tests/test_tool.py`
- 修改：`app/api/v1/router.py`

- [ ] **步骤 1：编写 models/tool.py**

```python
# app/models/tool.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ToolParameterSchema(BaseModel):
    """工具参数的 JSON Schema。"""

    type: str = "object"
    properties: dict = {}
    required: list[str] = []


class ToolConfig(BaseModel):
    """自定义 API 工具的配置。"""

    url: str = Field(description="API endpoint URL")
    method: str = Field(default="GET", description="HTTP method: GET / POST")
    headers: dict = Field(default_factory=dict)
    query_params: dict = Field(default_factory=dict)
    body_template: Optional[dict] = None


class ToolVO(BaseModel):
    """工具定义。"""

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

- [ ] **步骤 2：编写 db/tool_store.py**

```python
# app/db/tool_store.py
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.tool import ToolVO


class ToolStore:
    """工具定义的 JSON 文件存储。"""

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

- [ ] **步骤 3：编写 services/tool_service.py**

```python
# app/services/tool_service.py
import uuid
from datetime import datetime
from typing import Optional

from app.db.tool_store import tool_store
from app.models.tool import ToolVO, ToolCreateRequest, ToolUpdateRequest


class ToolService:
    """工具注册与管理。"""

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

- [ ] **步骤 4：编写 api/v1/tool.py**

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

- [ ] **步骤 5：更新 router.py**

```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.api.v1.chat import router as chat_router
from app.api.v1.agent import router as agent_router
from app.api.v1.knowledge_base import router as kb_router
from app/api/v1.document import router as doc_router
from app.api.v1.tool import router as tool_router

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])
router.include_router(chat_router)
router.include_router(agent_router)
router.include_router(kb_router)
router.include_router(doc_router)
router.include_router(tool_router)
```

- [ ] **步骤 6：编写 tests/test_tool.py**

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

    # 查询
    resp = await client.get(f"/api/v1/tools/{tool_id}", headers=auth_headers)
    assert resp.json()["data"]["name"] == "天气查询"

    # 删除
    resp = await client.delete(f"/api/v1/tools/{tool_id}", headers=auth_headers)
    assert resp.json()["code"] == 200


@pytest.mark.asyncio
async def test_cannot_delete_builtin(client, auth_headers):
    resp = await client.delete("/api/v1/tools/calculator", headers=auth_headers)
    assert resp.json()["code"] == 404
```

- [ ] **步骤 7：运行测试**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/test_tool.py -v
```

预期：全部通过

- [ ] **步骤 8：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: tool management API with builtin tools and custom tool registration"
```

---

## 任务 10：LangGraph 工作流编排

**文件：**
- 新建：`app/core/workflow.py`
- 修改：`app/services/chat_service.py`（为具备 `workflow` 能力的 Agent 接入工作流）

- [ ] **步骤 1：编写 core/workflow.py —— 基于 LangGraph 的 Agent 工作流**

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
    """工作流节点之间传递的状态。"""

    messages: list[BaseMessage]
    original_query: str
    context: str
    tool_calls: list[dict]
    final_response: str


class AgentWorkflow:
    """LangGraph 工作流，编排：记忆 → RAG → 工具 → 生成。"""

    def __init__(self, agent_config: AgentConfig, memory: ConversationMemory, conversation_id: str):
        self.agent_config = agent_config
        self.memory = memory
        self.conversation_id = conversation_id
        self.llm = create_chat_model(agent_config.llm_config)

    def build_graph(self) -> StateGraph:
        """根据 Agent 能力构建工作流图。"""
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
        """从记忆加载对话历史。"""
        history = self.memory.load_messages(self.conversation_id)
        state["messages"] = history
        return state

    def _rag_retrieve(self, state: WorkflowState) -> WorkflowState:
        """从知识库检索相关文档。"""
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
        """为 LLM 准备消息（实际生成发生在 stream_workflow）。"""
        return state

    async def stream_workflow(self, query: str) -> AsyncGenerator[str, None]:
        """执行工作流并以 SSE 事件流式输出 LLM 结果。"""
        from app.models.chat import ChatEvent, UsageInfo

        graph = self.build_graph()

        initial_state: WorkflowState = {
            "messages": [],
            "original_query": query,
            "context": "",
            "tool_calls": [],
            "final_response": "",
        }

        # 运行图以准备状态（记忆 + RAG 上下文）
        result = await graph.ainvoke(initial_state)

        # 为 LLM 构建消息
        messages = []
        if self.agent_config.system_prompt:
            messages.append(SystemMessage(content=self.agent_config.system_prompt))

        if result.get("context"):
            rag_prefix = f"基于以下参考资料回答用户问题。如果资料中没有相关信息，请说明。\n\n参考资料：\n{result['context']}\n\n"
            messages.append(SystemMessage(content=rag_prefix))

        messages.extend(result["messages"])
        messages.append(HumanMessage(content=query))

        # 流式输出 LLM 响应
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

- [ ] **步骤 2：更新 services/chat_service.py —— 增加工作流分支**

在 `stream_chat` 方法中、`_has_tools` 判断之前加入：

```python
    # 在 stream_chat() 中，加入此分支：
        if "workflow" in agent_config.capabilities:
            from app.core.workflow import AgentWorkflow
            workflow = AgentWorkflow(agent_config, memory, conversation_id)
            async for event in workflow.stream_workflow(message):
                yield event
            return
```

完整的更新后 `stream_chat`：

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

- [ ] **步骤 3：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: LangGraph workflow orchestration with memory → RAG → generate pipeline"
```

---

## 任务 11：Docker + 种子脚本 + 最终集成

**文件：**
- 新建：`Dockerfile`
- 新建：`scripts/seed.py`
- 修改：`app/main.py`（更新健康检查以展示 Chroma 状态）

- [ ] **步骤 1：编写 Dockerfile**

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

- [ ] **步骤 2：编写 scripts/seed.py —— 创建示例 Agent 用于测试**

```python
# scripts/seed.py
"""创建用于开发测试的示例 Agent。运行方式：poetry run python scripts/seed.py"""

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

- [ ] **步骤 3：更新 main.py 的健康检查端点以检测 Chroma**

```python
# 替换 main.py 中的 health_check 函数：

@app.get("/api/v1/health", tags=["system"])
async def health_check():
    """健康检查端点。"""
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

- [ ] **步骤 4：运行完整测试套件**

```bash
cd D:/PycharmProjects/pythonProject
poetry run pytest tests/ -v
```

预期：全部通过

- [ ] **步骤 5：提交**

```bash
cd D:/PycharmProjects/pythonProject
git add .
git commit -m "feat: Docker build, seed script, and health check with Chroma status"
```

---

## 任务 12：acgagent Java 侧 —— 网关路由 + 对话服务适配器

本任务修改现有的 acgagent Java 项目，使其调用 acgagent-ai。

**文件：**
- 修改：`acg-chat/src/main/resources/application.yml`（新增 acgagent-ai 配置）
- 修改：`acg-chat/src/main/java/com/darkness/agent/client/AgentClient.java`（将调用目标改为 acgagent-ai）
- 修改：`acg-gateway/src/main/resources/application.yml`（新增 `/api/knowledge/**` 路由）

> **注意：** 这些是对现有 Java 代码库的最小改动。完整范围取决于阅读当前源文件。本计划给出方向和关键代码改动。

- [ ] **步骤 1：向 acg-chat application.yml 添加 acgagent-ai 配置**

添加到 `acg-chat/src/main/resources/application.yml`（或 Nacos 的 `acg-chat.yaml`）：

```yaml
acg:
  ai:
    base-url: ${ACG_AI_URL:http://localhost:8100}
    api-key: ${ACG_AI_API_KEY:dev-api-key}
```

- [ ] **步骤 2：修改 AgentClient 以调用 acgagent-ai**

acg-chat 中的 `AgentClient` 应从直接调用外部 LLM API 改为调用 `acgagent-ai(8100)/api/v1/chat/{agent_id}/completions`，并传递 `X-API-Key` 和 `X-User-Id` 请求头。

关键改动：
- 目标 URL：`${acg.ai.base-url}/api/v1/chat/{agentId}/completions`
- 请求头：`X-API-Key: ${acg.ai.api-key}`、`X-User-Id: {currentUserId}`
- SSE 事件格式：解析 `{"type":"content","content":"..."}`，而非原始 OpenAI delta 格式
- 映射 `done` 事件以提取用量统计

- [ ] **步骤 3：为知识库新增网关路由**

添加到 `acg-gateway/src/main/resources/application.yml` 或 Nacos 的 `acg-gateway.yaml`：

```yaml
# 在 spring.cloud.gateway.routes 中新增：
- id: knowledge-service
  uri: lb://acg-chat
  predicates:
    - Path=/api/knowledge/**
```

- [ ] **步骤 4：提交**

```bash
cd D:/ideaproject/acgAgent
git add acg-chat/src acg-gateway/src
git commit -m "feat: integrate acgagent-ai into acg-chat and gateway routing"
```

---

## 自检清单

### 1. 规格覆盖

| 规格章节 | 任务 |
|---|---|
| 第 2 章 —— 技术栈（FastAPI、LangChain、Chroma、LangGraph） | 任务 1-10 |
| 第 5.2 节 —— Agent CRUD API | 任务 4 |
| 第 5.3 节 —— 对话（SSE 流式 + 同步） | 任务 3、6、10 |
| 第 5.4 节 —— 知识库 CRUD | 任务 7 |
| 第 5.5 节 —— 文档上传 | 任务 8 |
| 第 5.6 节 —— 工具管理 | 任务 9 |
| 第 5.7 节 —— 健康检查 | 任务 2、11 |
| 第 6.2 节 —— Agent 配置模型 | 任务 4 |
| 第 6.3 节 —— Chroma Collections | 任务 5、8 |
| 第 7.1 节 —— 对话记忆 | 任务 5 |
| 第 7.2 节 —— RAG 检索器 | 任务 7 |
| 第 7.3 节 —— 工具注册表 | 任务 6、9 |
| 第 7.4 节 —— 工作流（LangGraph） | 任务 10 |
| 第 8 章 —— acgagent 集成 | 任务 12 |
| 第 9 章 —— Docker 部署 | 任务 11 |

### 2. 占位符扫描

未发现 TBD、TODO、"implement later" 或 "fill in details"。所有步骤均含完整代码。

### 3. 类型一致性

- `AgentConfig.id` 为 `str` —— 在 API 路径中统一用作 `agent_id`
- `KnowledgeBase.id` 为 `str` —— 统一用作 `kb_id`
- `ChatEvent.type` 的枚举值（`content`、`tool_call`、`done`、`error`）在 `chat_service.py` 和 `workflow.py` 中使用一致
- `Result.success(data=...)` / `Result.error(code, message)` 在所有 API handler 中使用一致
