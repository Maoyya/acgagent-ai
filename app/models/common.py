"""
通用响应模型。

所有 API 统一使用 Result<T> 包装响应，包含 code/message/data 三字段。
"""
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """统一 API 响应封装：code / message / data 三段式。"""

    code: int = 200  # HTTP 风格状态码：200 成功，其余为错误
    message: str = "success"  # 人类可读的状态描述
    data: Optional[T] = None  # 业务数据载荷（泛型）

    @staticmethod
    def success(data: T = None) -> "Result[T]":
        """构造成功响应（code=200）。"""
        return Result(code=200, message="success", data=data)

    @staticmethod
    def error(code: int = 500, message: str = "error") -> "Result":
        """构造错误响应（默认 500）。"""
        return Result(code=code, message=message, data=None)
