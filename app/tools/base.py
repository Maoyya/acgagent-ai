from abc import ABC, abstractmethod
from langchain_core.tools import tool as lc_tool


class BaseAgentTool(ABC):
    def __init__(self, tool_id: str, name: str, description: str):
        self.id = tool_id
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, **kwargs) -> str:
        ...

    def to_langchain_tool(self):
        @lc_tool(self.name)
        def _tool_func(**kwargs) -> str:
            return self.execute(**kwargs)
        _tool_func.description = self.description
        return _tool_func
