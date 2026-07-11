"""
自定义工具 JSON 文件存储。

每个工具配置保存为 data/tools/{id}.json。
仅存储用户自定义 API 工具，内置工具（calculator/web_search/knowledge_search）不经过此存储。
"""
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.tool import ToolVO


class ToolStore:
    """自定义工具配置的 JSON 文件存储（持久化到 data/tools/）。"""

    def __init__(self):
        self._dir: Path = settings.data_dir / "tools"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, tool_id: str) -> Path:
        """返回工具 JSON 文件路径。"""
        return self._dir / f"{tool_id}.json"

    def list_all(self) -> list[ToolVO]:
        """列出全部自定义工具；损坏的 JSON 静默跳过，不中断列举。"""
        result = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(ToolVO(**data))
            except Exception:
                pass
        return result

    def get(self, tool_id: str) -> Optional[ToolVO]:
        """按 ID 读取单个工具；文件不存在返回 None。"""
        path = self._path(tool_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ToolVO(**data)

    def save(self, tool: ToolVO) -> ToolVO:
        """将工具写入 {id}.json（覆盖写）。"""
        path = self._path(tool.id)
        path.write_text(tool.model_dump_json(indent=2), encoding="utf-8")
        return tool

    def delete(self, tool_id: str) -> bool:
        """删除工具文件；文件不存在返回 False。"""
        path = self._path(tool_id)
        if path.exists():
            path.unlink()
            return True
        return False


tool_store = ToolStore()
