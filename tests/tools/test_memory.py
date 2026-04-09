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
