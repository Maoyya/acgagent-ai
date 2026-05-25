from app.tools.base import BaseAgentTool


class WebSearchTool(BaseAgentTool):
    def __init__(self):
        super().__init__(
            tool_id="web_search",
            name="web_search",
            description="搜索互联网获取实时信息。输入搜索关键词，返回搜索结果摘要。",
        )

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", kwargs.get("keywords", ""))
        return f"[v1.0 搜索功能暂未实现] 搜索关键词: {query}"
