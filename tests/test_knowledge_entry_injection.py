"""自动注入集成测试：覆盖 chat/tool 路径(_build_messages)与 workflow 路径。"""
from types import SimpleNamespace
from langchain_core.messages import SystemMessage

from app.models.agent import AgentConfig, LLMConfig
from app.models.knowledge_entry import KnowledgeEntry, EntryType, EntryScope
from app.db.knowledge_entry_store import knowledge_entry_store


def _llm_cfg():
    # 返回真实 LLMConfig（而非 dict），与 AgentConfig.llm_config 字段类型一致（避免 Pyright 误报）。
    return LLMConfig(provider="p", model="m", base_url="u")


def _entry(eid, name, summary, type=EntryType.character):
    return KnowledgeEntry(id=eid, type=type, scope=EntryScope.public,
                          name=name, summary=summary, details={})


def _fake_memory():
    """_build_messages 会调用 memory.load_messages(...)，给一个空记忆桩。"""
    return SimpleNamespace(load_messages=lambda cid: [])


def test_build_messages_injects_when_active(monkeypatch):
    monkeypatch.setattr(knowledge_entry_store, "get",
                        lambda eid: _entry(eid, "初音", "歌姬") if eid == "e1" else None)
    from app.services.chat_service import ChatService
    cfg = AgentConfig(id="a1", name="A", system_prompt="你是助手",
                      active_entry_ids=["e1"], llm_config=_llm_cfg())
    msgs = ChatService()._build_messages(cfg, memory=_fake_memory(),
                                         message="你好", conversation_id="c1", images=None)
    sys = [m for m in msgs if isinstance(m, SystemMessage)]
    assert any("【参考设定】" in m.content and "初音" in m.content for m in sys)


def test_build_messages_zero_regression_when_empty(monkeypatch):
    monkeypatch.setattr(knowledge_entry_store, "get", lambda eid: None)
    from app.services.chat_service import ChatService
    cfg = AgentConfig(id="a1", name="A", system_prompt="你是助手",
                      active_entry_ids=[], llm_config=_llm_cfg())
    msgs = ChatService()._build_messages(cfg, memory=_fake_memory(),
                                         message="你好", conversation_id="c1", images=None)
    sys = [m for m in msgs if isinstance(m, SystemMessage)]
    assert len(sys) == 1 and sys[0].content == "你是助手"


def test_workflow_injects_when_active(monkeypatch):
    monkeypatch.setattr(knowledge_entry_store, "get",
                        lambda eid: _entry(eid, "初音", "歌姬") if eid == "e1" else None)
    from app.core.knowledge_injector import build_system_content
    cfg = AgentConfig(id="a1", name="A", system_prompt="你是助手",
                      capabilities=["workflow"], active_entry_ids=["e1"], llm_config=_llm_cfg())
    # workflow 路径的注入文本由 build_system_content 决定（避免真实调 LLM）
    content = build_system_content(cfg)
    assert "【参考设定】" in content and "初音" in content
