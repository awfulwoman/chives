import json
import sqlite3
import time
import pytest
from chives.store import Store
import chives.tools.schedule as sched_tools
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path))
    sched_tools.init(s, connector="telegram", thread_id="123")
    return s


def test_schedule_nudge(store):
    result = sched_tools.schedule_nudge(
        description="Follow up on dentist appointment",
        iso_datetime="2026-04-15T09:00:00",
    )
    data = json.loads(result)
    assert "nudge_id" in data
    assert "scheduled_for" in data
    # Verify it's actually in the DB
    conn = sqlite3.connect(store.db_path)
    row = conn.execute("SELECT description FROM nudges WHERE id=?", (data["nudge_id"],)).fetchone()
    assert row is not None
    assert "dentist" in row[0].lower()


def test_cancel_nudge(store):
    result = sched_tools.schedule_nudge(
        description="test nudge",
        iso_datetime="2026-04-15T09:00:00",
    )
    nid = json.loads(result)["nudge_id"]
    cancel_result = sched_tools.cancel_nudge(nudge_id=str(nid))
    assert "cancelled" in cancel_result.lower() or "canceled" in cancel_result.lower()
    # Verify removed from DB
    conn = sqlite3.connect(store.db_path)
    row = conn.execute("SELECT id FROM nudges WHERE id=?", (nid,)).fetchone()
    assert row is None
