"""
文档处理服务。

处理文档的上传、解析、分块和向量化存储。
文档上传后立即返回，处理过程异步执行（asyncio.create_task），
调用方需通过查询文档状态来确认处理结果。
"""
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
        """列出指定知识库下的所有文档。"""
        return document_store.list_by_kb(kb_id)

    def get_document(self, kb_id: str, doc_id: str) -> DocumentVO | None:
        """获取单个文档详情。"""
        return document_store.get(kb_id, doc_id)

    async def upload_document(self, kb_id: str, file_name: str, file_content: bytes) -> DocumentVO:
        """上传文档并触发异步处理。

        流程：
        1. 校验知识库存在
        2. 保存原始文件到 uploads 目录
        3. 创建文档元数据（status="processing"）
        4. 启动异步处理任务
        5. 立即返回文档元数据，调用方可轮询状态
        """
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

        # 异步处理：解析 → 分块 → 向量化存入 ChromaDB
        asyncio.create_task(self._process_document(doc, kb, file_path))

        return doc

    async def _process_document(self, doc: DocumentVO, kb: KnowledgeBase, file_path: Path):
        """异步文档处理：解析文件内容 → 文本分块 → 写入 ChromaDB。

        处理成功：更新文档状态为 completed，更新知识库统计。
        处理失败：更新文档状态为 failed，记录错误信息。
        """
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
            # 向量化完成，更新文档状态和知识库统计

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
        """根据文件扩展名选择对应的解析器提取纯文本。"""
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
        """使用递归字符分割器按配置的 chunk_size/overlap/separators 切分文本。"""
        if not text.strip():
            return []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_config.chunk_size,
            chunk_overlap=chunk_config.chunk_overlap,
            separators=chunk_config.separators,
        )
        return splitter.split_text(text)

    def delete_document(self, kb_id: str, doc_id: str) -> bool:
        """删除文档：从 ChromaDB 清除 chunks + 更新知识库统计 + 删除元数据。"""
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
