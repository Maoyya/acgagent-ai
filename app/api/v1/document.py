"""文档上传与管理 API 端点（隶属于某知识库）。"""
from fastapi import APIRouter, UploadFile, File

from app.models.common import Result
from app.services.document_service import document_service

router = APIRouter(tags=["document"])


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
):
    """上传文档到指定知识库，异步走 解析→分块→向量化；缺文件名返回 400，知识库不存在返回 404。"""
    if file.filename is None:
        return Result.error(code=400, message="上传文件缺少文件名（filename）")
    content = await file.read()
    doc = await document_service.upload_document(kb_id, file.filename, content)
    if doc is None:
        return Result.error(code=404, message=f"Knowledge base not found: {kb_id}")
    return Result.success(data=doc)


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_documents(kb_id: str):
    """列出某知识库下全部文档。"""
    docs = document_service.list_documents(kb_id)
    return Result.success(data=docs)


@router.get("/knowledge-bases/{kb_id}/documents/{doc_id}")
async def get_document(kb_id: str, doc_id: str):
    """获取单个文档；不存在返回 404。"""
    doc = document_service.get_document(kb_id, doc_id)
    if doc is None:
        return Result.error(code=404, message=f"Document not found: {doc_id}")
    return Result.success(data=doc)


@router.delete("/knowledge-bases/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    """删除文档；不存在返回 404。"""
    ok = document_service.delete_document(kb_id, doc_id)
    if not ok:
        return Result.error(code=404, message=f"Document not found: {doc_id}")
    return Result.success()
