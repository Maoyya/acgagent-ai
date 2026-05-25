import uuid
import pytest
from app.db.chroma_client import init_chroma, close_chroma, get_chroma
from app.db.memory_store import memory_store
from app.core.memory import ConversationMemory, count_tokens
from app.models.agent import MemoryConfig


@pytest.fixture(autouse=True)
def setup_chroma():
    init_chroma()
    yield
    # Clean up all test collections after each test
    try:
        chroma = get_chroma()
        for col in chroma.list_collections():
            if col.name.startswith("memory_conv_"):
                chroma.delete_collection(col.name)
    except Exception:
        pass
    close_chroma()


def test_count_tokens():
    assert count_tokens("hello world") > 0
    assert count_tokens("你好世界") > 0


def test_save_and_load_messages():
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    memory_store.save_message(conv_id, "user", "Hello", token_count=5)
    memory_store.save_message(conv_id, "assistant", "Hi there!", token_count=10)

    history = memory_store.load_history(conv_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[1]["role"] == "assistant"


def test_conversation_memory_trim():
    config = MemoryConfig(type="conversation_window", max_tokens=20)
    memory = ConversationMemory(config)

    conv_id = f"test_conv_trim_{uuid.uuid4().hex[:8]}"
    for i in range(10):
        memory_store.save_message(conv_id, "user", f"Message {i} with enough words to use tokens", token_count=15)

    messages = memory.load_messages(conv_id)
    total_tokens = sum(count_tokens(m.content) for m in messages)
    assert total_tokens <= config.max_tokens


def test_delete_conversation():
    conv_id = f"test_conv_del_{uuid.uuid4().hex[:8]}"
    memory_store.save_message(conv_id, "user", "Bye", token_count=5)
    memory_store.delete_conversation(conv_id)

    history = memory_store.load_history(conv_id)
    assert len(history) == 0
