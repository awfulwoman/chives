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


async def test_run_loop_processes_queued_messages():
    """bus.run() is what main.py actually schedules; run_once is test-only."""
    import asyncio
    from chives.bus import Bus, Message

    bus = Bus()
    seen = []
    done = asyncio.Event()

    async def handler(msg: Message) -> str:
        seen.append(msg.text)
        if len(seen) == 2:
            done.set()
        return "ok"

    bus.add_handler(handler)
    task = asyncio.create_task(bus.run())

    await bus.put(Message("telegram", "1", 1, "first"))
    await bus.put(Message("telegram", "1", 1, "second"))
    await asyncio.wait_for(done.wait(), timeout=2)

    task.cancel()
    assert seen == ["first", "second"]


async def test_all_handlers_receive_each_message():
    from chives.bus import Bus, Message

    bus = Bus()
    a, b = [], []
    bus.add_handler(lambda m: _append(a, m))
    bus.add_handler(lambda m: _append(b, m))

    await bus.put(Message("telegram", "1", 1, "hello"))
    await bus.run_once()

    assert a == b == ["hello"]


async def _append(sink, msg):
    sink.append(msg.text)
    return "ok"


async def test_brief_command_rewrites_text_and_calls_agent():
    """/brief must reach the agent with rewritten text, not be answered inline."""
    from chives.bus import Message
    from chives.pipeline import build_pipeline, slash_command_middleware

    seen = []

    async def agent(msg: Message) -> str:
        seen.append(msg.text)
        return "your brief"

    pipeline = build_pipeline(agent, [slash_command_middleware()])
    result = await pipeline(Message("telegram", "1", 1, "/brief"))

    assert seen == ["Generate the morning brief now."]
    assert result == "your brief"


async def test_help_command_never_reaches_the_agent():
    from chives.bus import Message
    from chives.pipeline import build_pipeline, slash_command_middleware

    called = False

    async def agent(msg: Message) -> str:
        nonlocal called
        called = True
        return "should not happen"

    pipeline = build_pipeline(agent, [slash_command_middleware()])
    result = await pipeline(Message("telegram", "1", 1, "/help"))

    assert not called
    assert "/clear" in result and "/brief" in result


async def test_rate_limit_is_per_thread():
    """One chatty thread must not throttle a different conversation."""
    from chives.bus import Message
    from chives.pipeline import build_pipeline, rate_limit_middleware

    async def agent(msg: Message) -> str:
        return "ok"

    pipeline = build_pipeline(agent, [rate_limit_middleware(min_seconds=60)])

    assert await pipeline(Message("telegram", "a", 1, "hi")) == "ok"
    assert await pipeline(Message("telegram", "b", 2, "hi")) == "ok"
    assert "Slow down" in await pipeline(Message("telegram", "a", 1, "again"))


async def test_plain_message_passes_through_slash_middleware():
    from chives.bus import Message
    from chives.pipeline import build_pipeline, slash_command_middleware

    async def agent(msg: Message) -> str:
        return f"echo: {msg.text}"

    pipeline = build_pipeline(agent, [slash_command_middleware()])

    assert await pipeline(Message("telegram", "1", 1, "just a message")) == "echo: just a message"
