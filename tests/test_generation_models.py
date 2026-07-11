# tests/test_generation_models.py
import pytest
from pydantic import ValidationError

from app.models.generation import (
    GenerationStatus,
    GenerationTask,
    GenerationType,
    ImageGenerationRequest,
    VideoGenerationRequest,
)


def test_image_request_defaults():
    req = ImageGenerationRequest(prompt="a cat")
    assert req.size == "1024*1024"
    assert req.n == 1


def test_video_request_requires_image_url():
    with pytest.raises(ValidationError):
        VideoGenerationRequest(prompt="pan")  # 缺 image_url 必须报错


def test_task_roundtrip_serialization():
    from datetime import datetime

    now = datetime(2026, 7, 11, 12, 0, 0)
    task = GenerationTask(
        id="abc123",
        type=GenerationType.text_to_image,
        status=GenerationStatus.pending,
        prompt="a cat",
        provider_task_id="ds-1",
        created_at=now,
        updated_at=now,
    )
    restored = GenerationTask.model_validate_json(task.model_dump_json())
    assert restored.provider_task_id == "ds-1"
    assert restored.output_url is None
    assert restored.type == GenerationType.text_to_image
