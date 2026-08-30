import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient


def _make_app(agent=None):
    from chives.connectors.openwebui import create_app
    from chives.config import Config, LLMConfig

    store = MagicMock()
    store.stats.return_value = {
        "turn_total": 0,
        "turns_by_connector": {},
        "memory_count": 0,
        "pending_nudges": 0,
        "email_seen_count": 0,
        "last_turn": None,
    }
    config = MagicMock(spec=Config)
    config.llm = LLMConfig()
    return create_app(agent or AsyncMock(), store, config)


async def test_list_models():
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "chives-agent"


async def test_chat_completions_non_streaming():
    mock_agent = AsyncMock(return_value="Here is your answer.")
    app = _make_app(mock_agent)
    client = TestClient(app)

    payload = {
        "model": "chives",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "Here is your answer."


async def test_chat_completions_streaming():
    """Open WebUI streams by default — this is the path production actually uses."""
    from chives.connectors.openwebui import create_app

    mock_agent = AsyncMock(return_value="Streamed answer.")
    client = TestClient(create_app(mock_agent))

    resp = client.post(
        "/v1/chat/completions",
        json={"model": "chives", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    chunks = [
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ") and not line.endswith("[DONE]")
    ]
    assert chunks[0]["choices"][0]["delta"]["content"] == "Streamed answer."
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert resp.text.rstrip().endswith("data: [DONE]")
    assert len({c["id"] for c in chunks}) == 1, "all chunks must share one completion id"


async def test_streaming_uses_last_user_message():
    from chives.connectors.openwebui import create_app

    mock_agent = AsyncMock(return_value="ok")
    client = TestClient(create_app(mock_agent))

    client.post(
        "/v1/chat/completions",
        json={
            "model": "chives",
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "second"},
            ],
            "stream": True,
        },
    )

    mock_agent.assert_awaited_once_with("second", "openwebui", "openwebui")


async def test_ollama_list_models():
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["models"]) == 1
    assert data["models"][0]["name"] == "chives:latest"


async def test_ollama_chat_non_streaming():
    app = _make_app(AsyncMock(return_value="All lights off."))
    client = TestClient(app)
    payload = {
        "model": "chives:latest",
        "messages": [{"role": "user", "content": "turn off lights"}],
        "stream": False,
    }
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"]["role"] == "assistant"
    assert data["message"]["content"] == "All lights off."
    assert data["done"] is True


async def test_ollama_chat_streaming():
    app = _make_app(AsyncMock(return_value="Done."))
    client = TestClient(app)
    payload = {
        "model": "chives:latest",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    }
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    lines = [l for l in resp.text.strip().splitlines() if l]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["message"]["content"] == "Done."
    assert first["done"] is False
    last = json.loads(lines[1])
    assert last["done"] is True
    assert last["done_reason"] == "stop"


async def test_ollama_pull():
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/api/pull", json={"model": "chives:latest", "stream": False})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
