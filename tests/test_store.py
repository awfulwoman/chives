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


def test_update_memory(store):
    store.add_memory("original")
    mem_id = store.get_all_memories()[0]["id"]

    assert store.update_memory(mem_id, "revised") is True
    assert store.get_all_memories()[0]["fact"] == "revised"


def test_update_missing_memory_returns_false(store):
    assert store.update_memory(9999, "nope") is False


def test_delete_memory(store):
    store.add_memory("temporary")
    mem_id = store.get_all_memories()[0]["id"]

    assert store.delete_memory(mem_id) is True
    assert store.get_all_memories() == []


def test_delete_missing_memory_returns_false(store):
    assert store.delete_memory(9999) is False


def test_cancel_nudge_removes_it(store):
    import time

    nid = store.add_nudge("call dentist", time.time() - 1, "telegram", "42")
    assert store.get_pending_nudges()

    store.cancel_nudge(nid)

    assert store.get_pending_nudges() == []


def test_future_nudge_is_not_pending(store):
    import time

    store.add_nudge("next week", time.time() + 86400, "telegram", "42")
    assert store.get_pending_nudges() == []
