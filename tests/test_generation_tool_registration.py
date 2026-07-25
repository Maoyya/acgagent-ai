"""生成工具注册完整性测试。"""
from app.services.tool_service import tool_service
from app.tools import BUILTIN_TOOLS


def test_builtin_tools_includes_generation():
    assert "image_generation" in BUILTIN_TOOLS
    assert "video_generation" in BUILTIN_TOOLS


def test_tool_service_lists_generation_and_entry_lookup():
    ids = {t.id for t in tool_service.list_all()}
    # 新增的两个生成工具 + 补齐的 knowledge_entry_lookup
    assert {"image_generation", "video_generation", "knowledge_entry_lookup"} <= ids


def test_generation_tool_has_required_params_schema():
    by_id = {t.id: t for t in tool_service.list_all()}
    assert set(by_id["image_generation"].parameters.required) == {"prompt"}
    assert set(by_id["video_generation"].parameters.required) == {"prompt", "image_url"}
