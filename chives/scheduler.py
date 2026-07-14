from __future__ import annotations
import json as _json
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from chives.config import Config
from chives.store import Store
from chives.tools.registry import dispatch_tool


class Scheduler:
    def __init__(self, config: Config, agent, store: Store, telegram) -> None:
        self.config = config
        self.agent = agent
        self.store = store
        self.telegram = telegram
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
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

    async def _check_nudges(self) -> None:
        if self.telegram is None:
            return
        for nudge in self.store.get_pending_nudges():
            prompt = f"Send a gentle follow-up nudge: {nudge['description']}"
            response = await self.agent(prompt, "scheduler", nudge["thread_id"])
            await self.telegram.send(int(nudge["thread_id"]), response)
            self.store.mark_nudge_fired(nudge["id"])

    async def _check_event_reminders(self) -> None:
        try:
            raw = await dispatch_tool("list_calendar_events", _json.dumps({"period": "today"}))
            events = _json.loads(raw)
            if not isinstance(events, list):
                return
        except Exception:
            return

        now = datetime.now(timezone.utc)

        for ev in events:
            try:
                start_str = ev.get("start", "")
                try:
                    start = datetime.fromisoformat(start_str)
                except ValueError:
                    start = datetime.fromisoformat(start_str[:19]).replace(tzinfo=timezone.utc)
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
