import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from chives.config import Config
from chives.store import Store


@pytest.fixture
def config(tmp_path):
    c = Config()
    c.state_path = str(tmp_path / "state")
    c.profile_path = str(tmp_path / "profile")
    c.telegram.allowed_chat_ids = [42]
    c.idle_checkin_hours = 0
    (tmp_path / "profile").mkdir()
    return c


async def test_nudge_check_fires_pending(config, tmp_path):
    import time
    store = Store(config.state_path)
    nid = store.add_nudge("Call dentist", time.time() - 1, "telegram", "42")

    mock_agent = AsyncMock(return_value="Reminder: Call dentist")
    mock_telegram = AsyncMock()
    mock_telegram.send = AsyncMock()

    with patch("apscheduler.schedulers.asyncio.AsyncIOScheduler.start"):
        from chives.scheduler import Scheduler
        sched = Scheduler(config, mock_agent, store, mock_telegram)
        await sched._check_nudges()

    mock_telegram.send.assert_called_once()
    assert store.get_pending_nudges() == []


async def test_nudge_check_skips_when_telegram_disabled(config, tmp_path):
    import time
    store = Store(config.state_path)
    store.add_nudge("Call dentist", time.time() - 1, "telegram", "42")

    mock_agent = AsyncMock(return_value="Reminder: Call dentist")

    with patch("apscheduler.schedulers.asyncio.AsyncIOScheduler.start"):
        from chives.scheduler import Scheduler
        sched = Scheduler(config, mock_agent, store, None)
        await sched._check_nudges()

    mock_agent.assert_not_called()
    assert len(store.get_pending_nudges()) == 1


# --- start(): job registration and cron parsing ---


def _sched(config, store, telegram=None):
    from chives.scheduler import Scheduler

    return Scheduler(config, AsyncMock(), store, telegram or AsyncMock())


def test_start_registers_expected_jobs(config):
    store = Store(config.state_path)
    sched = _sched(config, store)

    with patch("apscheduler.schedulers.asyncio.AsyncIOScheduler.start"):
        sched.start()

    jobs = sched._scheduler.get_jobs()
    assert len(jobs) == 3, "expected morning brief + nudge check + event reminders"


def test_start_registers_idle_checkin_when_enabled(config):
    config.idle_checkin_hours = 4
    store = Store(config.state_path)
    sched = _sched(config, store)

    with patch("apscheduler.schedulers.asyncio.AsyncIOScheduler.start"):
        sched.start()

    assert len(sched._scheduler.get_jobs()) == 4


def test_start_uses_configured_brief_time(config):
    config.morning_brief_time = "06:45"
    store = Store(config.state_path)
    sched = _sched(config, store)

    with patch("apscheduler.schedulers.asyncio.AsyncIOScheduler.start"):
        sched.start()

    brief = sched._scheduler.get_jobs()[0]
    assert str(brief.trigger.fields[brief.trigger.FIELD_NAMES.index("hour")]) == "6"
    assert str(brief.trigger.fields[brief.trigger.FIELD_NAMES.index("minute")]) == "45"


def test_start_rejects_malformed_brief_time(config):
    """A bad CHIVES_MORNING_BRIEF_TIME must fail loudly at startup, not silently."""
    config.morning_brief_time = "quarter past eight"
    store = Store(config.state_path)
    sched = _sched(config, store)

    with patch("apscheduler.schedulers.asyncio.AsyncIOScheduler.start"):
        with pytest.raises(ValueError):
            sched.start()


async def test_idle_checkin_messages_every_allowed_chat(config):
    config.telegram.allowed_chat_ids = [42, 43]
    store = Store(config.state_path)
    telegram = AsyncMock()
    sched = _sched(config, store, telegram)

    await sched._idle_checkin()

    assert telegram.send.await_count == 2


# --- _check_event_reminders ---


def _event(start: str, title: str = "Standup", location: str = "") -> dict:
    return {"title": title, "start": start, "location": location}


def _in_minutes(mins: float, suffix: str = "+00:00") -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat().replace(
        "+00:00", suffix
    )


async def _run_reminders(config, events, telegram):
    import json as _json

    store = Store(config.state_path)
    sched = _sched(config, store, telegram)
    with patch(
        "chives.scheduler.dispatch_tool", AsyncMock(return_value=_json.dumps(events))
    ):
        await sched._check_event_reminders()


async def test_event_inside_window_triggers_reminder(config):
    telegram = AsyncMock()
    await _run_reminders(config, [_event(_in_minutes(10))], telegram)

    telegram.send.assert_awaited_once()
    chat_id, msg = telegram.send.await_args.args
    assert chat_id == 42
    assert "Standup" in msg and "min" in msg


async def test_event_beyond_window_is_ignored(config):
    telegram = AsyncMock()
    await _run_reminders(config, [_event(_in_minutes(60))], telegram)

    telegram.send.assert_not_awaited()


async def test_event_already_started_is_ignored(config):
    telegram = AsyncMock()
    await _run_reminders(config, [_event(_in_minutes(-5))], telegram)

    telegram.send.assert_not_awaited()


async def test_event_at_window_boundary_triggers(config):
    """delta == event_reminder_minutes is inclusive; 14.5 lands inside 15."""
    telegram = AsyncMock()
    await _run_reminders(config, [_event(_in_minutes(14.5))], telegram)

    telegram.send.assert_awaited_once()


async def test_reminder_includes_location(config):
    telegram = AsyncMock()
    await _run_reminders(config, [_event(_in_minutes(5), location="Room 3")], telegram)

    _, msg = telegram.send.await_args.args
    assert "at Room 3" in msg


async def test_naive_timestamp_is_treated_as_utc(config):
    """Events without a tz offset must not blow up the comparison."""
    from datetime import datetime, timedelta, timezone

    naive = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(tzinfo=None).isoformat()
    telegram = AsyncMock()
    await _run_reminders(config, [_event(naive)], telegram)

    telegram.send.assert_awaited_once()


async def test_unparseable_timestamp_skips_only_that_event(config):
    """One bad event must not suppress reminders for the good ones."""
    telegram = AsyncMock()
    await _run_reminders(
        config,
        [_event("not a date", title="Broken"), _event(_in_minutes(5), title="Good")],
        telegram,
    )

    telegram.send.assert_awaited_once()
    _, msg = telegram.send.await_args.args
    assert "Good" in msg


async def test_non_list_tool_result_is_ignored(config):
    telegram = AsyncMock()
    await _run_reminders(config, {"error": "calendar unavailable"}, telegram)

    telegram.send.assert_not_awaited()


async def test_tool_failure_does_not_propagate(config):
    """A gateway outage must not crash the scheduler job."""
    store = Store(config.state_path)
    telegram = AsyncMock()
    sched = _sched(config, store, telegram)

    with patch(
        "chives.scheduler.dispatch_tool", AsyncMock(side_effect=RuntimeError("gateway down"))
    ):
        await sched._check_event_reminders()

    telegram.send.assert_not_awaited()


async def test_invalid_json_from_tool_is_ignored(config):
    store = Store(config.state_path)
    telegram = AsyncMock()
    sched = _sched(config, store, telegram)

    with patch("chives.scheduler.dispatch_tool", AsyncMock(return_value="<html>502</html>")):
        await sched._check_event_reminders()

    telegram.send.assert_not_awaited()


async def test_reminder_goes_to_every_allowed_chat(config):
    config.telegram.allowed_chat_ids = [42, 43]
    telegram = AsyncMock()
    await _run_reminders(config, [_event(_in_minutes(5))], telegram)

    assert telegram.send.await_count == 2
