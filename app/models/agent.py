"""
Agent 数据模型。

AgentConfig 是核心实体，包含 LLM 配置、记忆策略、能力标签和关联资源。
LLMConfig 通过 base_url 支持任意 OpenAI 兼容的模型提供商。
MemoryConfig 支持 conversation_window（滑动窗口）和 none（无记忆）两种模式。
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = Field(description="Provider identifier: doubao / qwen / deepseek")
    model: str = Field(description="Model name")
    base_url: str = Field(description="API base URL (OpenAI-compatible)")
    api_key: str = Field(description="API key")
    temperature: float = Field(default=0.7, description="Generation temperature")
    max_tokens: int = Field(default=4096, description="Max output tokens")
    top_p: float = Field(default=0.9, description="Top-P sampling")


class MemoryConfig(BaseModel):
    type: str = Field(default="conversation_window", description="Memory type: conversation_window / summary / none")
    max_tokens: int = Field(default=8000, description="Context window size in tokens")


class AgentConfig(BaseModel):
    id: str = Field(default="", description="Auto-generated unique ID")
    name: str = Field(description="Agent display name")
    description: Optional[str] = Field(default=None, description="Agent description")
    system_prompt: Optional[str] = Field(default=None, description="System prompt for the LLM")
    llm_config: LLMConfig = Field(description="LLM configuration")
    memory_config: MemoryConfig = Field(default_factory=MemoryConfig, description="Memory configuration")
    capabilities: list[str] = Field(default_factory=lambda: ["chat"], description="Capabilities: chat / rag / tool_use / workflow")
    knowledge_base_ids: list[str] = Field(default_factory=list, description="Associated knowledge base IDs")
    tool_ids: list[str] = Field(default_factory=list, description="Associated tool IDs")
    active_entry_ids: list[str] = Field(default_factory=list, description="激活自动注入的结构化知识条目 ID")
    status: int = Field(default=1, description="1=enabled, 0=disabled")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AgentCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_config: LLMConfig
    memory_config: MemoryConfig = MemoryConfig()
    capabilities: list[str] = ["chat"]
    knowledge_base_ids: list[str] = []
    tool_ids: list[str] = []
    active_entry_ids: list[str] = []


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_config: Optional[LLMConfig] = None
    memory_config: Optional[MemoryConfig] = None
    capabilities: Optional[list[str]] = None
    knowledge_base_ids: Optional[list[str]] = None
    tool_ids: Optional[list[str]] = None
    active_entry_ids: Optional[list[str]] = None
    status: Optional[int] = None
