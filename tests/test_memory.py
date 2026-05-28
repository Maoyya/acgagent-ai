"""
对话记忆单元测试。

直接测试 MemoryStore 和 ConversationMemory 的核心逻辑，
不依赖 HTTP 请求，使用真实的 ChromaDB PersistentClient。

覆盖场景：
- token 计数（英文/中文）
- 消息保存和加载
- 滑动窗口裁剪：超出 token 预算的早期消息被丢弃
- 删除整个会话
- none 类型记忆不读写
- 空会话 ID 不崩溃
- 加载不存在的会话返回空列表
"""
import uuid
import pytest
from app.db.chroma_client import init_chroma, close_chroma, get_chroma
from app.db.memory_store import memory_store
from app.core.memory import ConversationMemory, count_tokens
from app.models.agent import MemoryConfig


@pytest.fixture(autouse=True)
def setup_chroma():
    """每个测试前后初始化 ChromaDB，清理测试产生的 collection。"""
    init_chroma()
    yield
    # 清理所有测试创建的 memory collection
    try:
        chroma = get_chroma()
        for col in chroma.list_collections():
            if col.name.startswith("memory_conv_"):
                chroma.delete_collection(col.name)
    except Exception:
        pass
    close_chroma()


def test_count_tokens():
    """token 计数对英文和中文均返回正整数。"""
    assert count_tokens("hello world") > 0
    assert count_tokens("你好世界") > 0


def test_save_and_load_messages():
    """保存两条消息后加载，顺序和内容应一致。"""
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    memory_store.save_message(conv_id, "user", "Hello", token_count=5)
    memory_store.save_message(conv_id, "assistant", "Hi there!", token_count=10)

    history = memory_store.load_history(conv_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[1]["role"] == "assistant"


def test_conversation_memory_trim():
    """滑动窗口裁剪：10 条消息，每条约 15 token，预算 20 token。
    加载后只保留最新的 1 条消息（总 token 不超预算）。"""
    config = MemoryConfig(type="conversation_window", max_tokens=20)
    memory = ConversationMemory(config)

    conv_id = f"test_conv_trim_{uuid.uuid4().hex[:8]}"
    for i in range(10):
        memory_store.save_message(conv_id, "user", f"Message {i} with enough words to use tokens", token_count=15)

    messages = memory.load_messages(conv_id)
    total_tokens = sum(count_tokens(m.content) for m in messages)
    assert total_tokens <= config.max_tokens


def test_delete_conversation():
    """删除会话后再次加载返回空列表。"""
    conv_id = f"test_conv_del_{uuid.uuid4().hex[:8]}"
    memory_store.save_message(conv_id, "user", "Bye", token_count=5)
    memory_store.delete_conversation(conv_id)

    history = memory_store.load_history(conv_id)
    assert len(history) == 0


def test_memory_type_none():
    """MemoryConfig type=none 时不读写任何消息。"""
    config = MemoryConfig(type="none")
    memory = ConversationMemory(config)
    conv_id = f"test_conv_none_{uuid.uuid4().hex[:8]}"

    # save 不应该写入
    memory.save_user_message(conv_id, "Hello")
    memory.save_assistant_message(conv_id, "Hi")

    # load 应该返回空
    messages = memory.load_messages(conv_id)
    assert messages == []


def test_empty_conversation_id():
    """空 conversation_id 时不崩溃，save 静默忽略，load 返回空。"""
    config = MemoryConfig(type="conversation_window", max_tokens=8000)
    memory = ConversationMemory(config)

    memory.save_user_message("", "Hello")
    messages = memory.load_messages("")
    assert messages == []


def test_load_nonexistent_conversation():
    """加载从未写入过的会话返回空列表。"""
    conv_id = f"test_conv_missing_{uuid.uuid4().hex[:8]}"
    history = memory_store.load_history(conv_id)
    assert history == []
