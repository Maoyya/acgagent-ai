"""
Agent 管理 CRUD 服务。

Agent 是系统的核心实体，定义了 AI 助手的模型配置、记忆策略、能力标签和关联资源。
存储在 JSON 文件中（data/agents/{id}.json）。
"""
import uuid
from datetime import datetime
from typing import Optional

from app.db.agent_store import agent_store
from app.db.knowledge_store import knowledge_store
from app.db.tool_store import tool_store
from app.models.agent import AgentConfig, AgentCreateRequest, AgentUpdateRequest
from app.tools import BUILTIN_TOOL_IDS


class AgentService:
    def list_all(self) -> list[AgentConfig]:
        """列出所有已创建的 Agent。"""
        return agent_store.list_all()

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """按 ID 获取 Agent 配置，不存在返回 None。"""
        return agent_store.get(agent_id)

    def _validate_references(self, kb_ids: list[str], tool_ids: list[str]) -> None:
        """校验 KB / tool 引用存在。通过 return；缺失 raise ValueError（列出缺失 ID）。

        - KB：每个 id 必须 knowledge_store.get(id) 存在。
        - Tool：合法 ⟺ 在 BUILTIN_TOOL_IDS 中 或 tool_store.get(id) 存在（内置工具不入库）。
        """
        missing_kb = [kb for kb in kb_ids if knowledge_store.get(kb) is None]
        missing_tool = [
            tid for tid in tool_ids
            if tid not in BUILTIN_TOOL_IDS and tool_store.get(tid) is None
        ]
        if missing_kb or missing_tool:
            raise ValueError(
                f"引用资源不存在: knowledge_base_ids={missing_kb}, tool_ids={missing_tool}"
            )

    def create(self, req: AgentCreateRequest) -> AgentConfig:
        """创建 Agent。自动生成 12 位 hex ID，默认启用（status=1）。"""
        agent = AgentConfig(
            id=uuid.uuid4().hex[:12],
            name=req.name,
            description=req.description,
            system_prompt=req.system_prompt,
            llm_config=req.llm_config,
            memory_config=req.memory_config,
            capabilities=req.capabilities,
            knowledge_base_ids=req.knowledge_base_ids,
            tool_ids=req.tool_ids,
            status=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return agent_store.save(agent)

    def update(self, agent_id: str, req: AgentUpdateRequest) -> Optional[AgentConfig]:
        """部分更新 Agent。只修改请求中显式传入的字段（exclude_unset=True）。"""
        agent = agent_store.get(agent_id)
        if agent is None:
            return None

        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(agent, field, value)
        agent.updated_at = datetime.now()
        return agent_store.save(agent)

    def delete(self, agent_id: str) -> bool:
        return agent_store.delete(agent_id)


agent_service = AgentService()
