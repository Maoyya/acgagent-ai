"""
RAG 检索器。

从 ChromaDB 中检索与用户问题最相关的文档片段。
每个知识库对应一个 ChromaDB collection（kb_{id}_chunks），
检索时使用 Embedding 模型将 query 向量化后做相似度匹配。
"""
import logging
from langchain_openai import OpenAIEmbeddings
from app.db.chroma_client import get_chroma
from app.models.knowledge_base import EmbeddingConfig

logger = logging.getLogger("acgagent-ai")


class RAGRetriever:
    def __init__(self, embedding_config: EmbeddingConfig):
        # 使用知识库配置的 Embedding 模型（如 text-embedding-v3）
        # base_url/api_key 为空时依赖环境变量或 SDK 默认值
        self.embedding = OpenAIEmbeddings(
            model=embedding_config.model,
            base_url=embedding_config.base_url or "",
            api_key=embedding_config.api_key or "not-needed",
        )

    def retrieve(
        self,
        query: str,
        knowledge_base_ids: list[str],
        top_k: int = 5,
    ) -> list[str]:
        """跨多个知识库 collection 检索相关文档片段。

        对每个知识库独立查询，合并结果。单个知识库检索失败不阻塞其他库。
        """
        chroma = get_chroma()
        results = []

        for kb_id in knowledge_base_ids:
            col_name = f"kb_{kb_id}_chunks"
            try:
                col = chroma.get_collection(name=col_name)
                query_result = col.query(query_texts=[query], n_results=top_k)
                for doc in query_result["documents"][0]:
                    results.append(doc)
            except Exception as e:
                logger.warning("RAG retrieve failed for %s: %s", col_name, e)

        return results

    @staticmethod
    def build_rag_context(chunks: list[str]) -> str:
        """将检索到的文档片段拼接为 LLM 可用的上下文字符串，用分隔线隔开。"""
        if not chunks:
            return ""
        return "\n\n---\n\n".join(chunks)
