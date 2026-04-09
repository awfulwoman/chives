import json
import pytest
from unittest.mock import MagicMock, patch
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def mock_ek(monkeypatch):
    mock_store = MagicMock()
    mock_reminder = MagicMock()
    mock_reminder.title.return_value = "Buy milk"
    mock_reminder.isCompleted.return_value = False
    mock_reminder.dueDateComponents.return_value = None
    mock_store.fetchRemindersMatchingPredicate_completion_.side_effect = (
        lambda pred, cb: cb([mock_reminder])
    )

    EventKit_mock = MagicMock()
    EventKit_mock.EKEventStore.alloc.return_value.init.return_value = mock_store
    EventKit_mock.EKEntityTypeReminder = 1

    with patch.dict("sys.modules", {"EventKit": EventKit_mock}):
        import sys
        sys.modules.pop("chives.tools.reminders", None)
        import chives.tools.reminders as rem
        rem._ek_store = mock_store
        yield mock_store, rem


def test_list_reminders(mock_ek):
    mock_store, rem = mock_ek
    result = rem.list_reminders(include_completed="false")
    data = json.loads(result)
    assert isinstance(data, list)


def test_create_reminder(mock_ek):
    mock_store, rem = mock_ek
    mock_store.saveReminder_commit_error_.return_value = True
    result = rem.create_reminder(title="Call doctor", due_iso="")
    assert "call doctor" in result.lower() or "created" in result.lower()
