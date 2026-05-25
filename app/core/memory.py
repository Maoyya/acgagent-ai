import tiktoken
import logging

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.db.memory_store import memory_store
from app.models.agent import MemoryConfig

logger = logging.getLogger("acgagent-ai")


def count_tokens(text: str, model: str = "gpt-4") -> int:
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
        if not conversation_id or self.config.type == "none":
            return
        tokens = count_tokens(content)
        memory_store.save_message(conversation_id, "user", content, token_count=tokens)

    def save_assistant_message(self, conversation_id: str, content: str):
        if not conversation_id or self.config.type == "none":
            return
        tokens = count_tokens(content)
        memory_store.save_message(conversation_id, "assistant", content, token_count=tokens)

    def _trim_to_budget(self, messages: list[BaseMessage]) -> list[BaseMessage]:
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
