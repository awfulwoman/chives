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
    c.event_reminder_minutes = 15
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
