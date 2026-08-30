import pytest
from chives.store import Store
import chives.tools.memory as memory_tools
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path))
    memory_tools.init(s)
    return s


def test_store_fact(store):
    result = memory_tools.store_fact("user likes coffee")
    assert "stored" in result.lower()
    mems = store.get_all_memories()
    assert any("coffee" in m["fact"] for m in mems)


def test_recall_facts(store):
    memory_tools.store_fact("user prefers short answers")
    memory_tools.store_fact("user has a dog named Biscuit")
    result = memory_tools.recall_facts("dog")
    assert "Biscuit" in result


def test_recall_empty(store):
    result = memory_tools.recall_facts("anything")
    assert "no" in result.lower() or result == ""


def test_update_fact(store):
    memory_tools.store_fact("user drinks tea")
    mem_id = store.get_all_memories()[0]["id"]

    result = memory_tools.update_fact(str(mem_id), "user drinks coffee")

    assert "updated" in result.lower()
    assert store.get_all_memories()[0]["fact"] == "user drinks coffee"


def test_update_missing_fact_reports_cleanly(store):
    result = memory_tools.update_fact("9999", "nope")
    assert "no fact found" in result.lower()


def test_delete_fact(store):
    memory_tools.store_fact("user has a cat")
    mem_id = store.get_all_memories()[0]["id"]

    result = memory_tools.delete_fact(str(mem_id))

    assert "deleted" in result.lower()
    assert store.get_all_memories() == []


def test_delete_missing_fact_reports_cleanly(store):
    result = memory_tools.delete_fact("9999")
    assert "no fact found" in result.lower()


def test_recall_falls_back_to_recent_when_no_match(store):
    """A query matching nothing still returns context rather than nothing."""
    for i in range(12):
        memory_tools.store_fact(f"fact number {i}")

    result = memory_tools.recall_facts("zzzz-no-such-word")

    assert result.count("\n") == 9, "expected the 10 most recent facts"
    assert "fact number 11" in result
    assert "fact number 1\n" not in result
