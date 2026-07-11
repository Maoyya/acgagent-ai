"""
媒体生成数据模型。

文生图 / 图生视频 的请求与任务实体。任务持久化由 app/db/generation_store.py 负责。
Result<T> 信封沿用 app/models/common.py，不在此重复定义。
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GenerationType(str, Enum):
    text_to_image = "text_to_image"
    image_to_video = "image_to_video"


class GenerationStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(description="文生图提示词")
    size: str = Field(default="1024*1024", description="图片尺寸，如 1024*1024")
    n: int = Field(default=1, description="生成数量")


class VideoGenerationRequest(BaseModel):
    prompt: str = Field(description="图生视频提示词")
    image_url: str = Field(description="公网可达的首帧图 URL（dashscope 需能拉取）")
    duration: int = Field(default=5, description="视频时长（秒），wan2.1 支持值")


class GenerationTask(BaseModel):
    id: str
    type: GenerationType
    status: GenerationStatus
    prompt: str
    input_image_url: Optional[str] = None       # 仅图生视频
    provider: str = "dashscope"
    provider_task_id: Optional[str] = None      # dashscope 返回的 task_id
    output_url: Optional[str] = None            # 本地持久 URL
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
