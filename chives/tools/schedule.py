from __future__ import annotations
import json
from datetime import datetime
from chives.store import Store
from chives.tools.registry import tool

_store: Store | None = None
_connector: str = "telegram"
_thread_id: str = ""


def init(store: Store, connector: str, thread_id: str) -> None:
    global _store, _connector, _thread_id
    _store = store
    _connector = connector
    _thread_id = thread_id
    _register()


def _register() -> None:
    @tool
    def schedule_nudge(description: str, iso_datetime: str) -> str:
        """Schedule a one-shot follow-up nudge at a specific date/time. iso_datetime must be ISO 8601."""
        assert _store is not None
        fire_at = datetime.fromisoformat(iso_datetime).timestamp()
        nudge_id = _store.add_nudge(description, fire_at, _connector, _thread_id)
        return json.dumps({"nudge_id": nudge_id, "scheduled_for": iso_datetime})

    @tool
    def cancel_nudge(nudge_id: str) -> str:
        """Cancel a previously scheduled nudge by its ID."""
        assert _store is not None
        _store.cancel_nudge(int(nudge_id))
        return f"Cancelled nudge {nudge_id}."

    globals().update({
        "schedule_nudge": schedule_nudge,
        "cancel_nudge": cancel_nudge,
    })
