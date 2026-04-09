from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable


@dataclass
class Message:
    connector: str
    thread_id: str
    chat_id: int
    text: str


Handler = Callable[[Message], Awaitable[str]]


class Bus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Message] = asyncio.Queue()
        self._handlers: list[Handler] = []

    def add_handler(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def put(self, message: Message) -> None:
        await self._queue.put(message)

    async def run_once(self) -> None:
        message = self._queue.get_nowait()
        for handler in self._handlers:
            await handler(message)

    async def run(self) -> None:
        while True:
            message = await self._queue.get()
            for handler in self._handlers:
                await handler(message)
