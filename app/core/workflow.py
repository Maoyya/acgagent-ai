"""
LangGraph 工作流引擎。

当 Agent 的 capabilities 包含 "workflow" 时，对话走此路径。
工作流编排：加载记忆 → (可选) RAG 检索 → 流式生成。
相比 ChatService 的直接调用，工作流模式支持更复杂的节点编排和多步推理。
"""
import logging
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from app.core.llm import create_chat_model
from app.core.memory import ConversationMemory
from app.core.retriever import RAGRetriever
from app.models.agent import AgentConfig

logger = logging.getLogger("acgagent-ai")


# 工作流节点间传递的状态，每个 node 接收并返回此结构
class WorkflowState(TypedDict):
    messages: list[BaseMessage]    # 从记忆加载的历史消息
    original_query: str            # 用户原始问题
    context: str                   # RAG 检索到的上下文（无 RAG 时为空）
    tool_calls: list[dict]         # 预留：工具调用记录
    final_response: str            # 预留：最终响应


class AgentWorkflow:
    def __init__(self, agent_config: AgentConfig, memory: ConversationMemory, conversation_id: str):
        self.agent_config = agent_config
        self.memory = memory
        self.conversation_id = conversation_id
        self.llm = create_chat_model(agent_config.llm_config)

    def build_graph(self) -> StateGraph:
        """根据 Agent 能力动态构建工作流图。

        固定节点：load_memory → generate
        条件节点：如 Agent 启用 rag 且关联了知识库，中间插入 retrieve 节点。
        """
        graph = StateGraph(WorkflowState)

        graph.add_node("load_memory", self._load_memory)

        if "rag" in self.agent_config.capabilities and self.agent_config.knowledge_base_ids:
            graph.add_node("retrieve", self._rag_retrieve)
            graph.add_edge("load_memory", "retrieve")
            graph.add_edge("retrieve", "generate")
        else:
            graph.add_edge("load_memory", "generate")

        graph.add_node("generate", self._generate)
        graph.set_entry_point("load_memory")
        graph.add_edge("generate", END)

        return graph.compile()

    def _load_memory(self, state: WorkflowState) -> WorkflowState:
        """从 ChromaDB 加载当前会话的历史消息，受 token 预算裁剪。"""
        history = self.memory.load_messages(self.conversation_id)
        state["messages"] = history
        return state

    def _rag_retrieve(self, state: WorkflowState) -> WorkflowState:
        """从关联知识库中检索与用户问题最相关的文档片段。

        使用第一个知识库的 EmbeddingConfig 构建检索器，
        跨所有关联知识库 collection 查询。检索失败时降级为空上下文，不中断流程。
        """
        try:
            from app.db.knowledge_store import knowledge_store
            kb = None
            if self.agent_config.knowledge_base_ids:
                kb = knowledge_store.get(self.agent_config.knowledge_base_ids[0])

            if kb:
                retriever = RAGRetriever(kb.embedding_config)
                chunks = retriever.retrieve(state["original_query"], self.agent_config.knowledge_base_ids)
                state["context"] = RAGRetriever.build_rag_context(chunks)
            else:
                state["context"] = ""
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)
            state["context"] = ""
        return state

    def _generate(self, state: WorkflowState) -> WorkflowState:
        """预留节点。当前图执行到此仅透传状态，实际 LLM 调用在 stream_workflow 中完成。"""
        return state

    async def stream_workflow(self, query: str) -> AsyncGenerator[str, None]:
        """执行完整工作流并通过 SSE 流式返回 LLM 生成内容。

        流程：
        1. 构建并执行 LangGraph（加载记忆 + 可选 RAG 检索）
        2. 拼装完整消息列表：system_prompt → RAG 上下文 → 历史消息 → 当前问题
        3. 流式调用 LLM，逐块通过 SSE 推送 content 事件
        4. 完成后保存助手回复到记忆，发送 done 事件
        """
        from app.models.chat import ChatEvent, UsageInfo

        graph = self.build_graph()

        initial_state: WorkflowState = {
            "messages": [],
            "original_query": query,
            "context": "",
            "tool_calls": [],
            "final_response": "",
        }

        result = await graph.ainvoke(initial_state)

        # 按优先级拼装消息：系统提示 → RAG 上下文 → 历史 → 当前问题
        messages = []
        if self.agent_config.system_prompt:
            messages.append(SystemMessage(content=self.agent_config.system_prompt))

        if result.get("context"):
            rag_prefix = f"基于以下参考资料回答用户问题。如果资料中没有相关信息，请说明。\n\n参考资料：\n{result['context']}\n\n"
            messages.append(SystemMessage(content=rag_prefix))

        messages.extend(result["messages"])
        messages.append(HumanMessage(content=query))

        full_content = ""
        try:
            async for chunk in self.llm.astream(messages):
                if chunk.content:
                    full_content += chunk.content
                    event = ChatEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

            # 流结束后保存完整回复，供下次对话加载
            self.memory.save_assistant_message(self.conversation_id, full_content)
            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"

        except Exception as e:
            logger.error("Workflow streaming error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"
