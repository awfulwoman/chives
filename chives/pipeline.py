from __future__ import annotations
import time
from chives.bus import Message, Handler


def build_pipeline(agent_handler: Handler, middlewares: list) -> Handler:
    handler = agent_handler
    for mw in reversed(middlewares):
        _next = handler

        async def _dispatch(msg: Message, mw=mw, next_h=_next) -> str:
            return await mw(msg, next_h)

        handler = _dispatch
    return handler


def rate_limit_middleware(min_seconds: float = 1.0):
    last_seen: dict[str, float] = {}

    async def middleware(msg: Message, next_handler: Handler) -> str:
        now = time.monotonic()
        last = last_seen.get(msg.thread_id, 0)
        if now - last < min_seconds:
            return "Slow down — I'm still thinking about your last message."
        last_seen[msg.thread_id] = now
        return await next_handler(msg)

    return middleware


def slash_command_middleware():
    async def middleware(msg: Message, next_handler: Handler) -> str:
        if msg.text.startswith("/help"):
            return (
                "Commands:\n"
                "/help — show this\n"
                "/clear — clear conversation history\n"
                "/brief — morning brief now\n"
            )
        if msg.text.startswith("/brief"):
            msg.text = "Generate the morning brief now."
            return await next_handler(msg)
        return await next_handler(msg)

    return middleware
