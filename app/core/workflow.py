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


class WorkflowState(TypedDict):
    messages: list[BaseMessage]
    original_query: str
    context: str
    tool_calls: list[dict]
    final_response: str


class AgentWorkflow:
    def __init__(self, agent_config: AgentConfig, memory: ConversationMemory, conversation_id: str):
        self.agent_config = agent_config
        self.memory = memory
        self.conversation_id = conversation_id
        self.llm = create_chat_model(agent_config.llm_config)

    def build_graph(self) -> StateGraph:
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
        history = self.memory.load_messages(self.conversation_id)
        state["messages"] = history
        return state

    def _rag_retrieve(self, state: WorkflowState) -> WorkflowState:
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
        return state

    async def stream_workflow(self, query: str) -> AsyncGenerator[str, None]:
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

            self.memory.save_assistant_message(self.conversation_id, full_content)
            done_event = ChatEvent(type="done", usage=UsageInfo().model_dump())
            yield f"data: {done_event.model_dump_json(exclude_none=True)}\n\n"

        except Exception as e:
            logger.error("Workflow streaming error: %s", e)
            error_event = ChatEvent(type="error", code=500, message=str(e))
            yield f"data: {error_event.model_dump_json(exclude_none=True)}\n\n"
