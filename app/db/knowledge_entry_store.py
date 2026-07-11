"""
结构化知识条目 JSON 文件存储。

每个条目保存为 data/knowledge_entries/{id}.json。
_dir() 每次按需读取 settings.data_dir（lazy），便于测试 monkeypatch。
"""
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.knowledge_entry import KnowledgeEntry


class KnowledgeEntryStore:
    def _dir(self) -> Path:
        d = settings.data_dir / "knowledge_entries"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, entry_id: str) -> Path:
        # 纵深防御：剥掉任何目录/`..` 组件，仅保留纯文件名，确保落在本目录内。
        # 主防御在 service 层 entry_id 格式校验。
        return self._dir() / f"{Path(entry_id).name}.json"

    def list_all(self) -> list[KnowledgeEntry]:
        result = []
        for f in sorted(self._dir().glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(KnowledgeEntry(**data))
            except Exception:
                pass
        return result

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        path = self._path(entry_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return KnowledgeEntry(**data)
        except Exception:
            # 损坏/截断的 JSON 视为不存在（与 list_all 一致），避免未捕获异常 → API 500 / 聊天崩溃。
            return None

    def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        path = self._path(entry.id)
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        return entry

    def delete(self, entry_id: str) -> bool:
        path = self._path(entry_id)
        if path.exists():
            path.unlink()
            return True
        return False


knowledge_entry_store = KnowledgeEntryStore()
