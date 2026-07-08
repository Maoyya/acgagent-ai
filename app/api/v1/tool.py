"""工具 CRUD API 端点。"""
from fastapi import APIRouter

from app.models.tool import ToolCreateRequest
from app.models.common import Result
from app.services.tool_service import tool_service

router = APIRouter(tags=["tool"])


@router.get("/tools")
async def list_tools():
    """列出全部自定义工具。"""
    return Result.success(data=tool_service.list_all())


@router.get("/tools/{tool_id}")
async def get_tool(tool_id: str):
    """按 ID 获取工具；不存在返回 404。"""
    tool = tool_service.get(tool_id)
    if tool is None:
        return Result.error(code=404, message=f"Tool not found: {tool_id}")
    return Result.success(data=tool)


@router.post("/tools")
async def create_tool(body: ToolCreateRequest):
    """创建自定义工具。"""
    tool = tool_service.create(body)
    return Result.success(data=tool)


@router.delete("/tools/{tool_id}")
async def delete_tool(tool_id: str):
    """删除工具；不存在或为内置工具返回 404。"""
    ok = tool_service.delete(tool_id)
    if not ok:
        return Result.error(code=404, message=f"Tool not found or builtin tool cannot be deleted: {tool_id}")
    return Result.success()
