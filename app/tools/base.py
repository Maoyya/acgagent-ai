"""
工具基类。

所有 Agent 可调用的工具都继承 BaseAgentTool，实现 execute() 方法。
通过 to_langchain_tool() 转换为 LangChain Tool 格式，供 LLM bind_tools() 使用。
"""
from abc import ABC, abstractmethod
from langchain_core.tools import tool as lc_tool


class BaseAgentTool(ABC):
    def __init__(self, tool_id: str, name: str, description: str):
        self.id = tool_id
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """执行工具逻辑，返回字符串结果。"""
        ...

    def to_langchain_tool(self):
        """将此工具转换为 LangChain @tool 装饰器格式的函数，供 LLM 调用。"""
        @lc_tool(self.name)
        def _tool_func(**kwargs) -> str:
            return self.execute(**kwargs)
        _tool_func.description = self.description
        return _tool_func
