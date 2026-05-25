from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChunkConfig(BaseModel):
    chunk_size: int = Field(default=500, description="Max characters per chunk")
    chunk_overlap: int = Field(default=50, description="Overlap characters between chunks")
    separators: list[str] = Field(default_factory=lambda: ["\n\n", "\n", "。", " "], description="Split separators")


class EmbeddingConfig(BaseModel):
    provider: str = Field(default="dashscope", description="Provider: dashscope / openai")
    model: str = Field(default="text-embedding-v3", description="Embedding model name")
    base_url: Optional[str] = Field(default=None, description="API base URL")
    api_key: Optional[str] = Field(default=None, description="API key")


class KnowledgeBase(BaseModel):
    id: str = Field(default="", description="Auto-generated ID")
    name: str = Field(description="Knowledge base name")
    description: Optional[str] = Field(default=None, description="Description")
    embedding_config: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    chunk_config: ChunkConfig = Field(default_factory=ChunkConfig)
    document_count: int = Field(default=0)
    chunk_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    embedding_config: EmbeddingConfig = EmbeddingConfig()
    chunk_config: ChunkConfig = ChunkConfig()


class KnowledgeBaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    chunk_config: Optional[ChunkConfig] = None
