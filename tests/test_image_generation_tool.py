"""文生图工具单元测试。monkeypatch generation_service，不真实调 dashscope。"""
from app.models.common import Result
from app.services.generation_service import generation_service
from app.tools.image_generation import ImageGenerationTool


async def _ok(req, user_id):
    assert req.prompt
    assert req.size == "1024*1024"
    assert req.n == 1
    return Result.success({"task_id": "tid123"})


async def _err(req, user_id):
    return Result.error(500, "generation api key not configured")


def test_execute_success_returns_task_id_and_poll_hint(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_image", _ok)
    out = ImageGenerationTool().execute(prompt="一只在窗台的猫")
    assert "tid123" in out
    assert "/api/v1/generations/tasks/tid123" in out


def test_execute_missing_prompt_returns_hint():
    out = ImageGenerationTool().execute(prompt="")
    assert out == "请提供文生图提示词"


def test_execute_failure_propagates_message(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_image", _err)
    out = ImageGenerationTool().execute(prompt="一只猫")
    assert "文生图提交失败" in out
    assert "generation api key not configured" in out


async def _no_task_id(req, user_id):
    return Result.success({})


def test_execute_success_without_task_id_fails_loud(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_image", _no_task_id)
    out = ImageGenerationTool().execute(prompt="一只猫")
    assert "缺少 task_id" in out
