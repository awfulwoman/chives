from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from chives.tools.registry import tool

_ek_store = None


def _get_store():
    global _ek_store
    if _ek_store is not None:
        return _ek_store
    import EventKit
    import threading

    store = EventKit.EKEventStore.alloc().init()
    done = threading.Event()

    def cb(granted, error):
        done.set()

    # macOS 14+: requestFullAccessToEventsWithCompletion_
    # macOS 13: requestAccessToEntityType_completion_
    try:
        store.requestFullAccessToEventsWithCompletion_(cb)
    except AttributeError:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, cb)

    done.wait(timeout=10)
    _ek_store = store
    return store


def _ns_date(iso: str):
    import Foundation
    dt = datetime.fromisoformat(iso)
    ts = dt.timestamp()
    return Foundation.NSDate.dateWithTimeIntervalSince1970_(ts)


@tool
def list_calendar_events(period: str) -> str:
    """List calendar events. period must be 'today' or 'week'."""
    import EventKit
    store = _get_store()

    now = datetime.now(timezone.utc)
    if period == "today":
        end = now.replace(hour=23, minute=59, second=59)
    else:
        end = now + timedelta(days=7)

    import Foundation
    ns_start = Foundation.NSDate.dateWithTimeIntervalSince1970_(now.timestamp())
    ns_end = Foundation.NSDate.dateWithTimeIntervalSince1970_(end.timestamp())

    calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, calendars
    )
    events = store.eventsMatchingPredicate_(pred)

    results = []
    for ev in (events or []):
        results.append({
            "title": str(ev.title()),
            "start": str(ev.startDate().description()),
            "location": str(ev.location() or ""),
        })
    return json.dumps(results)


@tool
def create_calendar_event(title: str, start_iso: str, end_iso: str, location: str) -> str:
    """Create a calendar event. Dates must be ISO 8601 format (e.g. 2026-04-10T14:00:00)."""
    import EventKit
    store = _get_store()

    event = EventKit.EKEvent.eventWithEventStore_(store)
    event.setTitle_(title)
    event.setStartDate_(_ns_date(start_iso))
    event.setEndDate_(_ns_date(end_iso))
    if location:
        event.setLocation_(location)
    event.setCalendar_(store.defaultCalendarForNewEvents())

    error_ptr = None
    ok = store.saveEvent_span_commit_error_(
        event, EventKit.EKSpanThisEvent, True, error_ptr
    )
    if ok:
        return f"Created event: {title} at {start_iso}"
    return f"Failed to create event: {title}"
