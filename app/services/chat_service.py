"""
对话服务 — 系统核心。

根据 Agent 的 capabilities 配置路由到三种对话模式：
- workflow: LangGraph 工作流（支持 RAG + 多步编排）
- tool_use: LLM + 工具绑定（LLM 自主决定是否调用工具）
- chat: 纯 LLM 对话（无工具、无 RAG）

所有流式响应使用 SSE 协议（text/event-stream）。
"""
import logging
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import create_chat_model
from app.services import image_service
from app.core.memory import ConversationMemory
from app.models.agent import AgentConfig
from app.models.chat import ChatEvent, ChatCompletionVO, UsageInfo

logger = logging.getLogger("acgagent-ai")


class ChatService:
    def _build_memory(self, agent_config: AgentConfig) -> ConversationMemory:
        """根据 Agent 的 memory 配置创建记忆管理器。"""
        return ConversationMemory(agent_config.memory_config)

    async def stream_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
        images: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """对话入口。保存用户消息后根据能力路由到对应模式。"""
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        # 优先级：workflow > tool_use > 纯聊天
        # 注意：workflow/RAG 路径本轮不支持图（spec §7），images 不传入。
        if "workflow" in agent_config.capabilities:
            from app.core.workflow import AgentWorkflow
            workflow = AgentWorkflow(agent_config, memory, conversation_id)
            async for event in workflow.stream_workflow(message):
                yield event
            return

        llm = create_chat_model(agent_config.llm_config)

        if self._has_tools(agent_config):
            async for event in self._stream_with_tools(llm, agent_config, message, memory, conversation_id, images):
                yield event
        else:
            async for event in self._stream_plain(llm, agent_config, message, memory, conversation_id, images):
                yield event

    async def _stream_plain(self, llm, agent_config, message, memory, conversation_id, images=None):
        """纯聊天模式：直接流式调用 LLM，无工具绑定。"""
        messages = self._build_messages(agent_config, memory, message, conversation_id, images)
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

    async def _stream_with_tools(self, llm, agent_config, message, memory, conversation_id, images=None):
        """工具调用模式：将工具绑定到 LLM，LLM 在生成过程中可自主调用工具。

        SSE 输出两类事件：
        - content: LLM 生成的文本片段
        - tool_call: LLM 决定调用工具时的事件（含工具名和参数）
        """
        tools = self._get_tools(agent_config)
        llm_with_tools = llm.bind_tools(tools)
        messages = self._build_messages(agent_config, memory, message, conversation_id, images)
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

    def _build_messages(self, agent_config, memory, message, conversation_id, images=None):
        """构建发送给 LLM 的消息列表。

        顺序：system_prompt → 会话历史（经 token 裁剪） → 当前用户消息。
        当前用户消息的 content 由 image_service.build_message_content 组装：
        无图返回纯字符串（零回归），有图返回多模态 list（图生文）。
        """
        messages = []
        if agent_config.system_prompt:
            messages.append(SystemMessage(content=agent_config.system_prompt))
        history = memory.load_messages(conversation_id)
        messages.extend(history)
        messages.append(HumanMessage(content=image_service.build_message_content(message, images)))
        return messages

    async def sync_chat(
        self,
        agent_config: AgentConfig,
        message: str,
        conversation_id: str = "",
        user_id: str | None = None,
        images: list[str] | None = None,
    ) -> ChatCompletionVO:
        """同步对话模式。等待 LLM 完整响应后一次性返回，不使用流式。"""
        memory = self._build_memory(agent_config)
        memory.save_user_message(conversation_id, message)

        llm = create_chat_model(agent_config.llm_config)
        messages = self._build_messages(agent_config, memory, message, conversation_id, images)

        try:
            response = await llm.ainvoke(messages)
            content = response.content or ""
            memory.save_assistant_message(conversation_id, content)
            return ChatCompletionVO(content=content, usage=UsageInfo())
        except Exception as e:
            logger.error("Chat sync error: %s", e)
            raise

    def _get_tools(self, agent_config: AgentConfig) -> list:
        """根据 Agent 的 tool_ids 实例化对应工具并转换为 LangChain Tool 格式。

        内置工具按 BUILTIN_TOOLS 映射实例化（id→类单一真相源，去重 Rule 7）；
        自定义工具 ID 不在此处理 —— chat_service 当前不消费 tool_store，
        仅由 agent 可用性校验保证其存在性。
        knowledge_search 需关联知识库，未关联时跳过。
        """
        from app.tools import BUILTIN_TOOLS

        tools = []
        for tid in agent_config.tool_ids:
            cls = BUILTIN_TOOLS.get(tid)
            if cls is None:
                continue
            if tid == "knowledge_search":
                if agent_config.knowledge_base_ids:
                    tools.append(cls(agent_config.knowledge_base_ids))
            else:
                tools.append(cls())
        return [t.to_langchain_tool() for t in tools]

    def _has_tools(self, agent_config: AgentConfig) -> bool:
        """判断是否启用工具调用：需同时满足有工具 ID 且 capabilities 含 tool_use。"""
        return bool(agent_config.tool_ids) and "tool_use" in agent_config.capabilities


chat_service = ChatService()
