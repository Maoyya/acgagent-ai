"""
文档 JSON 文件存储。

按知识库分目录存储：data/documents/{kb_id}/{doc_id}.json。
"""
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.document import DocumentVO


class DocumentStore:
    """文档的 JSON 文件存储（按知识库分目录，持久化到 data/documents/{kb_id}/）。"""

    def __init__(self):
        self._dir: Path = settings.data_dir / "documents"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _kb_dir(self, kb_id: str) -> Path:
        """返回（并按需创建）某知识库的文档目录。"""
        d = self._dir / kb_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_by_kb(self, kb_id: str) -> list[DocumentVO]:
        """列出某知识库下全部文档；损坏的 JSON 静默跳过，不中断列举。"""
        kb_dir = self._kb_dir(kb_id)
        result = []
        for f in sorted(kb_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(DocumentVO(**data))
            except Exception:
                pass
        return result

    def get(self, kb_id: str, doc_id: str) -> Optional[DocumentVO]:
        """按「知识库 ID + 文档 ID」读取单个文档；不存在返回 None。"""
        path = self._kb_dir(kb_id) / f"{doc_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return DocumentVO(**data)

    def save(self, doc: DocumentVO) -> DocumentVO:
        """将文档写入 {kb_id}/{doc_id}.json（覆盖写）。"""
        path = self._kb_dir(doc.knowledge_base_id) / f"{doc.id}.json"
        path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        return doc

    def delete(self, kb_id: str, doc_id: str) -> bool:
        """删除文档；文件不存在返回 False。"""
        path = self._kb_dir(kb_id) / f"{doc_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False


document_store = DocumentStore()
