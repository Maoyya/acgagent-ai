"""图生视频工具单元测试。monkeypatch generation_service，不真实调 dashscope。"""
from app.models.common import Result
from app.services.generation_service import generation_service
from app.tools.video_generation import VideoGenerationTool


async def _ok(req, user_id):
    assert req.prompt
    assert req.image_url
    assert req.duration == 5
    return Result.success({"task_id": "vid456"})


async def _err(req, user_id):
    return Result.error(500, "generation api key not configured")


def test_execute_success_returns_task_id_and_poll_hint(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_video", _ok)
    out = VideoGenerationTool().execute(prompt="猫从窗台跳下", image_url="https://x/y.png")
    assert "vid456" in out
    assert "/api/v1/generations/tasks/vid456" in out


def test_execute_missing_prompt_returns_hint():
    out = VideoGenerationTool().execute(prompt="", image_url="https://x/y.png")
    assert out == "请提供图生视频提示词"


def test_execute_missing_image_url_returns_hint():
    out = VideoGenerationTool().execute(prompt="猫跑", image_url="")
    assert out == "请提供公网可达的首帧图 URL"


def test_execute_failure_propagates_message(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_video", _err)
    out = VideoGenerationTool().execute(prompt="猫跑", image_url="https://x/y.png")
    assert "图生视频提交失败" in out
    assert "generation api key not configured" in out


async def _no_task_id(req, user_id):
    return Result.success({})


def test_execute_success_without_task_id_fails_loud(monkeypatch):
    monkeypatch.setattr(generation_service, "submit_video", _no_task_id)
    out = VideoGenerationTool().execute(prompt="猫跑", image_url="https://x/y.png")
    assert "缺少 task_id" in out
