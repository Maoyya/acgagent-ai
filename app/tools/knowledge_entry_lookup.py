"""
结构化条目按需检索工具。

仅检索公共库（scope=public）；私有条目经 Agent.active_entry_ids 自动注入触达（spec §4.3 v1 边界）。
作为 Tool 被 LLM 自主调用；无构造参数（chat_service._get_tools 走 else 分支实例化）。
"""
import logging
from app.tools.base import BaseAgentTool
from app.db.chroma_client import get_chroma

logger = logging.getLogger("acgagent-ai")

_COLLECTION = "kb_structured_entries"
_TYPE_LABEL = {"style": "风格", "character": "角色", "story": "故事"}


class KnowledgeEntryLookupTool(BaseAgentTool):
    def __init__(self):
        super().__init__(
            tool_id="knowledge_entry_lookup",
            name="knowledge_entry_lookup",
            description="在公共设定库中搜索风格/角色/故事等参考设定。"
                        "输入 query 关键词（可选 entry_type: style/character/story），返回最相关条目。",
        )

    def execute(self, query: str = "", entry_type: str = "", **kwargs) -> str:
        query = query or kwargs.get("question", "")
        if not query:
            return "请提供搜索关键词"
        where = {"scope": "public"}
        if entry_type:
            where["type"] = entry_type
        try:
            col = get_chroma().get_collection(name=_COLLECTION)
            res = col.query(query_texts=[query], n_results=3, where=where)
        except Exception as e:
            logger.warning("knowledge_entry_lookup failed: %s", e)
            return "未找到相关信息"
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        if not docs:
            return "未找到相关信息"
        lines = []
        for doc, meta in zip(docs, metas):
            t = _TYPE_LABEL.get(meta.get("type", ""), meta.get("type", ""))
            lines.append(f"[{t}] {doc}")
        return "\n\n---\n\n".join(lines)
