import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.tool import ToolVO


class ToolStore:
    def __init__(self):
        self._dir: Path = settings.data_dir / "tools"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, tool_id: str) -> Path:
        return self._dir / f"{tool_id}.json"

    def list_all(self) -> list[ToolVO]:
        result = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(ToolVO(**data))
            except Exception:
                pass
        return result

    def get(self, tool_id: str) -> Optional[ToolVO]:
        path = self._path(tool_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ToolVO(**data)

    def save(self, tool: ToolVO) -> ToolVO:
        path = self._path(tool.id)
        path.write_text(tool.model_dump_json(indent=2), encoding="utf-8")
        return tool

    def delete(self, tool_id: str) -> bool:
        path = self._path(tool_id)
        if path.exists():
            path.unlink()
            return True
        return False


tool_store = ToolStore()
