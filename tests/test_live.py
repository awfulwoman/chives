"""
Live integration tests for the chives instance.

Run against the real server to check for availability, response times, and correctness.

    uv run pytest tests/test_live.py -v -s

Override the base URL:

    CHIVES_LIVE_URL=http://localhost:8000 uv run pytest tests/test_live.py -v -s
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
import pytest

BASE_URL = os.environ.get("CHIVES_LIVE_URL", "https://chives.ewwww.eu").rstrip("/")

# Generous timeout for a local LLM — the real concern is anything beyond this.
RESPONSE_TIMEOUT = 60.0
# Time-to-first-token threshold for streaming responses.
TTFT_THRESHOLD = 30.0


def _server_reachable() -> bool:
    try:
        httpx.get(BASE_URL, timeout=3.0)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _server_reachable(), reason=f"{BASE_URL} is unreachable from here"
)


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=RESPONSE_TIMEOUT) as c:
        yield c


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


def test_status_page(client):
    """GET / should return the HTML status page quickly."""
    t0 = time.monotonic()
    resp = client.get("/")
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200, resp.text
    assert "text/html" in resp.headers["content-type"]
    assert "running" in resp.text
    assert elapsed < 5.0, f"Status page took {elapsed:.1f}s — server may be slow"


def test_models_endpoint(client):
    """GET /v1/models should return the OpenAI model list immediately."""
    t0 = time.monotonic()
    resp = client.get("/v1/models")
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert any(m["id"] == "chives-agent" for m in data["data"])
    assert elapsed < 3.0, f"/v1/models took {elapsed:.1f}s"


def test_ollama_tags(client):
    """GET /api/tags should return the Ollama model list immediately."""
    t0 = time.monotonic()
    resp = client.get("/api/tags")
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["models"]) >= 1
    assert elapsed < 3.0, f"/api/tags took {elapsed:.1f}s"


# ---------------------------------------------------------------------------
# Chat completions — non-streaming
# ---------------------------------------------------------------------------


def test_simple_chat_nonstream(client):
    """POST /v1/chat/completions with a trivial prompt should return within the timeout."""
    payload = {
        "model": "chives",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }
    t0 = time.monotonic()
    resp = client.post("/v1/chat/completions", json=payload)
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200, resp.text
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    assert content.strip(), "Response content is empty"
    assert data["choices"][0]["finish_reason"] == "stop"
    print(f"\n  [{elapsed:.1f}s] response: {content[:120]!r}")


def test_chat_response_is_coherent(client):
    """The agent should respond conversationally, not as a JSON structure."""
    payload = {
        "model": "chives",
        "messages": [{"role": "user", "content": "What is your name?"}],
        "stream": False,
    }
    resp = client.post("/v1/chat/completions", json=payload)

    assert resp.status_code == 200
    content = resp.json()["choices"][0]["message"]["content"]
    print(f"\n  response: {content!r}")
    # The model should produce prose, not a JSON classification blob.
    assert '{"tags":' not in content, (
        f"LLM is outputting tag JSON instead of conversational text: {content!r}"
    )
    # Should be a non-trivial sentence, not a one-word or empty reply.
    assert len(content.split()) > 5, f"Response suspiciously short: {content!r}"


def test_empty_message_does_not_crash(client):
    """An empty user message should return 200, not a 500."""
    payload = {
        "model": "chives",
        "messages": [{"role": "user", "content": ""}],
        "stream": False,
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Chat completions — streaming (SSE)
# ---------------------------------------------------------------------------


def test_streaming_sse_format():
    """POST /v1/chat/completions stream=True should return valid SSE chunks."""
    payload = {
        "model": "chives",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    }
    chunks = []
    t0 = time.monotonic()
    first_chunk_at = None

    with httpx.Client(base_url=BASE_URL, timeout=RESPONSE_TIMEOUT) as client:
        with client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:"):].strip()
                if raw == "[DONE]":
                    break
                if first_chunk_at is None:
                    first_chunk_at = time.monotonic()
                chunks.append(json.loads(raw))

    ttft = (first_chunk_at or time.monotonic()) - t0
    total = time.monotonic() - t0

    assert chunks, "No SSE data chunks received"
    # Last content chunk should have finish_reason == None; the stop chunk has it set.
    stop_chunks = [c for c in chunks if c["choices"][0].get("finish_reason") == "stop"]
    assert stop_chunks, "No stop chunk received"
    assert ttft < TTFT_THRESHOLD, f"Time-to-first-token was {ttft:.1f}s"
    print(f"\n  TTFT={ttft:.1f}s  total={total:.1f}s  chunks={len(chunks)}")


# ---------------------------------------------------------------------------
# Ollama-compat endpoints (used by Home Assistant)
# ---------------------------------------------------------------------------


def test_ollama_chat_nonstream(client):
    """POST /api/chat non-streaming should return a valid Ollama response."""
    payload = {
        "model": "chives:latest",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }
    t0 = time.monotonic()
    resp = client.post("/api/chat", json=payload)
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["message"]["role"] == "assistant"
    assert data["message"]["content"].strip()
    assert data["done"] is True
    print(f"\n  [{elapsed:.1f}s] ollama response: {data['message']['content'][:80]!r}")


# ---------------------------------------------------------------------------
# Concurrency — ensure requests don't block each other
# ---------------------------------------------------------------------------


async def _chat(url: str, msg: str) -> tuple[str, float]:
    payload = {
        "model": "chives",
        "messages": [{"role": "user", "content": msg}],
        "stream": False,
    }
    async with httpx.AsyncClient(base_url=url, timeout=RESPONSE_TIMEOUT) as ac:
        t0 = time.monotonic()
        resp = await ac.post("/v1/chat/completions", json=payload)
        elapsed = time.monotonic() - t0
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content, elapsed


async def test_concurrent_requests():
    """Three simultaneous requests should all complete within the timeout."""
    messages = ["hi", "what day is it?", "tell me a very short joke"]
    results = await asyncio.gather(*[_chat(BASE_URL, m) for m in messages])

    for i, (content, elapsed) in enumerate(results):
        print(f"\n  [{elapsed:.1f}s] msg={messages[i]!r}  reply={content[:60]!r}")
        assert content.strip(), f"Empty response for message {i}"
        assert elapsed < RESPONSE_TIMEOUT, f"Request {i} timed out ({elapsed:.1f}s)"
