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
    """知识条目类型：决定 details 字段结构（见 spec §3.3）。"""

    style = "style"
    character = "character"
    story = "story"


class EntryScope(str, Enum):
    """可见范围：public 全局共享；private 仅限所属 user_id。"""

    public = "public"
    private = "private"


class KnowledgeEntry(BaseModel):
    """结构化知识条目：风格 / 角色 / 故事，向量化进 ChromaDB collection kb_structured_entries。"""

    id: str = Field(default="", description="Auto-generated ID")
    type: EntryType
    scope: EntryScope
    user_id: Optional[str] = Field(default=None, description="private 必填；public 为 None")
    name: str = Field(description="条目名称")
    summary: str = Field(description="一句话概述，同时作为 embedding 文本")
    tags: list[str] = Field(default_factory=list, description="检索辅助标签")
    details: dict = Field(default_factory=dict, description="类型特有字段（spec §3.3）")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class KnowledgeEntryCreateRequest(BaseModel):
    """创建知识条目请求。"""

    type: EntryType
    scope: EntryScope
    user_id: Optional[str] = None  # scope=private 时必填
    name: str
    summary: str
    tags: list[str] = []
    details: dict = {}  # 结构由 type 决定（spec §3.3）


class KnowledgeEntryUpdateRequest(BaseModel):
    """更新知识条目请求（部分更新；type / user_id 不可变，传未知字段 → 422）。"""

    # type / user_id 不在此 → 不可变；extra=forbid 使传这些字段（或任何未知字段）→ 422（spec §6）
    model_config = ConfigDict(extra="forbid")
    scope: Optional[EntryScope] = None
    name: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    details: Optional[dict] = None
