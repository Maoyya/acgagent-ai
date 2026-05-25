from typing import Optional
from pydantic import BaseModel


class ChatOptions(BaseModel):
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatRequest(BaseModel):
    conversation_id: str = ""
    message: str
    stream: bool = True
    options: Optional[ChatOptions] = None


class ChatEvent(BaseModel):
    type: str  # content | tool_call | tool_result | thinking | error | done
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Optional[str] = None
    code: Optional[int] = None
    message: Optional[str] = None
    usage: Optional[dict] = None


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionVO(BaseModel):
    content: str
    usage: UsageInfo = UsageInfo()
    tool_calls: list[dict] = []
