from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DocumentVO(BaseModel):
    id: str = Field(default="", description="Auto-generated ID")
    knowledge_base_id: str = Field(description="Parent knowledge base ID")
    file_name: str = Field(description="Original file name")
    file_size: int = Field(default=0, description="File size in bytes")
    chunk_count: int = Field(default=0, description="Number of chunks after processing")
    status: str = Field(default="processing", description="processing / completed / failed")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(default_factory=datetime.now)
