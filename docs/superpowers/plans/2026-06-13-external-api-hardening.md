# External API Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing single-key API auth so the in-cluster Java backend can call acgagent-ai safely — 401 on missing/wrong key, constant-time compare, default-key startup warning — without adding new subsystems.

**Architecture:** Two surgical changes to existing files. (1) `app/api/deps.py::verify_api_key` makes the header optional, returns 401 for missing/empty keys, and compares with `secrets.compare_digest`. (2) `app/main.py` adds a `_warn_default_api_key()` helper invoked from the lifespan that logs a WARNING when the key is still the default. API-key provisioning (`.env`, gitignored — already done) and network-layer restriction are operational/deployment-side, not code tasks here.

**Tech Stack:** FastAPI, pydantic-settings, pytest + pytest-asyncio, httpx `ASGITransport`.

**Spec:** `docs/superpowers/specs/2026-06-13-external-api-hardening-design.md`

**Conventions:**
- All Python/pytest commands use the project interpreter: `C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe` (conda env `acgagent-ai`, Python 3.13). The full path is used in every command below.
- Working directory is the repo root (`C:/Users/10173/PycharmProjects/acgagent-ai`).
- TDD per task: write test → see it fail → implement → see it pass → commit.

---

## File Structure

- **Modify** `app/api/deps.py` — harden `verify_api_key` (optional header, 401 on missing/empty, `secrets.compare_digest`).
- **Modify** `app/main.py` — add `_warn_default_api_key()` helper; call it from `lifespan` startup.
- **Create** `tests/test_auth.py` — auth edge cases: valid key 200, missing key 401, wrong key 401.
- **Create** `tests/test_main.py` — `_warn_default_api_key()` behavior via `caplog`.

---

### Task 1: Harden `verify_api_key` (missing key → 401, constant-time compare)

**Files:**
- Modify: `app/api/deps.py` (the `verify_api_key` function)
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth.py`:

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

- [ ] **Step 2: Run tests to verify failure**

Run:
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest tests/test_auth.py -v
```
Expected: `test_protected_without_key_returns_401` FAILS (`assert 401 == 422`). The other two PASS (valid key already 200; wrong key already 401). The missing-key failure is what this task fixes.

- [ ] **Step 3: Implement the hardened `verify_api_key`**

Replace the entire contents of `app/api/deps.py` with:

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

- [ ] **Step 4: Run tests to verify pass**

Run:
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest tests/test_auth.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/deps.py tests/test_auth.py
git commit -m "feat(api): return 401 on missing key and use constant-time compare"
```

---

### Task 2: Default-key startup warning

**Files:**
- Modify: `app/main.py` (add helper + call from `lifespan`)
- Create: `tests/test_main.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main.py`:

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

- [ ] **Step 2: Run tests to verify failure**

Run:
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest tests/test_main.py -v
```
Expected: FAIL with `AttributeError: module 'app.main' has no attribute '_warn_default_api_key'`.

- [ ] **Step 3: Implement the helper and wire it into the lifespan**

In `app/main.py`:

(a) Add this function immediately after the `logger = logging.getLogger("acgagent-ai")` line (before `@asynccontextmanager`):

```python
def _warn_default_api_key() -> None:
    """api_key 仍为默认值时打印告警（生产应通过 ACG_AI_API_KEY 覆盖）。"""
    if settings.api_key == "dev-api-key":
        logger.warning(
            "Using default API key 'dev-api-key'; set ACG_AI_API_KEY in production."
        )
```

(b) Inside `lifespan`, add one call line immediately after the `logging.basicConfig(...)` line (keep all surrounding lines unchanged):

```python
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    _warn_default_api_key()
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest tests/test_main.py -v
```
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat(main): warn when API key is still the default"
```

---

### Task 3: Full regression + connectivity re-verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite**

Run:
```bash
"C:/Users/10173/miniconda3/envs/acgagent-ai/python.exe" -m pytest -q
```
Expected: all tests PASS (existing suite + new `tests/test_auth.py` + `tests/test_main.py`), no failures.

- [ ] **Step 2: Re-verify live behavior (only if a server is running on 8100)**

The server reads `ACG_AI_API_KEY` from `.env`. Confirm the hardened behavior end-to-end:

```bash
KEY=$(grep ACG_AI_API_KEY .env | cut -d= -f2)
curl -sS -o /dev/null -w "no-key: %{http_code}\n" http://127.0.0.1:8100/api/v1/agents
curl -sS -o /dev/null -w "wrong:  %{http_code}\n" -H "X-API-Key: wrong" http://127.0.0.1:8100/api/v1/agents
curl -sS -o /dev/null -w "valid:  %{http_code}\n" -H "X-API-Key: $KEY" http://127.0.0.1:8100/api/v1/agents
```
Expected:
```
no-key: 401
wrong:  401
valid:  200
```
(`no-key` changed from 422 → 401.)

- [ ] **Step 3: No commit (verification only)**

All green ⇒ hardening complete.

---

## Self-Review (completed by plan author)

- **Spec coverage:** Spec §1 (deps.py) → Task 1; §2 (main.py warning) → Task 2; §3 (`.env` provisioning) + §4 (network restriction) → operational, noted in Architecture (not code); §5 (call convention/health) → confirmed by Task 3 live check; §6 (tests) → Tasks 1 & 2. No spec section lacks a task.
- **Placeholder scan:** None — all code blocks are complete; no TBD/TODO/"add error handling".
- **Type/name consistency:** `_warn_default_api_key` identical in Task 2 test and impl; `verify_api_key` signature consistent; `settings.api_key` used uniformly.
