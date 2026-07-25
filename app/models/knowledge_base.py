"""
知识库数据模型。

知识库定义了 Embedding 配置和分块策略，用于 RAG 检索。
每个知识库在 ChromaDB 中对应一个 collection（kb_{id}_chunks）。
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChunkConfig(BaseModel):
    chunk_size: int = Field(default=500, description="Max characters per chunk")
    chunk_overlap: int = Field(default=50, description="Overlap characters between chunks")
    separators: list[str] = Field(default_factory=lambda: ["\n\n", "\n", "。", " "], description="Split separators")


class EmbeddingConfig(BaseModel):
    provider: str = Field(default="zhipu", description="Provider: zhipu / doubao / qwen（须有对应 ACG_AI_LLM_KEY_<PROVIDER> 字段）")
    model: str = Field(default="embedding-3", description="Embedding model name")
    base_url: Optional[str] = Field(default=None, description="API base URL（为空时按 provider 取默认 OpenAI 兼容端点，见 app/core/embeddings.py）")
    # api_key 不在此配置：与 chat 共用同一 provider key，统一从 .env 取（ACG_AI_LLM_KEY_<PROVIDER>）。


class KnowledgeBase(BaseModel):
    """知识库实体：聚合 Embedding / 分块配置，关联多个文档；对应 ChromaDB collection kb_{id}_chunks。"""

    id: str = Field(default="", description="Auto-generated ID")
    name: str = Field(description="Knowledge base name")
    description: Optional[str] = Field(default=None, description="Description")
    embedding_config: EmbeddingConfig = Field(default_factory=EmbeddingConfig, description="向量化模型配置")
    chunk_config: ChunkConfig = Field(default_factory=ChunkConfig, description="文档分块策略")
    document_count: int = Field(default=0, description="关联文档数")
    chunk_count: int = Field(default=0, description="已向量化的分片总数")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class KnowledgeBaseCreateRequest(BaseModel):
    """创建知识库请求。"""

    name: str  # 知识库名称
    description: Optional[str] = None  # 可选描述
    embedding_config: EmbeddingConfig = EmbeddingConfig()  # 向量化配置，缺省走默认
    chunk_config: ChunkConfig = ChunkConfig()  # 分块策略，缺省走默认


class KnowledgeBaseUpdateRequest(BaseModel):
    """更新知识库请求（部分更新；embedding_config 创建后不可改）。"""

    name: Optional[str] = None
    description: Optional[str] = None
    chunk_config: Optional[ChunkConfig] = None  # 仅可调分块策略
