# 对外 API 加固实施计划

> **致 agentic worker：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 来逐任务实现本计划。步骤使用复选框（`- [ ]`）语法进行进度追踪。

**目标：** 对现有的单 Key API 鉴权进行加固，使集群内的 Java 后端能安全地调用 acgagent-ai —— 缺失/错误 key 返回 401、常数时间比对、默认 key 启动告警 —— 不引入新的子系统。

**架构：** 对现有文件做两处外科手术式改动。(1) `app/api/deps.py::verify_api_key` 把请求头改为可选，缺失/空 key 返回 401，并用 `secrets.compare_digest` 比对。(2) `app/main.py` 新增 `_warn_default_api_key()` 辅助函数，在 lifespan 中调用，当 key 仍为默认值时打印 WARNING 日志。API Key 的注入（`.env`，已 gitignore —— 已完成）和网络层限制属于运维/部署侧工作，不是本计划的代码任务。

**技术栈：** FastAPI、pydantic-settings、pytest + pytest-asyncio、httpx `ASGITransport`。

**规格：** `docs/superpowers/specs/2026-06-13-external-api-hardening-design.md`

**约定：**
- 所有 Python/pytest 命令使用项目解释器：`C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe`（conda 环境 `acgagent-ai`，Python 3.13）。下方每条命令均使用该完整路径。
- 工作目录为仓库根目录（`C:/Users/10173/PycharmProjects/acgagent-ai`）。
- 每个任务遵循 TDD：写测试 → 看它失败 → 实现 → 看它通过 → 提交。

---

## 文件结构

- **修改** `app/api/deps.py` —— 加固 `verify_api_key`（可选请求头、缺失/空返回 401、`secrets.compare_digest`）。
- **修改** `app/main.py` —— 新增 `_warn_default_api_key()` 辅助函数；在 `lifespan` 启动段调用。
- **新建** `tests/test_auth.py` —— 鉴权边界用例：合法 key 200、缺失 key 401、错误 key 401。
- **新建** `tests/test_main.py` —— 通过 `caplog` 验证 `_warn_default_api_key()` 的行为。

---

### 任务 1：加固 `verify_api_key`（缺失 key → 401，常数时间比对）

**文件：**
- 修改：`app/api/deps.py`（`verify_api_key` 函数）
- 新建：`tests/test_auth.py`

- [ ] **步骤 1：编写失败的测试**

新建 `tests/test_auth.py`：

```python
"""
API 鉴权边界测试：合法 key / 缺失 key / 错误 key。
"""
import pytest


@pytest.mark.asyncio
async def test_protected_with_valid_key(client, auth_headers):
    """合法 key 访问受保护端点返回 200。"""
    resp = await client.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_without_key_returns_401(client):
    """缺失 X-API-Key 返回 401（加固前为 422）。"""
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_with_wrong_key_returns_401(client):
    """错误的 X-API-Key 返回 401。"""
    resp = await client.get("/api/v1/agents", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401
```

- [ ] **步骤 2：运行测试以验证失败**

运行：
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest tests/test_auth.py -v
```
预期：`test_protected_without_key_returns_401` 失败（`assert 401 == 422`）。另外两个通过（合法 key 已是 200；错误 key 已是 401）。缺失 key 的失败正是本任务要修复的。

- [ ] **步骤 3：实现加固后的 `verify_api_key`**

用以下内容替换 `app/api/deps.py` 的全部内容：

```python
"""
API 依赖注入。

verify_api_key: 所有 /api/v1/* 路由的认证守卫，校验 X-API-Key Header。
get_user_id: 可选依赖，从 X-User-Id Header 提取用户标识（预留多租户支持）。
"""
import secrets

from fastapi import Header, HTTPException


async def verify_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> str:
    """校验 API Key。所有 v1 路由默认依赖此函数。

    - 缺失/空 key → 401 Missing API key
    - 比对使用 secrets.compare_digest（常数时间，防计时侧信道）；不符 → 401
    """
    from app.config import settings

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


async def get_user_id(x_user_id: str | None = Header(None, alias="X-User-Id")) -> str | None:
    """从请求头提取用户 ID，未传递时返回 None。"""
    return x_user_id
```

- [ ] **步骤 4：运行测试以验证通过**

运行：
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest tests/test_auth.py -v
```
预期：3 个测试全部通过。

- [ ] **步骤 5：提交**

