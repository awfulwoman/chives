from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from chives.config import Config
from chives.store import Store


class Scheduler:
    def __init__(self, config: Config, agent, store: Store, telegram) -> None:
        self.config = config
        self.agent = agent
        self.store = store
        self.telegram = telegram
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        hour, minute = self.config.morning_brief_time.split(":")
        self._scheduler.add_job(
            self._morning_brief,
            CronTrigger(hour=int(hour), minute=int(minute)),
        )
        self._scheduler.add_job(
            self._check_nudges, "interval", minutes=1
        )
        self._scheduler.add_job(
            self._check_event_reminders, "interval", minutes=1
        )
        if self.config.idle_checkin_hours > 0:
            self._scheduler.add_job(
                self._idle_checkin,
                "interval",
                hours=self.config.idle_checkin_hours,
            )
        self._scheduler.start()

    async def _morning_brief(self) -> None:
        prompt = (
            "Generate the morning brief: today's calendar events, overdue reminders, "
            "and unread emails needing action. Max 10 lines. Most urgent first."
        )
        response = await self.agent(prompt, "scheduler", "morning_brief")
        for chat_id in self.config.telegram.allowed_chat_ids:
            await self.telegram.send(chat_id, response)

    async def _check_nudges(self) -> None:
        for nudge in self.store.get_pending_nudges():
            prompt = f"Send a gentle follow-up nudge: {nudge['description']}"
            response = await self.agent(prompt, "scheduler", nudge["thread_id"])
            await self.telegram.send(int(nudge["thread_id"]), response)
            self.store.mark_nudge_fired(nudge["id"])

    async def _check_event_reminders(self) -> None:
        from datetime import datetime, timezone, timedelta
        import json as _json
        from chives.tools.registry import _registry

        list_events = _registry.get("list_calendar_events")
        if list_events is None:
            return

        try:
            raw = list_events(period="today")
            events = _json.loads(raw)
        except Exception:
            return

        now = datetime.now(timezone.utc)

        for ev in events:
            try:
                start_str = ev.get("start", "")
                start = datetime.fromisoformat(start_str[:19])
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                delta = (start - now).total_seconds() / 60
                if 0 <= delta <= self.config.event_reminder_minutes:
                    title = ev.get("title", "event")
                    location = ev.get("location", "")
                    loc_str = f" at {location}" if location else ""
                    msg = f"Heads up: {title}{loc_str} starts in {int(delta)} min."
                    for chat_id in self.config.telegram.allowed_chat_ids:
                        await self.telegram.send(chat_id, msg)
            except Exception:
                continue

    async def _idle_checkin(self) -> None:
        for chat_id in self.config.telegram.allowed_chat_ids:
            await self.telegram.send(chat_id, "Still here — anything you need?")
