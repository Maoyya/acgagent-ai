from fastapi import APIRouter

from app.models.tool import ToolCreateRequest
from app.models.common import Result
from app.services.tool_service import tool_service

router = APIRouter(tags=["tool"])


@router.get("/tools")
async def list_tools():
    return Result.success(data=tool_service.list_all())


@router.get("/tools/{tool_id}")
async def get_tool(tool_id: str):
    tool = tool_service.get(tool_id)
    if tool is None:
        return Result.error(code=404, message=f"Tool not found: {tool_id}")
    return Result.success(data=tool)


@router.post("/tools")
async def create_tool(body: ToolCreateRequest):
    tool = tool_service.create(body)
    return Result.success(data=tool)


@router.delete("/tools/{tool_id}")
async def delete_tool(tool_id: str):
    ok = tool_service.delete(tool_id)
    if not ok:
        return Result.error(code=404, message=f"Tool not found or builtin tool cannot be deleted: {tool_id}")
    return Result.success()
