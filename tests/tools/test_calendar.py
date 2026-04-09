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
    """Patch EventKit at the module level before import."""
    mock_store = MagicMock()
    mock_event = MagicMock()
    mock_event.title.return_value = "Dentist"
    mock_event.startDate.return_value = MagicMock()
    mock_event.startDate.return_value.description.return_value = "2026-04-10 10:00:00 +0000"
    mock_event.location.return_value = "123 Main St"
    mock_store.eventsMatchingPredicate_.return_value = [mock_event]

    EventKit_mock = MagicMock()
    EventKit_mock.EKEventStore.alloc.return_value.init.return_value = mock_store
    EventKit_mock.EKEntityTypeEvent = 0

    Foundation_mock = MagicMock()
    Foundation_mock.NSDate.dateWithTimeIntervalSince1970_.return_value = MagicMock()

    with patch.dict("sys.modules", {"EventKit": EventKit_mock, "Foundation": Foundation_mock}):
        import importlib
        import sys
        # Remove cached module so we get a fresh import with mocked deps
        sys.modules.pop("chives.tools.calendar", None)
        import chives.tools.calendar as cal
        cal._ek_store = mock_store
        yield mock_store, cal


def test_list_events_today(mock_ek):
    mock_store, cal = mock_ek
    result = cal.list_calendar_events(period="today")
    data = json.loads(result)
    assert isinstance(data, list)


def test_create_event_returns_confirmation(mock_ek):
    mock_store, cal = mock_ek
    mock_store.saveEvent_span_commit_error_.return_value = True
    result = cal.create_calendar_event(
        title="Meeting",
        start_iso="2026-04-10T10:00:00",
        end_iso="2026-04-10T11:00:00",
        location="Office",
    )
    assert "created" in result.lower() or "meeting" in result.lower()
