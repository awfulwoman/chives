from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
        self._scheduler.add_job(
            self._check_nudges, "interval", minutes=1
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

    async def _idle_checkin(self) -> None:
        for chat_id in self.config.telegram.allowed_chat_ids:
            await self.telegram.send(chat_id, "Still here — anything you need?")
