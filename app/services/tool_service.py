"""
工具管理服务。

工具分为两类：
- builtin: 内置工具（calculator/web_search/knowledge_search），硬编码，不可删除
- api: 用户自定义 API 工具，通过接口注册，持久化到 JSON 文件

列表查询时合并返回内置工具和自定义工具。
"""
import uuid
from datetime import datetime
from typing import Optional

from app.db.tool_store import tool_store
from app.models.tool import ToolVO, ToolCreateRequest, ToolParameterSchema


class ToolService:
    def __init__(self):
        # 内置工具 ID 集合，这些工具不可删除
        self._builtin_ids = {"calculator", "web_search", "knowledge_search"}

    def list_all(self) -> list[ToolVO]:
        """返回所有工具（内置 + 用户自定义），内置工具排在前面。"""
        stored = tool_store.list_all()
        builtins = self._get_builtins()
        return builtins + stored

    def get(self, tool_id: str) -> Optional[ToolVO]:
        """获取工具详情。内置工具从内存获取，自定义工具从存储获取。"""
        if tool_id in self._builtin_ids:
            return self._get_builtins_map().get(tool_id)
        return tool_store.get(tool_id)

    def create(self, req: ToolCreateRequest) -> ToolVO:
        """创建自定义 API 工具。"""
        tool = ToolVO(
            id=uuid.uuid4().hex[:12],
            name=req.name,
            description=req.description,
            type=req.type,
            config=req.config,
            parameters=req.parameters,
            created_at=datetime.now(),
        )
        return tool_store.save(tool)

    def delete(self, tool_id: str) -> bool:
        """删除工具。内置工具（calculator/web_search/knowledge_search）不可删除。"""
        if tool_id in self._builtin_ids:
            return False
        return tool_store.delete(tool_id)

    def _get_builtins(self) -> list[ToolVO]:
        return [
            ToolVO(id="calculator", name="计算器", description="计算数学表达式", type="builtin",
                   parameters=ToolParameterSchema(properties={"expression": {"type": "string", "description": "数学表达式"}}, required=["expression"])),
            ToolVO(id="web_search", name="网络搜索", description="搜索互联网获取实时信息", type="builtin",
                   parameters=ToolParameterSchema(properties={"query": {"type": "string", "description": "搜索关键词"}}, required=["query"])),
            ToolVO(id="knowledge_search", name="知识库搜索", description="在知识库中检索信息", type="builtin",
                   parameters=ToolParameterSchema(properties={"query": {"type": "string", "description": "搜索问题"}}, required=["query"])),
        ]

    def _get_builtins_map(self) -> dict[str, ToolVO]:
        return {t.id: t for t in self._get_builtins()}


tool_service = ToolService()
