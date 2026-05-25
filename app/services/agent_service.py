import uuid
from datetime import datetime
from typing import Optional

from app.db.agent_store import agent_store
from app.models.agent import AgentConfig, AgentCreateRequest, AgentUpdateRequest


class AgentService:
    def list_all(self) -> list[AgentConfig]:
        return agent_store.list_all()

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        return agent_store.get(agent_id)

    def create(self, req: AgentCreateRequest) -> AgentConfig:
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
