import logging
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import create_chat_model
from app.core.memory import ConversationMemory
from app.models.agent import AgentConfig
from app.models.chat import ChatEvent, ChatCompletionVO, UsageInfo

logger = logging.getLogger("acgagent-ai")


class ChatService:
    def _build_memory(self, agent_config: AgentConfig) -> ConversationMemory:
        return ConversationMemory(agent_config.memory_config)

    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        if "workflow" in agent_config.capabilities:
            from app.core.workflow import AgentWorkflow
            workflow = AgentWorkflow(agent_config, memory, conversation_id)
            async for event in workflow.stream_workflow(message):
                yield event
            return

        llm = create_chat_model(agent_config.llm_config)

        if self._has_tools(agent_config):
            async for event in self._stream_with_tools(llm, agent_config, message, memory, conversation_id):
                yield event
        else:
            async for event in self._stream_plain(llm, agent_config, message, memory, conversation_id):
                yield event

    async def _stream_plain(self, llm, agent_config, message, memory, conversation_id):
        messages = self._build_messages(agent_config, memory, message, conversation_id)
        full_content = ""
        try:
            async for chunk in llm.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"
            memory.save_assistant_message(conversation_id, full_content)
            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"
        except Exception as e:
            logger.error("Chat streaming error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"

    async def _stream_with_tools(self, llm, agent_config, message, memory, conversation_id):
        tools = self._get_tools(agent_config)
        llm_with_tools = llm.bind_tools(tools)
        messages = self._build_messages(agent_config, memory, message, conversation_id)
        full_content = ""

        try:
            async for chunk in llm_with_tools.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

                if chunk.tool_call_chunks:
                    for tc in chunk.tool_call_chunks:
                        if tc.get("name"):
                            event = ChatEvent(type="tool_call", tool_name=tc["name"], tool_input=tc.get("args"))
                            yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

            memory.save_assistant_message(conversation_id, full_content)
            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"
        except Exception as e:
            logger.error("Tool chat error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"

    def _build_messages(self, agent_config, memory, message, conversation_id):
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))
        history = memory.load_messages(conversation_id)
        messages.extend(history)
        messages.append(HumanMessage(content=message))
        return messages

    async def sync_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
    ) -> ChatCompletionVO:
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        llm = create_chat_model(agent_config.llm_config)
        messages = self._build_messages(agent_config, memory, message, conversation_id)

        try:
            response = await llm.ainvoke(messages)
            content = response.content or ""
            memory.save_assistant_message(conversation_id, content)
            return ChatCompletionVO(content=content, usage=UsageInfo())
        except Exception as e:
            logger.error("Chat sync error: %s", e)
            raise

    def _get_tools(self, agent_config: AgentConfig) -> list:
        from app.tools.calculator import CalculatorTool
        from app.tools.web_search import WebSearchTool
        from app.tools.knowledge_search import KnowledgeSearchTool

        tools = []
        for tid in agent_config.tool_ids:
            if tid == "calculator":
                tools.append(CalculatorTool())
            elif tid == "web_search":
                tools.append(WebSearchTool())
            elif tid == "knowledge_search":
                if agent_config.knowledge_base_ids:
                    tools.append(KnowledgeSearchTool(agent_config.knowledge_base_ids))
        return [t.to_langchain_tool() for t in tools]

    def _has_tools(self, agent_config: AgentConfig) -> bool:
        return bool(agent_config.tool_ids) and "tool_use" in agent_config.capabilities


chat_service = ChatService()
