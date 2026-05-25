import logging
from langchain_openai import OpenAIEmbeddings
from app.db.chroma_client import get_chroma
from app.models.knowledge_base import EmbeddingConfig

logger = logging.getLogger("acgagent-ai")


class RAGRetriever:
    def __init__(self, embedding_config: EmbeddingConfig):
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
        if not chunks:
            return ""
        return "\n\n---\n\n".join(chunks)
