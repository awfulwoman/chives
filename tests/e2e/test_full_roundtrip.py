"""Full-stack round trip: Telegram update -> Bus -> pipeline -> Agent -> live LLM
-> tool dispatch -> SQLite -> outbound send.

This is the path main.py wires up and that nothing else in the suite covers.
Only the Telegram transport is faked; the LLM and the store are real.
"""
from __future__ import annotations

import pytest

from chives.bus import Bus, Message
from chives.pipeline import build_pipeline, rate_limit_middleware, slash_command_middleware
from tests.e2e.conftest import CALENDAR_SENTINEL, THREAD_ID

pytestmark = pytest.mark.live


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


@pytest.fixture
def stack(agent, store):
    """Assemble the same graph main.py builds, minus the network transports."""
    bus = Bus()
    telegram = FakeTelegram()

    pipeline = build_pipeline(
        lambda msg: agent.run(msg.text, msg.connector, msg.thread_id),
        [rate_limit_middleware(min_seconds=0.5), slash_command_middleware()],
    )

    async def handle_message(msg: Message) -> None:
        response = await pipeline(msg)
        if response:
            await telegram.send(msg.chat_id, response)

    bus.add_handler(handle_message)
    return bus, telegram, store


def _update(text: str) -> Message:
    return Message(
        connector="telegram", thread_id=THREAD_ID, chat_id=int(THREAD_ID), text=text
    )


async def test_message_round_trips_to_a_reply(stack):
    bus, telegram, store = stack

    await bus.put(_update("What's on my calendar today?"))
    await bus.run_once()

    assert telegram.sent, "nothing was sent back to the user"
    chat_id, reply = telegram.sent[0]
    assert chat_id == int(THREAD_ID)
    assert reply.strip()


async def test_round_trip_persists_both_turns(stack):
    bus, telegram, store = stack

    await bus.put(_update("What's on my calendar today?"))
    await bus.run_once()

    turns = store.get_turns("telegram", THREAD_ID)
    roles = [t["role"] for t in turns]
    assert "user" in roles and "assistant" in roles, f"turns not persisted: {roles}"
    assert turns[-1]["content"] == telegram.sent[0][1], "stored reply differs from sent reply"


async def test_round_trip_grounds_reply_in_tool_output(stack, gateway):
    bus, telegram, store = stack

    await bus.put(_update("What's on my calendar today?"))
    await bus.run_once()

    assert gateway.called("list_calendar_events")
    assert CALENDAR_SENTINEL.split()[0] in telegram.sent[0][1]


async def test_conversation_history_carries_across_turns(stack):
    """Second turn must see the first — this is what get_turns feeds the model."""
    bus, telegram, store = stack

    await bus.put(_update("My favourite colour is chartreuse. Just acknowledge."))
    await bus.run_once()

    await bus.put(_update("What did I just say my favourite colour was?"))
    await bus.run_once()

    assert len(telegram.sent) == 2
    assert "chartreuse" in telegram.sent[1][1].lower(), (
        f"model lost conversation history: {telegram.sent[1][1]!r}"
    )


async def test_threads_stay_isolated(stack, agent):
    """A fact told in one chat must not leak into another chat's history."""
    bus, telegram, store = stack
    other_thread = "999999999"

    await bus.put(_update("My favourite colour is chartreuse. Just acknowledge."))
    await bus.run_once()

    assert not store.get_turns("telegram", other_thread)
    assert store.get_turns("telegram", THREAD_ID)


async def test_slash_help_short_circuits_before_the_llm(stack, gateway):
    """/help is answered by middleware — the model must never be reached."""
    bus, telegram, store = stack

    await bus.put(_update("/help"))
    await bus.run_once()

    assert "Commands:" in telegram.sent[0][1]
    assert gateway.calls == []
    assert not store.get_turns("telegram", THREAD_ID)


async def test_rate_limit_rejects_a_burst(agent):
    """A second message inside the window is rejected without reaching the model.

    Uses its own pipeline: a live generation takes longer than the 0.5s window
    main.py uses, so the default window can never trip in an e2e test.
    """
    bus = Bus()
    telegram = FakeTelegram()
    pipeline = build_pipeline(
        lambda msg: agent.run(msg.text, msg.connector, msg.thread_id),
        [rate_limit_middleware(min_seconds=300), slash_command_middleware()],
    )

    async def handle(msg: Message) -> None:
        reply = await pipeline(msg)
        if reply:
            await telegram.send(msg.chat_id, reply)

    bus.add_handler(handle)

    await bus.put(_update("Say ok."))
    await bus.run_once()
    await bus.put(_update("Say ok again."))
    await bus.run_once()

    assert "Slow down" in telegram.sent[1][1]


async def test_brief_command_reaches_the_model(stack, gateway):
    """/brief rewrites the text and must still flow through to a real generation."""
    bus, telegram, store = stack

    await bus.put(_update("/brief"))
    await bus.run_once()

    assert telegram.sent[0][1].strip()
    assert gateway.calls, "morning brief produced no tool calls"
