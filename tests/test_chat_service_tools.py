"""chat_service 工具实例化与内置工具常量测试。

锁定意图（Rule 9）：
- BUILTIN_TOOL_IDS 是「合法内置 tool_id」的单一真相源（校验逻辑将共用它）。
- _get_tools 改用映射后，内置工具实例化行为与旧版 switch 完全一致。
"""
from app.tools import BUILTIN_TOOL_IDS, BUILTIN_TOOLS
from app.models.agent import AgentConfig, LLMConfig
from app.services.chat_service import chat_service


def _agent(tool_ids):
    return AgentConfig(
        name="t",
        llm_config=LLMConfig(provider="x", model="m", base_url="http://x", api_key="k"),
        tool_ids=tool_ids,
    )


def test_builtin_tool_ids_matches_builtin_tools():
    """BUILTIN_TOOL_IDS 是「合法内置 tool_id」单一真相源，等于 BUILTIN_TOOLS 的键集合。"""
    assert BUILTIN_TOOL_IDS == {"calculator", "web_search", "knowledge_search", "knowledge_entry_lookup", "image_generation", "video_generation"}
    assert set(BUILTIN_TOOLS.keys()) == BUILTIN_TOOL_IDS


def test_get_tools_instantiates_each_builtin_once():
    """calculator / web_search 各实例化一次；未关联 KB 时 knowledge_search 被跳过。"""
    tools = chat_service._get_tools(_agent(["calculator", "web_search", "knowledge_search"]))
    assert len(tools) == 2  # knowledge_search 无 KB → 跳过（沿用旧行为）


def test_get_tools_knowledge_search_requires_kb():
    """knowledge_search 有关联 KB 时才实例化。"""
    agent = _agent(["knowledge_search"])
    agent.knowledge_base_ids = ["kb-1"]
    assert len(chat_service._get_tools(agent)) == 1
    assert len(chat_service._get_tools(_agent(["knowledge_search"]))) == 0


def test_get_tools_ignores_unknown_and_custom_ids():
    """非内置 ID（含自定义工具 ID）在 _get_tools 中被忽略 —— 沿用既有行为，本计划不改变它。"""
    assert len(chat_service._get_tools(_agent(["calculator", "unknown_custom"]))) == 1
