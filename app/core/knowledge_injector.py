"""
结构化条目自动注入器。

把 Agent 的 active_entry_ids 对应条目渲染成【参考设定】块拼到 system_prompt 后。
注入挂载点：chat_service._build_messages 与 workflow.stream_workflow（两处共用）。
- 无激活条目 → 返回原 system_prompt（零回归）
- 激活条目已删 → 跳过 + log warning，不中断
- 仅渲染 details 中非空字段（省 token）
"""
import logging

from app.db.knowledge_entry_store import knowledge_entry_store

logger = logging.getLogger("acgagent-ai")

# 各 type 渲染时从 details 取的字段（key, 展示标签），顺序即展示顺序。
# 注意：series 由 _render_entry 的 extra 括注（如"初音(Vocaloid)"）单独展示，
# 不再进 character 的字段列表，避免重复渲染。
_FIELD_LABELS = {
    "style": [("visual_elements", "视觉"), ("tone", "调性")],
    "character": [("appearance", "外貌"),
                  ("personality", "性格"), ("speech_style", "口吻")],
    "story": [("setting", "世界观"), ("plot_points", "情节"), ("tone", "基调")],
}
_TYPE_LABEL = {"style": "风格", "character": "角色", "story": "故事"}


def _render_entry(entry) -> str:
    type_key = entry.type.value if hasattr(entry.type, "value") else str(entry.type)
    extra = f"({entry.details['series']})" if entry.details.get("series") else ""
    parts = [f"[{_TYPE_LABEL.get(type_key, type_key)}] {entry.name}{extra}：{entry.summary}"]
    for key, label in _FIELD_LABELS.get(type_key, []):
        val = entry.details.get(key)
        if not val:
            continue
        if isinstance(val, list):
            val = "/".join(str(v) for v in val)
        parts.append(f"{label}:{val}")
    return " | ".join(parts)


def build_system_content(agent_config) -> str:
    """构建最终 system 内容 = system_prompt + 【参考设定】块；均无则返回 ''。"""
    base = agent_config.system_prompt or ""
    active_ids = getattr(agent_config, "active_entry_ids", None) or []
    if not active_ids:
        return base
    lines = []
    for eid in active_ids:
        entry = knowledge_entry_store.get(eid)
        if entry is None:
            logger.warning("active_entry_id not found, skipped: %s", eid)
            continue
        lines.append(_render_entry(entry))
    if not lines:
        return base
    block = "【参考设定】\n" + "\n".join(lines)
    return f"{base}\n\n{block}" if base else block
