"""系统提示词生成功能测试。"""
import pytest


def test_prompt_mode_enum_values():
    """PromptMode 应只有 acg / compliant 两个值，且为 str 枚举（便于 JSON 序列化）。"""
    from app.models.prompt import PromptMode
    assert PromptMode("acg") is PromptMode.acg
    assert PromptMode("compliant") is PromptMode.compliant
    assert {m.value for m in PromptMode} == {"acg", "compliant"}


def test_moderation_verdict_defaults():
    """通过的裁决默认无违规/原因，confidence 默认 1.0，mode 必填。"""
    from app.models.prompt import ModerationVerdict, PromptMode
    v = ModerationVerdict(passed=True, mode=PromptMode.acg)
    assert v.violated_rules == []
    assert v.reasons == []
    assert v.confidence == 1.0
    assert v.mode is PromptMode.acg


def test_cost_estimate_defaults():
    """估算一期 est_completion_tokens 恒为 0；prompt_tokens 与 model 必填。"""
    from app.models.prompt import CostEstimate
    e = CostEstimate(prompt_tokens=42, model="deepseek-chat")
    assert e.est_completion_tokens == 0
    assert e.prompt_tokens == 42
