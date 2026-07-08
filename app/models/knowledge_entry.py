"""
结构化知识条目数据模型。

条目分 3 种 type（style/character/story），2 种 scope（public/private）。
type 决定 details 字段内容（见 spec §3.3）；scope=private 时 user_id 必填。
存储为 JSON（data/knowledge_entries/{id}.json），向量化进 ChromaDB collection kb_structured_entries。
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class EntryType(str, Enum):
    style = "style"
    character = "character"
    story = "story"


class EntryScope(str, Enum):
    public = "public"
    private = "private"


class KnowledgeEntry(BaseModel):
    id: str = Field(default="", description="Auto-generated ID")
    type: EntryType
    scope: EntryScope
    user_id: Optional[str] = Field(default=None, description="private 必填；public 为 None")
    name: str
    summary: str = Field(description="一句话概述，同时作为 embedding 文本")
    tags: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict, description="类型特有字段（spec §3.3）")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class KnowledgeEntryCreateRequest(BaseModel):
    type: EntryType
    scope: EntryScope
    user_id: Optional[str] = None
    name: str
    summary: str
    tags: list[str] = []
    details: dict = {}


class KnowledgeEntryUpdateRequest(BaseModel):
    # type 不在此 → 不可变；extra=forbid 使传 type（或任何未知字段）→ 422（spec §6）
    model_config = ConfigDict(extra="forbid")
    scope: Optional[EntryScope] = None
    user_id: Optional[str] = None
    name: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    details: Optional[dict] = None
