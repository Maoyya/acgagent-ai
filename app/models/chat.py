"""
对话请求/响应模型。

ChatRequest: 对话请求，支持流式/同步模式
ChatEvent: SSE 事件，类型包括 content/tool_call/tool_result/thinking/error/done
"""
from typing import Optional
from pydantic import BaseModel


class ChatOptions(BaseModel):
    """对话生成参数（均可选，缺省走 Agent 的 LLM 配置）。"""

    temperature: Optional[float] = None  # 采样温度
    max_tokens: Optional[int] = None  # 最大输出 token


class ChatRequest(BaseModel):
    """对话请求。stream=True 走 SSE，False 走一次性同步返回。"""

    conversation_id: str = ""  # 空串则开新会话
    message: str
    images: list[str] = []  # 图生文：图片 URL 列表，可空
    stream: bool = True  # 是否流式
    options: Optional[ChatOptions] = None  # 生成参数覆盖


class ChatEvent(BaseModel):
    """SSE 事件。type 决定携带哪些字段（见各字段注释）。"""

    type: str  # content | tool_call | tool_result | thinking | error | done
    content: Optional[str] = None  # type=content：文本片段
    tool_name: Optional[str] = None  # type=tool_call：工具名
    tool_input: Optional[dict] = None  # type=tool_call：工具入参
    tool_output: Optional[str] = None  # type=tool_result：工具返回
    code: Optional[int] = None  # type=error：错误码
    message: Optional[str] = None  # type=error：错误描述
    usage: Optional[dict] = None  # type=done：token 用量


class UsageInfo(BaseModel):
    """单次对话的 token 用量统计。"""

    prompt_tokens: int = 0  # 输入
    completion_tokens: int = 0  # 输出
    total_tokens: int = 0  # 合计


class ChatCompletionVO(BaseModel):
    """同步对话响应（非流式）。"""

    content: str  # 完整回复
    usage: UsageInfo = UsageInfo()  # token 用量
    tool_calls: list[dict] = []  # 本轮触发的工具调用
