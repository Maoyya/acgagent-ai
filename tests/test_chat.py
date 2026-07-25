"""
对话 API 测试。

覆盖场景：
- 缺少 message 字段的请求体校验
- 对话不存在的 Agent 返回 404
- 对话已禁用的 Agent 返回 400
- 同步/流式模式切换
"""
import pytest


@pytest.mark.asyncio
async def test_chat_missing_message(client, auth_headers):
    """请求体缺少 message 字段时返回 422 校验错误。"""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_sync_agent_not_found(client, auth_headers):
    """同步对话不存在的 Agent 返回业务层 404。"""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404


@pytest.mark.asyncio
async def test_chat_stream_agent_not_found(client, auth_headers):
    """流式对话不存在的 Agent 也返回 404（非 SSE）。"""
    resp = await client.post(
        "/api/v1/chat/nonexistent/completions",
        json={"message": "hello", "stream": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404


@pytest.mark.asyncio
async def test_chat_disabled_agent(client, auth_headers):
    """对话已禁用的 Agent（status=0）返回 400。"""
    # 创建 Agent
    resp = await client.post("/api/v1/agents?validate=false", json={
        "name": "Disabled Agent",
        "llm_config": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "temperature": 0.7,
        },
    }, headers=auth_headers)
    agent_id = resp.json()["data"]["id"]

    # 禁用 Agent
    await client.put(
        f"/api/v1/agents/{agent_id}?validate=false",
        json={"status": 0},
        headers=auth_headers,
    )

    # 尝试对话
    resp = await client.post(
        f"/api/v1/chat/{agent_id}/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400


@pytest.mark.asyncio
async def test_chat_missing_llm_key_returns_500_envelope(client, auth_headers, monkeypatch):
    """Agent 的 LLM key 无法解析时（api_key 空 + Settings 无对应 key），返回 Result.error(500) 信封，
    而不是让 ValueError 裸奔成无信封 500、或流式中途崩溃。

    为什么重要：resolve_api_key 的 fail-loud ValueError 必须被 chat 层在分流前转成受控错误，
    覆盖流式/同步（及 workflow）路径（C1/C2）。
    """
    from app.config import settings
    monkeypatch.setattr(settings, "llm_key_deepseek", "")  # 确保无可解析 key

    resp = await client.post("/api/v1/agents?validate=false", json={
        "name": "No-Key Agent",
        "llm_config": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            # 不再支持 agent 级 api_key；Settings 已 monkeypatch 为空 → resolve_api_key 必抛
            "temperature": 0.7,
        },
    }, headers=auth_headers)
    agent_id = resp.json()["data"]["id"]

    # 同步：应返回 code=500 信封（而非裸 500）
    resp = await client.post(
        f"/api/v1/chat/{agent_id}/completions",
        json={"message": "hello", "stream": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 500

    # 流式：同样应在分流前预检，返回 code=500 信封（而非 SSE 中途崩溃）
    resp = await client.post(
        f"/api/v1/chat/{agent_id}/completions",
        json={"message": "hello", "stream": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 500
    # C2 意图：必须是 JSON 信封（application/json），而非 SSE 流（text/event-stream）。
    # 预检若被移除，stream 分支会返回 StreamingResponse（恒 200），失败要到 SSE 中途才暴露——
    # 此断言把"在分流前拦下"这一意图锁定下来（Rule 9：业务逻辑变了测试要能失败）。
    assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_upload_image_returns_url(client, auth_headers, tmp_path, monkeypatch):
    """上传图片 → 200，返回 url，文件落到 storage_root_dir。"""
    from app.services import image_service
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")

    png = b"\x89PNG\r\n\x1a\n"
    resp = await client.post(
        "/api/v1/chat/images",
        files={"file": ("cat.png", png, "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    url = body["data"]["url"]
    assert url.startswith("http://x/up/")
    fname = url.rsplit("/", 1)[-1]
    assert (tmp_path / fname).read_bytes() == png


@pytest.mark.asyncio
async def test_upload_image_rejects_non_image(client, auth_headers, tmp_path, monkeypatch):
    """非图片 mime → 400。"""
    from app.services import image_service
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    resp = await client.post(
        "/api/v1/chat/images",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=auth_headers,
    )
    assert resp.json()["code"] == 400


@pytest.mark.asyncio
async def test_upload_rejects_oversize_via_streaming(client, auth_headers, monkeypatch):
    """分块读取累计超限时提前 400，而不是先把整个超大请求读进内存。

    为什么重要：旧实现 `await file.read()` 先把整文件缓冲进内存再做大小校验，
    攻击者上传超大请求即可 DoS 内存。分块 + running cap 让内存占用有界。
    """
    from app.services import image_service
    monkeypatch.setattr(image_service, "MAX_IMAGE_BYTES", 10)

    big = b"\x89PNG" + b"x" * 200  # 200 字节，远超 monkeypatch 后的 10 上限
    resp = await client.post(
        "/api/v1/chat/images",
        files={"file": ("cat.png", big, "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 400


@pytest.mark.asyncio
async def test_upload_returns_500_on_storage_error(client, auth_headers, tmp_path, monkeypatch):
    """落盘 OSError（盘满/权限）转成受控 500 信封，而非裸 500 堆栈。

    为什么重要：save_upload 的 write_bytes 可能抛 OSError，旧实现未捕获会让
    FastAPI 返回无信封 500。捕获后包成 Result.error(500) 与其他错误路径一致。
    """
    from app.services import image_service

    def _boom(filename, content, content_type):
        raise OSError("disk full")

    monkeypatch.setattr(image_service, "save_upload", _boom)

    resp = await client.post(
        "/api/v1/chat/images",
        files={"file": ("cat.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 500
    assert "message" in body  # Result 信封，而非裸 500


@pytest.mark.asyncio
async def test_chat_sync_missing_image_returns_500_envelope(client, auth_headers, monkeypatch):
    """同步对话 images 引用不存在的图片 → 受控 Result.error(500) 信封，而非裸 500。

    为什么重要：Fix A 后 to_data_urls 对缺失文件抛 FileNotFoundError；若 _build_messages
    在 try 外执行 + sync_chat 未包信封，错误会裸奔成无信封 500。本测试锁定该意图。
    """
    from app.services import image_service

    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages):
            captured["called"] = True  # 不应被调用（先在 _build_messages 失败）

            class _R:
                content = "x"
            return _R()

    monkeypatch.setattr("app.services.chat_service.create_chat_model", lambda cfg: _FakeLLM())
    from app.config import settings
    monkeypatch.setattr(settings, "llm_key_qwen", "sk-test")  # 预检通过，聚焦"图片缺失 → 500"

    resp = await client.post("/api/v1/agents?validate=false", json={
        "name": "Sync Img Agent",
        "llm_config": {
            "provider": "qwen",
            "model": "qwen-vl-max",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "temperature": 0.7,
        },
    }, headers=auth_headers)
    agent_id = resp.json()["data"]["id"]

    resp = await client.post(f"/api/v1/chat/{agent_id}/completions", json={
        "message": "describe",
        "images": ["http://x/does-not-exist.png"],
        "stream": False,
    }, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 500
    assert "message" in body  # 必须是 Result 信封
    assert not captured.get("called")  # LLM 不应被调用（_build_messages 先失败）


@pytest.mark.asyncio
async def test_chat_threads_images_to_model(client, auth_headers, tmp_path, monkeypatch):
    """意图：对话请求带 images 时，模型端收到多模态消息（端到端透传）。conversation_id 留空以规避 ChromaDB。"""
    from app.services import image_service
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", b"\x89PNG", "image/png")

    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages):
            captured["messages"] = messages

            class _R:
                content = "it's a cat"
            return _R()

    monkeypatch.setattr("app.services.chat_service.create_chat_model", lambda cfg: _FakeLLM())
    from app.config import settings
    monkeypatch.setattr(settings, "llm_key_qwen", "sk-test")  # 预检通过，让 LLM 真正被调用

    resp = await client.post("/api/v1/agents?validate=false", json={
        "name": "Vision Agent",
        "llm_config": {
            "provider": "qwen",
            "model": "qwen-vl-max",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "temperature": 0.7,
        },
    }, headers=auth_headers)
    agent_id = resp.json()["data"]["id"]

    resp = await client.post(f"/api/v1/chat/{agent_id}/completions", json={
        "message": "describe",
        "images": [ref.url],
        "stream": False,
    }, headers=auth_headers)
    assert resp.json()["code"] == 200
    last = captured["messages"][-1]
    assert isinstance(last.content, list)
    assert last.content[1]["type"] == "image_url"
