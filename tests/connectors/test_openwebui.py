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
    assert data["data"][0]["id"] == "chives"


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
