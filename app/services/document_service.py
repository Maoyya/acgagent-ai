import uuid
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.db.chroma_client import get_chroma
from app.db.document_store import document_store
from app.db.knowledge_store import knowledge_store
from app.models.document import DocumentVO
from app.models.knowledge_base import KnowledgeBase

logger = logging.getLogger("acgagent-ai")


class DocumentService:
    def list_documents(self, kb_id: str) -> list[DocumentVO]:
        return document_store.list_by_kb(kb_id)

    def get_document(self, kb_id: str, doc_id: str) -> DocumentVO | None:
        return document_store.get(kb_id, doc_id)

    async def upload_document(self, kb_id: str, file_name: str, file_content: bytes) -> DocumentVO:
        kb = knowledge_store.get(kb_id)
        if kb is None:
            return None

        doc_id = uuid.uuid4().hex[:12]

        upload_dir = settings.data_dir / "uploads" / kb_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{doc_id}_{file_name}"
        file_path.write_bytes(file_content)

        doc = DocumentVO(
            id=doc_id,
            knowledge_base_id=kb_id,
            file_name=file_name,
            file_size=len(file_content),
            status="processing",
            created_at=datetime.now(),
        )
        document_store.save(doc)

        asyncio.create_task(self._process_document(doc, kb, file_path))

        return doc

    async def _process_document(self, doc: DocumentVO, kb: KnowledgeBase, file_path: Path):
        try:
            text = self._read_file(file_path)
            chunks = self._chunk_text(text, kb.chunk_config)

            chroma = get_chroma()
            col_name = f"kb_{kb.id}_chunks"
            col = chroma.get_or_create_collection(
                name=col_name,
                metadata={"hnsw:space": "cosine"},
            )

            chunk_ids = [f"{doc.id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "doc_id": doc.id,
                    "chunk_index": i,
                    "source": doc.file_name,
                    "chunk_size": len(chunk),
                    "created_at": datetime.now().isoformat(),
                }
                for i, chunk in enumerate(chunks)
            ]

            col.add(
                ids=chunk_ids,
                documents=chunks,
                metadatas=metadatas,
            )

            doc.status = "completed"
            doc.chunk_count = len(chunks)
            document_store.save(doc)

            kb.document_count += 1
            kb.chunk_count += len(chunks)
            kb.updated_at = datetime.now()
            knowledge_store.save(kb)

            logger.info("Document %s processed: %d chunks", doc.id, len(chunks))

        except Exception as e:
            logger.error("Document processing failed for %s: %s", doc.id, e)
            doc.status = "failed"
            doc.error_message = str(e)
            document_store.save(doc)

    def _read_file(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext in (".txt", ".md"):
            return path.read_text(encoding="utf-8")
        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext == ".docx":
            from docx import Document
            doc = Document(str(path))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _chunk_text(self, text: str, chunk_config) -> list[str]:
        if not text.strip():
            return []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_config.chunk_size,
            chunk_overlap=chunk_config.chunk_overlap,
            separators=chunk_config.separators,
        )
        return splitter.split_text(text)

    def delete_document(self, kb_id: str, doc_id: str) -> bool:
        doc = document_store.get(kb_id, doc_id)
        if doc is None:
            return False

        chroma = get_chroma()
        try:
            col = chroma.get_collection(name=f"kb_{kb_id}_chunks")
            col.delete(where={"doc_id": doc_id})
        except Exception:
            pass

        kb = knowledge_store.get(kb_id)
        if kb:
            kb.document_count = max(0, kb.document_count - 1)
            kb.chunk_count = max(0, kb.chunk_count - doc.chunk_count)
            kb.updated_at = datetime.now()
            knowledge_store.save(kb)

        return document_store.delete(kb_id, doc_id)


document_service = DocumentService()
