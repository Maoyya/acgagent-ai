import logging
from app.tools.base import BaseAgentTool
from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")


class KnowledgeSearchTool(BaseAgentTool):
    def __init__(self, knowledge_base_ids: list[str]):
        super().__init__(
            tool_id="knowledge_search",
            name="knowledge_search",
            description="在知识库中搜索相关信息。输入搜索查询，返回最相关的文档片段。",
        )
        self.knowledge_base_ids = knowledge_base_ids

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", kwargs.get("question", ""))
        if not query:
            return "请提供搜索查询"

        results = []
        chroma = get_chroma()
        for kb_id in self.knowledge_base_ids:
            col_name = f"kb_{kb_id}_chunks"
            try:
                col = chroma.get_collection(name=col_name)
                query_result = col.query(query_texts=[query], n_results=3)
                for doc in query_result["documents"][0]:
                    results.append(doc)
            except Exception as e:
                logger.warning("KB search failed for %s: %s", col_name, e)

        if not results:
            return "未找到相关信息"
        return "\n\n---\n\n".join(results)
