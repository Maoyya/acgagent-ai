"""
Agent 配置模型和数据完整性测试。

覆盖场景：
- AgentConfig 默认值（status=1, capabilities=["chat"]）
- AgentCreateRequest 必填字段校验
- AgentUpdateRequest 部分更新（exclude_unset）行为
- LLMConfig 默认值
- MemoryConfig 默认值
"""
import pytest
from datetime import datetime
from app.models.agent import (
    AgentConfig,
    AgentCreateRequest,
    AgentUpdateRequest,
    LLMConfig,
    MemoryConfig,
)


def test_llm_config_defaults():
    """LLMConfig 的 temperature/max_tokens/top_p 有合理默认值。"""
    config = LLMConfig(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test",
    )
    assert config.temperature == 0.7
    assert config.max_tokens == 4096
    assert config.top_p == 0.9


def test_memory_config_defaults():
    """MemoryConfig 默认为 conversation_window，8000 token 预算。"""
    config = MemoryConfig()
    assert config.type == "conversation_window"
    assert config.max_tokens == 8000


def test_agent_config_defaults():
    """AgentConfig 默认启用，能力为 chat。"""
    agent = AgentConfig(
        name="Test",
        llm_config=LLMConfig(
            provider="test", model="test",
            base_url="http://localhost", api_key="key",
        ),
    )
    assert agent.status == 1
    assert agent.capabilities == ["chat"]
    assert agent.knowledge_base_ids == []
    assert agent.tool_ids == []
    assert agent.id == ""  # 创建时未指定，由 service 层生成
    assert isinstance(agent.created_at, datetime)


def test_create_request_missing_name():
    """AgentCreateRequest 缺少 name 时 Pydantic 校验失败。"""
    with pytest.raises(Exception):
        AgentCreateRequest(
            llm_config=LLMConfig(
                provider="test", model="test",
                base_url="http://localhost", api_key="key",
            ),
        )


def test_create_request_missing_llm_config():
    """AgentCreateRequest 缺少 llm_config 时校验失败。"""
    with pytest.raises(Exception):
        AgentCreateRequest(name="No LLM")


def test_update_request_exclude_unset():
    """AgentUpdateRequest 只有序列化显式传入的字段。

    这是部分更新（PATCH 语义）的关键：未传入的字段不出现在 model_dump 中，
    service 层据此只更新有变化的字段。
    """
    req = AgentUpdateRequest(name="New Name")
    data = req.model_dump(exclude_unset=True)
    assert "name" in data
    assert "description" not in data
    assert "system_prompt" not in data


def test_update_request_all_fields_none():
    """AgentUpdateRequest 所有字段均可选，全部为 None 时 exclude_unset 为空。"""
    req = AgentUpdateRequest()
    data = req.model_dump(exclude_unset=True)
    assert data == {}
