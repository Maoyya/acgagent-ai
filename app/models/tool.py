from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ToolParameterSchema(BaseModel):
    type: str = "object"
    properties: dict = {}
    required: list[str] = []


class ToolConfig(BaseModel):
    url: str = Field(description="API endpoint URL")
    method: str = Field(default="GET", description="HTTP method: GET / POST")
    headers: dict = Field(default_factory=dict)
    query_params: dict = Field(default_factory=dict)
    body_template: Optional[dict] = None


class ToolVO(BaseModel):
    id: str = Field(default="", description="Auto-generated ID")
    name: str = Field(description="Tool display name")
    description: str = Field(description="Tool description for LLM")
    type: str = Field(default="api", description="Tool type: api / builtin")
    config: Optional[ToolConfig] = None
    parameters: ToolParameterSchema = Field(default_factory=ToolParameterSchema)
    created_at: datetime = Field(default_factory=datetime.now)


class ToolCreateRequest(BaseModel):
    name: str
    description: str
    type: str = "api"
    config: Optional[ToolConfig] = None
    parameters: ToolParameterSchema = ToolParameterSchema()


class ToolUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[ToolConfig] = None
    parameters: Optional[ToolParameterSchema] = None
