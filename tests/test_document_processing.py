"""
文档处理服务单元测试。

直接测试 DocumentService 的文件解析和分块逻辑，
不依赖 HTTP 请求和 ChromaDB 向量化。

覆盖场景：
- TXT 文件解析
- Markdown 文件解析
- 空文件不产生 chunks
- 分块参数生效（chunk_size / chunk_overlap）
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.services.document_service import DocumentService


@pytest.fixture
def service():
    return DocumentService()


def test_read_txt_file(service, tmp_path):
    """TXT 文件直接读取 UTF-8 内容。"""
    f = tmp_path / "test.txt"
    f.write_text("Hello world\nSecond line", encoding="utf-8")
    text = service._read_file(f)
    assert "Hello world" in text
    assert "Second line" in text


def test_read_md_file(service, tmp_path):
    """Markdown 文件按 TXT 处理，直接读取。"""
    f = tmp_path / "test.md"
    f.write_text("# Title\n\nParagraph", encoding="utf-8")
    text = service._read_file(f)
    assert "# Title" in text


def test_read_unsupported_file(service, tmp_path):
    """不支持的文件类型抛出 ValueError。"""
    f = tmp_path / "test.xyz"
    f.write_text("content", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        service._read_file(f)


def test_chunk_text_basic(service):
    """包含分隔符的长文本应被切分为多个 chunks。"""
    from app.models.knowledge_base import ChunkConfig
    config = ChunkConfig(chunk_size=50, chunk_overlap=10)
    # 使用分隔符让 splitter 能正常切分
    text = "\n\n".join([f"段落{i}这是一段用于测试分块功能的文本内容。" for i in range(10)])
    chunks = service._chunk_text(text, config)
    assert len(chunks) > 1


def test_chunk_empty_text(service):
    """空文本或纯空白文本不产生 chunks。"""
    from app.models.knowledge_base import ChunkConfig
    config = ChunkConfig()
    assert service._chunk_text("", config) == []
    assert service._chunk_text("   \n\n  ", config) == []


def test_chunk_short_text_single(service):
    """短文本（不足一个 chunk_size）应只产生一个 chunk。"""
    from app.models.knowledge_base import ChunkConfig
    config = ChunkConfig(chunk_size=1000, chunk_overlap=50)
    text = "这是一段很短的文本"
    chunks = service._chunk_text(text, config)
    assert len(chunks) == 1
    assert chunks[0] == text
