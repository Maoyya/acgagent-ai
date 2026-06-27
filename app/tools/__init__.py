"""内置工具注册中心。

集中定义「内置工具 id → 实现类」的映射，作为单一真相源：
- chat_service._get_tools 据此实例化内置工具；
- agent 可用性校验据此判断「合法 tool_id」（自定义工具另查 tool_store）。

注意：自定义（用户 API）工具不在此映射，存于 app/db/tool_store.py。
"""
from app.tools.calculator import CalculatorTool
from app.tools.knowledge_search import KnowledgeSearchTool
from app.tools.web_search import WebSearchTool

# 内置工具 id → 实现类
BUILTIN_TOOLS = {
    "calculator": CalculatorTool,
    "web_search": WebSearchTool,
    "knowledge_search": KnowledgeSearchTool,
}

# 内置工具 id 集合（供引用完整性校验消费）
BUILTIN_TOOL_IDS = set(BUILTIN_TOOLS.keys())
