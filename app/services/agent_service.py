"""
Agent 管理 CRUD 服务。

Agent 是系统的核心实体，定义了 AI 助手的模型配置、记忆策略、能力标签和关联资源。
存储在 JSON 文件中（data/agents/{id}.json）。
"""
import uuid
from datetime import datetime
from typing import Optional

from app.db.agent_store import agent_store
from app.models.agent import AgentConfig, AgentCreateRequest, AgentUpdateRequest


class AgentService:
    def list_all(self) -> list[AgentConfig]:
        """列出所有已创建的 Agent。"""
        return agent_store.list_all()

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """按 ID 获取 Agent 配置，不存在返回 None。"""
        return agent_store.get(agent_id)

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
