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
    def __init__(self):
        self._dir: Path = settings.data_dir / "documents"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _kb_dir(self, kb_id: str) -> Path:
        d = self._dir / kb_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_by_kb(self, kb_id: str) -> list[DocumentVO]:
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
        path = self._kb_dir(kb_id) / f"{doc_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return DocumentVO(**data)

    def save(self, doc: DocumentVO) -> DocumentVO:
        path = self._kb_dir(doc.knowledge_base_id) / f"{doc.id}.json"
        path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        return doc

    def delete(self, kb_id: str, doc_id: str) -> bool:
        path = self._kb_dir(kb_id) / f"{doc_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False


document_store = DocumentStore()
