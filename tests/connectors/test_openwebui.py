import json
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient


async def test_list_models():
    from chives.connectors.openwebui import create_app

    mock_agent = AsyncMock()
    app = create_app(mock_agent)
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "chives-agent"


async def test_chat_completions_non_streaming():
    from chives.connectors.openwebui import create_app

    mock_agent = AsyncMock(return_value="Here is your answer.")
    app = create_app(mock_agent)
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


async def test_ollama_list_models():
    from chives.connectors.openwebui import create_app

    app = create_app(AsyncMock())
    client = TestClient(app)
    resp = client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["models"]) == 1
    assert data["models"][0]["name"] == "chives:latest"


async def test_ollama_chat_non_streaming():
    from chives.connectors.openwebui import create_app

    app = create_app(AsyncMock(return_value="All lights off."))
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
    from chives.connectors.openwebui import create_app

    app = create_app(AsyncMock(return_value="Done."))
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
    from chives.connectors.openwebui import create_app

    app = create_app(AsyncMock())
    client = TestClient(app)
    resp = client.post("/api/pull", json={"model": "chives:latest", "stream": False})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
