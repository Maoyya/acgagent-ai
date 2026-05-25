from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: Optional[T] = None

    @staticmethod
    def success(data: T = None) -> "Result[T]":
        return Result(code=200, message="success", data=data)

    @staticmethod
    def error(code: int = 500, message: str = "error") -> "Result":
        return Result(code=code, message=message, data=None)
