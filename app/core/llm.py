from langchain_openai import ChatOpenAI
from app.models.agent import LLMConfig


def create_chat_model(config: LLMConfig) -> ChatOpenAI:
    return ChatOpenAI(
        model=config.model,
        base_url=config.base_url,
        api_key=config.api_key,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        streaming=True,
    )
