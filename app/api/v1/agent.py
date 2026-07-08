"""
Agent CRUD API 端点。
"""
from fastapi import APIRouter

from app.models.agent import AgentCreateRequest, AgentUpdateRequest
from app.models.common import Result
from app.services.agent_service import agent_service

router = APIRouter(tags=["agent"])


@router.get("/agents")
async def list_agents():
    """列出全部 Agent。"""
    agents = agent_service.list_all()
    return Result.success(data=agents)


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """按 ID 获取 Agent；不存在返回 404。"""
    agent = agent_service.get(agent_id)
    if agent is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success(data=agent)


@router.post("/agents")
async def create_agent(body: AgentCreateRequest, validate: bool = True):
    """创建 Agent；校验失败（如 LLM 密钥缺失）返回 400。"""
    try:
        agent = agent_service.create(body, validate=validate)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    return Result.success(data=agent)


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdateRequest, validate: bool = True):
    """更新 Agent；校验失败返回 400，不存在返回 404。"""
    try:
        agent = agent_service.update(agent_id, body, validate=validate)
    except ValueError as e:
        return Result.error(code=400, message=str(e))
    if agent is None:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success(data=agent)


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """删除 Agent；不存在返回 404。"""
    ok = agent_service.delete(agent_id)
    if not ok:
        return Result.error(code=404, message=f"Agent not found: {agent_id}")
    return Result.success()
