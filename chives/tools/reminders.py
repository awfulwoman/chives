from __future__ import annotations
import json
import threading
from chives.tools.registry import tool

_ek_store = None


def _get_store():
    global _ek_store
    if _ek_store is not None:
        return _ek_store
    import EventKit

    store = EventKit.EKEventStore.alloc().init()
    done = threading.Event()

    def cb(granted, error):
        done.set()

    try:
        store.requestFullAccessToRemindersWithCompletion_(cb)
    except AttributeError:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeReminder, cb)

    done.wait(timeout=10)
    _ek_store = store
    return store


@tool
def list_reminders(include_completed: str) -> str:
    """List reminders. include_completed must be 'true' or 'false'."""
    import EventKit

    store = _get_store()
    store.refreshSourcesIfNecessary()
    done = threading.Event()
    found: list = []

    pred = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
        None, None, None
    )

    def cb(reminders):
        found.extend(reminders or [])
        done.set()

    store.fetchRemindersMatchingPredicate_completion_(pred, cb)
    done.wait(timeout=10)

    results = []
    for r in found:
        if include_completed == "false" and r.isCompleted():
            continue
        results.append({
            "title": str(r.title()),
            "completed": bool(r.isCompleted()),
        })
    return json.dumps(results)


@tool
def create_reminder(title: str, due_iso: str) -> str:
    """Create a reminder. due_iso is optional ISO 8601 date or empty string."""
    import EventKit

    store = _get_store()
    reminder = EventKit.EKReminder.reminderWithEventStore_(store)
    reminder.setTitle_(title)
    reminder.setCalendar_(store.defaultCalendarForNewReminders())

    if due_iso:
        from datetime import datetime
        import Foundation

        dt = datetime.fromisoformat(due_iso)
        components = Foundation.NSDateComponents.alloc().init()
        components.setYear_(dt.year)
        components.setMonth_(dt.month)
        components.setDay_(dt.day)
        components.setHour_(dt.hour)
        components.setMinute_(dt.minute)
        reminder.setDueDateComponents_(components)

    ok = store.saveReminder_commit_error_(reminder, True, None)
    if ok:
        return f"Created reminder: {title}"
    return f"Failed to create reminder: {title}"


@tool
def complete_reminder(title: str) -> str:
    """Mark a reminder as completed by title (case-insensitive match)."""
    import EventKit

    store = _get_store()
    store.refreshSourcesIfNecessary()
    done = threading.Event()
    found: list = []

    pred = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
        None, None, None
    )

    def cb(reminders):
        found.extend(reminders or [])
        done.set()

    store.fetchRemindersMatchingPredicate_completion_(pred, cb)
    done.wait(timeout=10)

    for r in found:
        if title.lower() in str(r.title()).lower():
            r.setCompleted_(True)
            store.saveReminder_commit_error_(r, True, None)
            return f"Completed: {r.title()}"

    return f"No reminder found matching: {title}"
