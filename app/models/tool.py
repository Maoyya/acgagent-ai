"""
工具数据模型。

支持两类工具：
- builtin: 内置工具（calculator/web_search/knowledge_search），无持久化配置
- api: 自定义 API 工具，通过 ToolConfig 定义 HTTP 调用参数
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ToolParameterSchema(BaseModel):
    """自定义工具的入参 JSON Schema（OpenAI function-calling 风格）。"""

    type: str = "object"  # 固定为 object
    properties: dict = {}  # 各参数定义
    required: list[str] = []  # 必填参数名


class ToolConfig(BaseModel):
    """自定义 API 工具的 HTTP 调用配置。"""

    url: str = Field(description="API endpoint URL")
    method: str = Field(default="GET", description="HTTP method: GET / POST")
    headers: dict = Field(default_factory=dict, description="请求头")
    query_params: dict = Field(default_factory=dict, description="URL query 参数")
    body_template: Optional[dict] = Field(default=None, description="POST body 模板")


class ToolVO(BaseModel):
    """工具实体：builtin 无 config，api 类型通过 config 定义 HTTP 调用。"""

    id: str = Field(default="", description="Auto-generated ID")
    name: str = Field(description="Tool display name")
    description: str = Field(description="Tool description for LLM")
    type: str = Field(default="api", description="Tool type: api / builtin")
    config: Optional[ToolConfig] = Field(default=None, description="api 类型的 HTTP 配置；builtin 为空")
    parameters: ToolParameterSchema = Field(default_factory=ToolParameterSchema, description="入参 schema")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class ToolCreateRequest(BaseModel):
    """创建自定义工具请求。"""

    name: str
    description: str
    type: str = "api"  # 固定 api（builtin 不可创建）
    config: Optional[ToolConfig] = None  # HTTP 调用配置
    parameters: ToolParameterSchema = ToolParameterSchema()  # 入参 schema


class ToolUpdateRequest(BaseModel):
    """更新自定义工具请求（部分更新）。"""

    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[ToolConfig] = None
    parameters: Optional[ToolParameterSchema] = None
