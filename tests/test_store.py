import time
import pytest
from chives.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path))


def test_add_and_get_turns(store):
    store.add_turn("telegram", "123", "user", "hello")
    store.add_turn("telegram", "123", "assistant", "hi there")
    turns = store.get_turns("telegram", "123")
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "hello"
    assert turns[1]["role"] == "assistant"


def test_turns_isolated_by_thread(store):
    store.add_turn("telegram", "123", "user", "thread 1")
    store.add_turn("telegram", "456", "user", "thread 2")
    assert len(store.get_turns("telegram", "123")) == 1
    assert len(store.get_turns("telegram", "456")) == 1


def test_add_and_get_memory(store):
    store.add_memory("user prefers bullet points")
    mems = store.get_all_memories()
    assert len(mems) == 1
    assert mems[0]["fact"] == "user prefers bullet points"


def test_nudge_lifecycle(store):
    fire_at = time.time() - 1  # already past
    nid = store.add_nudge("call dentist", fire_at, "telegram", "123")
    pending = store.get_pending_nudges()
    assert any(n["id"] == nid for n in pending)
    store.mark_nudge_fired(nid)
    assert not any(n["id"] == nid for n in store.get_pending_nudges())


def test_email_seen(store):
    assert not store.is_email_seen("msg-001")
    store.mark_email_seen("msg-001")
    assert store.is_email_seen("msg-001")
    # idempotent
    store.mark_email_seen("msg-001")
    assert store.is_email_seen("msg-001")
