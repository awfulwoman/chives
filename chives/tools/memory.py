from __future__ import annotations
from chives.store import Store
from chives.tools.registry import tool

_store: Store | None = None


def init(store: Store) -> None:
    global _store
    _store = store
    # Register tools now that we have dependencies
    _register()


def _register() -> None:
    @tool
    def store_fact(fact: str) -> str:
        """Store a fact about the user or their context for future recall."""
        assert _store is not None
        _store.add_memory(fact)
        return f"Stored: {fact}"

    @tool
    def recall_facts(query: str) -> str:
        """Recall stored facts relevant to a query. Returns id and fact for each result."""
        assert _store is not None
        memories = _store.get_all_memories()
        if not memories:
            return "No facts stored yet."
        hits = [m for m in memories if query.lower() in m["fact"].lower()]
        if not hits:
            hits = memories[-10:]
        return "\n".join(f"[{m['id']}] {m['fact']}" for m in hits)

    @tool
    def update_fact(memory_id: str, new_fact: str) -> str:
        """Update a stored fact by its id (from recall_facts)."""
        assert _store is not None
        ok = _store.update_memory(int(memory_id), new_fact)
        return f"Updated fact {memory_id}." if ok else f"No fact found with id {memory_id}."

    @tool
    def delete_fact(memory_id: str) -> str:
        """Delete a stored fact by its id (from recall_facts)."""
        assert _store is not None
        ok = _store.delete_memory(int(memory_id))
        return f"Deleted fact {memory_id}." if ok else f"No fact found with id {memory_id}."

    globals()["store_fact"] = store_fact
    globals()["recall_facts"] = recall_facts
    globals()["update_fact"] = update_fact
    globals()["delete_fact"] = delete_fact
