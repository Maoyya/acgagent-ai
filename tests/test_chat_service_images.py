"""chat_service 图生文接入测试。

锁定意图（Rule 9）：
- 无图时 _build_messages 产出纯字符串 HumanMessage（零回归）；
- 有图时产出多模态 list（真实读盘转 base64）；
- 发图时存入记忆的是用户文字，不含图片负载（图片不入记忆）。
"""
import pytest
from langchain_core.messages import HumanMessage

from app.models.agent import AgentConfig, LLMConfig
from app.services import image_service
from app.services.chat_service import ChatService


def _agent():
    return AgentConfig(name="t", llm_config=LLMConfig(provider="x", model="m", base_url="http://x"))


class _NoHistoryMemory:
    def load_messages(self, conv_id):
        return []


def test_build_messages_no_images_is_plain_string():
    svc = ChatService()
    msgs = svc._build_messages(_agent(), _NoHistoryMemory(), "hello", "c1", images=None)
    assert isinstance(msgs[-1], HumanMessage)
    assert msgs[-1].content == "hello"


def test_build_messages_with_images_is_multimodal(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", b"\x89PNG", "image/png")

    svc = ChatService()
    msgs = svc._build_messages(_agent(), _NoHistoryMemory(), "describe", "c1", images=[ref.url])

    last = msgs[-1]
    assert isinstance(last, HumanMessage)
    assert isinstance(last.content, list)
    assert last.content[0] == {"type": "text", "text": "describe"}
    assert last.content[1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_sync_chat_persists_text_not_images(monkeypatch, tmp_path):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", b"\x89PNG", "image/png")

    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages):
            captured["messages"] = messages

            class _R:
                content = "reply"
            return _R()

    monkeypatch.setattr("app.services.chat_service.create_chat_model", lambda cfg: _FakeLLM())

    saved = {}

    class _Mem:
        def load_messages(self, conv_id):
            return []

        def save_user_message(self, conv, msg):
            saved["user"] = msg

        def save_assistant_message(self, conv, msg):
            saved["asst"] = msg

    monkeypatch.setattr(ChatService, "_build_memory", lambda self, cfg: _Mem())

    svc = ChatService()
    await svc.sync_chat(_agent(), "describe this", conversation_id="c1", images=[ref.url])

    assert saved["user"] == "describe this"                                   # 记忆只有文字
    assert captured["messages"][-1].content[0] == {"type": "text", "text": "describe this"}  # 模型收到多模态
