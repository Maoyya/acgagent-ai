import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.agent_service import agent_service
from app.models.agent import AgentCreateRequest, LLMConfig


def main():
    agent = agent_service.create(AgentCreateRequest(
        name="通用助手",
        description="基于 DeepSeek 的通用对话助手",
        system_prompt="你是一个友善且专业的 AI 助手。请用中文回答问题。",
        llm_config=LLMConfig(
            provider="deepseek",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            # api_key 不再配置：运行时按 provider 从 ACG_AI_LLM_KEY_DEEPSEEK 取（见 app/core/llm.py）
            temperature=0.7,
            max_tokens=4096,
            top_p=0.9,
        ),
        capabilities=["chat", "rag", "tool_use", "workflow"],
    ))
    print(f"Sample agent created: {agent.id} - {agent.name}")


if __name__ == "__main__":
    main()
