"""
对话记忆管理。

负责对话历史的读写和 token 预算裁剪。
记忆存储在 ChromaDB 中，按 conversation_id 隔离。
支持三种模式：conversation_window（滑动窗口）、summary（预留）、none（无记忆）。
"""
import tiktoken
import logging

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.db.memory_store import memory_store
from app.models.agent import MemoryConfig

logger = logging.getLogger("acgagent-ai")


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """计算文本的 token 数量。未知模型回退到 cl100k_base 编码（GPT-4 系列）。"""
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


class ConversationMemory:
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.max_tokens = config.max_tokens

    def load_messages(self, conversation_id: str) -> list[BaseMessage]:
        """加载会话历史并按 token 预算裁剪。

        从 ChromaDB 读取原始消息，转换为 LangChain Message 对象，
        然后从最新消息向前累加 token，超出预算的早期消息被丢弃。
        """
        if self.config.type == "none" or not conversation_id:
            return []

        raw_messages = memory_store.load_history(conversation_id)
        lc_messages = []
        for msg in raw_messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))

        return self._trim_to_budget(lc_messages)

    def save_user_message(self, conversation_id: str, content: str):
        """保存用户消息到对话记忆。同时记录 token 数供后续裁剪参考。"""
        if not conversation_id or self.config.type == "none":
            return
        tokens = count_tokens(content)
        memory_store.save_message(conversation_id, "user", content, token_count=tokens)

    def save_assistant_message(self, conversation_id: str, content: str):
        """保存助手回复到对话记忆。"""
        if not conversation_id or self.config.type == "none":
            return
        tokens = count_tokens(content)
        memory_store.save_message(conversation_id, "assistant", content, token_count=tokens)

    def _trim_to_budget(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """滑动窗口裁剪：保留最新的消息直到总 token 数不超过预算。

        从消息列表末尾（最新）向前遍历，累加 token 数，
        一旦超过 max_tokens 就停止，只保留窗口内的消息。
        这保证了最近上下文的完整性，早期对话自然丢弃。
        """
        if not messages:
            return []

        total = 0
        kept = []
        for msg in reversed(messages):
            msg_tokens = count_tokens(msg.content)
            if total + msg_tokens > self.max_tokens:
                break
            total += msg_tokens
            kept.insert(0, msg)
        return kept
