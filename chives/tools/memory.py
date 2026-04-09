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
        """Recall stored facts relevant to a query."""
        assert _store is not None
        memories = _store.get_all_memories()
        if not memories:
            return "No facts stored yet."
        hits = [m["fact"] for m in memories if query.lower() in m["fact"].lower()]
        if not hits:
            # Return most recent 10 facts when no substring match
            hits = [m["fact"] for m in memories[-10:]]
        return "\n".join(f"- {h}" for h in hits)

    globals()["store_fact"] = store_fact
    globals()["recall_facts"] = recall_facts
