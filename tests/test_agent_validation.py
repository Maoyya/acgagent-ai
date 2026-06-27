"""Agent 引用完整性校验单测（_validate_references）。

锁定意图（Rule 9）：
- 不存在的 kb_id / 自定义 tool_id 必须被拦下（避免配出引用悬空的 Agent）。
- 内置 tool_id（calculator 等）合法，不查 tool_store（内置工具不入库）。
"""
import pytest

from app.services.agent_service import agent_service


def test_accepts_empty_references():
    """空 kb/tool → 通过（默认 Agent 无引用）。"""
    agent_service._validate_references([], [])  # 不抛


def test_rejects_missing_knowledge_base():
    """不存在的 kb_id → ValueError 列出缺失。"""
    with pytest.raises(ValueError) as exc:
        agent_service._validate_references(["no-such-kb"], [])
    assert "no-such-kb" in str(exc.value)


def test_accepts_builtin_tool_ids_without_store():
    """内置 tool_id 合法，不查 tool_store。"""
    agent_service._validate_references([], ["calculator", "web_search", "knowledge_search"])


def test_rejects_missing_custom_tool():
    """不存在的自定义 tool_id → ValueError 列出缺失。"""
    with pytest.raises(ValueError) as exc:
        agent_service._validate_references([], ["no-such-tool"])
    assert "no-such-tool" in str(exc.value)


def test_message_lists_all_missing():
    """同时缺失 kb 与 tool → 一条消息列全两类缺失。"""
    with pytest.raises(ValueError) as exc:
        agent_service._validate_references(["bad-kb"], ["bad-tool"])
    msg = str(exc.value)
    assert "bad-kb" in msg and "bad-tool" in msg