```bash
git add app/api/deps.py tests/test_auth.py
git commit -m "feat(api): return 401 on missing key and use constant-time compare"
```

---

### 任务 2：默认 key 启动告警

**文件：**
- 修改：`app/main.py`（新增辅助函数 + 在 `lifespan` 中调用）
- 新建：`tests/test_main.py`

- [ ] **步骤 1：编写失败的测试**

新建 `tests/test_main.py`：

```python
"""
启动期默认 API Key 告警的单元测试。
"""
import logging

from app import main
from app.config import settings


def test_warn_default_key_logs_when_default(caplog, monkeypatch):
    """api_key 仍为默认值时，打印 WARNING。"""
    monkeypatch.setattr(settings, "api_key", "dev-api-key")
    caplog.set_level(logging.WARNING)
    main._warn_default_api_key()
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


def test_warn_default_key_silent_when_real(caplog, monkeypatch):
    """api_key 已改为真实值时，不打印 WARNING。"""
    monkeypatch.setattr(settings, "api_key", "some-real-key-xyz")
    caplog.set_level(logging.WARNING)
    main._warn_default_api_key()
    assert not [rec for rec in caplog.records if rec.levelno == logging.WARNING]
```

- [ ] **步骤 2：运行测试以验证失败**

运行：
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest tests/test_main.py -v
```
预期：失败，报 `AttributeError: module 'app.main' has no attribute '_warn_default_api_key'`。

- [ ] **步骤 3：实现辅助函数并接入 lifespan**

在 `app/main.py` 中：

(a) 在 `logger = logging.getLogger("acgagent-ai")` 这一行之后（`@asynccontextmanager` 之前）紧接着添加此函数：

```python
def _warn_default_api_key() -> None:
    """api_key 仍为默认值时打印告警（生产应通过 ACG_AI_API_KEY 覆盖）。"""
    if settings.api_key == "dev-api-key":
        logger.warning(
            "Using default API key 'dev-api-key'; set ACG_AI_API_KEY in production."
        )
```

(b) 在 `lifespan` 内部，`logging.basicConfig(...)` 这一行之后紧接着添加一行调用（保持其余各行不变）：

```python
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    _warn_default_api_key()
```

- [ ] **步骤 4：运行测试以验证通过**

运行：
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest tests/test_main.py -v
```
预期：两个测试均通过。

- [ ] **步骤 5：提交**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat(main): warn when API key is still the default"
```

---

### 任务 3：全量回归 + 连通性复验

**文件：** 无（仅验证）。

- [ ] **步骤 1：运行完整测试套件**

运行：
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest -q
```
预期：所有测试通过（既有套件 + 新增的 `tests/test_auth.py` + `tests/test_main.py`），无失败。

- [ ] **步骤 2：重新验证线上行为（仅当 8100 端口有服务在运行时）**

服务从 `.env` 读取 `ACG_AI_API_KEY`。端到端确认加固后的行为：

```bash
KEY=$(grep ACG_AI_API_KEY .env | cut -d= -f2)
curl -sS -o /dev/null -w "no-key: %{http_code}\n" http://127.0.0.1:8100/api/v1/agents
curl -sS -o /dev/null -w "wrong:  %{http_code}\n" -H "X-API-Key: wrong" http://127.0.0.1:8100/api/v1/agents
curl -sS -o /dev/null -w "valid:  %{http_code}\n" -H "X-API-Key: $KEY" http://127.0.0.1:8100/api/v1/agents
```
预期：
```
no-key: 401
wrong:  401
valid:  200
```
（`no-key` 从 422 变为 401。）

- [ ] **步骤 3：无需提交（仅验证）**

全部通过 ⇒ 加固完成。

---

## 自检（由计划作者完成）

- **规格覆盖：** 规格 §1（deps.py）→ 任务 1；§2（main.py 告警）→ 任务 2；§3（`.env` 注入）+ §4（网络限制）→ 运维侧，在「架构」中说明（非代码）；§5（调用约定/健康检查）→ 由任务 3 的线上检查确认；§6（测试）→ 任务 1 和 2。没有规格章节缺少对应任务。
- **占位符扫描：** 无 —— 所有代码块均完整；没有 TBD/TODO/"add error handling"。
- **类型/命名一致性：** `_warn_default_api_key` 在任务 2 的测试与实现中一致；`verify_api_key` 签名一致；`settings.api_key` 使用统一。
