from fastapi import APIRouter

from app.models.agent import AgentCreateRequest, AgentUpdateRequest
from app.models.common import Result
from app.services.agent_service import agent_service

router = APIRouter(tags=["agent"])


@router.get("/agents")
async def list_agents():
    agents = agent_service.list_all()
    return Result.success(data=agents)


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = agent_service.get(agent_id)
    if agent is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success(data=agent)


@router.post("/agents")
async def create_agent(body: AgentCreateRequest):
    agent = agent_service.create(body)
    return Result.success(data=agent)


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdateRequest):
    agent = agent_service.update(agent_id, body)
    if agent is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success(data=agent)


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    ok = agent_service.delete(agent_id)
    if not ok:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success()
