"""
知识库 JSON 文件存储。

每个知识库元数据保存为 data/knowledge_bases/{id}.json。
"""
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.knowledge_base import KnowledgeBase


class KnowledgeStore:
    """知识库元数据的 JSON 文件存储（持久化到 data/knowledge_bases/）。"""

    def __init__(self):
        self._dir: Path = settings.data_dir / "knowledge_bases"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, kb_id: str) -> Path:
        """返回知识库 JSON 文件路径。"""
        return self._dir / f"{kb_id}.json"

    def list_all(self) -> list[KnowledgeBase]:
        """列出全部知识库；损坏的 JSON 静默跳过，不中断列举。"""
        result = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(KnowledgeBase(**data))
            except Exception:
                pass
        return result

    def get(self, kb_id: str) -> Optional[KnowledgeBase]:
        """按 ID 读取单个知识库；文件不存在返回 None。"""
        path = self._path(kb_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return KnowledgeBase(**data)

    def save(self, kb: KnowledgeBase) -> KnowledgeBase:
        """将知识库写入 {id}.json（覆盖写）。"""
        path = self._path(kb.id)
        path.write_text(kb.model_dump_json(indent=2), encoding="utf-8")
        return kb

    def delete(self, kb_id: str) -> bool:
        """删除知识库文件；文件不存在返回 False。"""
        path = self._path(kb_id)
        if path.exists():
            path.unlink()
            return True
        return False


knowledge_store = KnowledgeStore()
