"""Live-model behaviour tests.

These assert that the harnessed model, given the real profile/ prompt and the
real tool schemas, actually behaves the way PROTOCOLS.md requires. A failure
here means the model (or the prompt) regressed — not that the plumbing broke.
"""
from __future__ import annotations

import time

import httpx
import pytest

from tests.e2e.conftest import (
    BASE_URL,
    CALENDAR_SENTINEL,
    EMAIL_SENTINEL,
    MODEL,
    REMINDER_SENTINEL,
    THREAD_ID,
)

pytestmark = pytest.mark.live


def _scheduled_nudges(store) -> list[str]:
    """Every unfired nudge, regardless of whether it is due yet."""
    with store._conn() as conn:
        return [r["description"] for r in conn.execute(
            "SELECT description FROM nudges WHERE fired=0"
        ).fetchall()]


def test_endpoint_serves_expected_model(live_endpoint):
    """Smoke: the endpoint is up and serving the model chives is configured for."""
    resp = httpx.get(f"{BASE_URL}/models", timeout=10)
    assert resp.status_code == 200
    assert MODEL in {m["id"] for m in resp.json()["data"]}


async def test_simple_response_is_coherent(agent):
    """A plain question gets a plain, non-empty answer with no leaked scaffolding."""
    reply = await agent.run("Say hello in one short sentence.", "telegram", THREAD_ID)

    assert reply.strip(), "model returned an empty response"
    assert len(reply) < 500, f"expected a short answer, got {len(reply)} chars"
    for leak in ("<tool_call>", "<|", "```json", "function_call"):
        assert leak not in reply, f"raw scaffolding {leak!r} leaked into the reply: {reply!r}"


async def test_calendar_question_triggers_tool_call(agent, gateway):
    """PROTOCOLS.md: calendar questions must always hit list_calendar_events."""
    reply = await agent.run("What's on my calendar today?", "telegram", THREAD_ID)

    assert gateway.called("list_calendar_events"), (
        f"model answered a calendar question without calling the tool. "
        f"Tools called: {gateway.names}. Reply: {reply!r}"
    )
    assert CALENDAR_SENTINEL.split()[0] in reply, (
        f"tool returned {CALENDAR_SENTINEL!r} but the reply didn't use it: {reply!r}"
    )


async def test_reminder_question_triggers_tool_call(agent, gateway):
    reply = await agent.run("What reminders am I behind on?", "telegram", THREAD_ID)

    assert gateway.called("list_reminders"), (
        f"expected list_reminders, got {gateway.names}. Reply: {reply!r}"
    )
    assert REMINDER_SENTINEL.split()[0] in reply.lower() or "kettle" in reply.lower(), (
        f"reply ignored the tool result: {reply!r}"
    )


async def test_email_question_triggers_tool_call(agent, gateway):
    reply = await agent.run("Any unread email I need to deal with?", "telegram", THREAD_ID)

    assert gateway.called("fetch_unread_emails"), (
        f"expected fetch_unread_emails, got {gateway.names}. Reply: {reply!r}"
    )
    assert "wobblefish" in reply.lower(), f"reply ignored the tool result: {reply!r}"


async def test_shared_fact_is_actually_stored(agent, store):
    """PROTOCOLS.md: never claim to remember something without calling store_fact."""
    reply = await agent.run(
        "Remember that my sister's name is Bramblewick and her birthday is 3rd March.",
        "telegram",
        THREAD_ID,
    )

    facts = [m["fact"] for m in store.get_all_memories()]
    assert facts, (
        f"model claimed to remember but store_fact was never called. Reply: {reply!r}"
    )
    assert any("bramblewick" in f.lower() for f in facts), (
        f"store_fact was called but lost the detail: {facts}"
    )


async def test_commitment_schedules_a_nudge(agent, store):
    """PROTOCOLS.md: 'remind me to X' must schedule a nudge, not just acknowledge."""
    reply = await agent.run(
        "Remind me to call the dentist tomorrow at 3pm.", "telegram", THREAD_ID
    )

    # Not get_pending_nudges() — that means "due to fire right now". A nudge for
    # tomorrow is correctly scheduled but not yet pending.
    nudges = _scheduled_nudges(store)
    assert nudges, f"no nudge scheduled. Reply: {reply!r}"
    assert any("dentist" in d.lower() for d in nudges), (
        f"nudge scheduled but lost the subject: {nudges}"
    )


async def test_model_never_calls_unknown_tools(agent, gateway):
    """Hallucinated tool names dispatch to the unknown-tool error path silently."""
    from chives.tools.registry import get_tools_schema

    registered = {s["function"]["name"] for s in get_tools_schema()}
    await agent.run("Sort out my whole day for me — calendar, reminders, email.", "telegram", THREAD_ID)

    unknown = [n for n in gateway.names if n not in registered]
    assert not unknown, f"model invented tool names: {unknown}"


async def test_multi_tool_request_chains_correctly(agent, gateway):
    """A morning-brief style prompt should pull from more than one source."""
    reply = await agent.run(
        "Give me a quick brief: today's events and anything overdue.", "telegram", THREAD_ID
    )

    assert len(set(gateway.names)) >= 2, (
        f"expected at least two distinct tools, got {gateway.names}. Reply: {reply!r}"
    )
    assert reply.strip()


async def test_response_latency_within_budget(agent):
    """Guards against a model swap that makes the assistant unusably slow."""
    start = time.monotonic()
    await agent.run("Reply with just the word: ok", "telegram", THREAD_ID)
    elapsed = time.monotonic() - start

    assert elapsed < 60, f"simple turn took {elapsed:.1f}s — too slow for an interactive assistant"
