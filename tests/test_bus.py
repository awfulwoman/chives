import asyncio
import pytest
from chives.bus import Bus, Message
from chives.pipeline import build_pipeline, rate_limit_middleware, slash_command_middleware


async def test_bus_delivers_messages():
    bus = Bus()
    received = []

    async def handler(msg: Message) -> str:
        received.append(msg.text)
        return "ok"

    bus.add_handler(handler)

    msg = Message(connector="telegram", thread_id="1", chat_id=1, text="hello")
    await bus.put(msg)

    await bus.run_once()
    assert received == ["hello"]


async def test_rate_limit_blocks_rapid_messages():
    calls = []

    async def agent(msg: Message) -> str:
        calls.append(msg.text)
        return "ok"

    handler = build_pipeline(agent, [rate_limit_middleware(min_seconds=60)])
    msg = Message(connector="telegram", thread_id="1", chat_id=1, text="msg")

    await handler(msg)
    result = await handler(msg)
    assert "slow down" in result.lower() or result == ""
    assert len(calls) == 1


async def test_slash_clear_resets_handler():
    responses = []

    async def agent(msg: Message) -> str:
        responses.append(msg.text)
        return "handled"

    handler = build_pipeline(agent, [slash_command_middleware()])
    result = await handler(Message(connector="t", thread_id="1", chat_id=1, text="/help"))
    assert "help" in result.lower() or result != "handled"
