"""Tests for the MCP gateway proxy — the module that supplies every live tool.

Uses httpx.MockTransport so no gateway needs to be running.
"""
from __future__ import annotations

import json

import httpx
import pytest

import chives.tools.gateway as gateway
from chives.tools.registry import clear_registry, dispatch_tool, get_tools_schema

GATEWAY_URL = "http://127.0.0.1:4000/mcp"

TOOLS_LIST = [
    {
        "name": "list_calendar_events",
        "description": "List calendar events for a period.",
        "inputSchema": {
            "type": "object",
            "properties": {"period": {"type": "string"}},
            "required": ["period"],
        },
    },
    {"name": "no_schema_tool"},
]


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


def _rpc_result(result: dict) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})


def _patch_transport(monkeypatch, handler):
    """Route every httpx.AsyncClient created by gateway.py through `handler`."""
    real_init = httpx.AsyncClient.__init__

    def init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)


async def test_init_discovers_and_registers_tools(monkeypatch):
    _patch_transport(monkeypatch, lambda req: _rpc_result({"tools": TOOLS_LIST}))

    await gateway.init(GATEWAY_URL)

    names = {s["function"]["name"] for s in get_tools_schema()}
    assert names == {"list_calendar_events", "no_schema_tool"}


async def test_init_translates_input_schema(monkeypatch):
    _patch_transport(monkeypatch, lambda req: _rpc_result({"tools": TOOLS_LIST}))

    await gateway.init(GATEWAY_URL)

    schemas = {s["function"]["name"]: s["function"] for s in get_tools_schema()}
    cal = schemas["list_calendar_events"]
    assert cal["description"] == "List calendar events for a period."
    assert cal["parameters"]["required"] == ["period"]
    assert cal["parameters"]["properties"]["period"]["type"] == "string"


async def test_init_defaults_missing_schema_and_description(monkeypatch):
    """A gateway tool advertising no inputSchema must still produce valid JSON schema."""
    _patch_transport(monkeypatch, lambda req: _rpc_result({"tools": TOOLS_LIST}))

    await gateway.init(GATEWAY_URL)

    bare = next(
        s["function"] for s in get_tools_schema() if s["function"]["name"] == "no_schema_tool"
    )
    assert bare["description"] == ""
    assert bare["parameters"] == {"type": "object", "properties": {}}


async def test_init_raises_when_gateway_unauthorised(monkeypatch):
    """The gateway requires a bearer token; a 401 must surface, not pass silently."""
    _patch_transport(
        monkeypatch,
        lambda req: httpx.Response(401, json={"error": {"message": "missing or invalid bearer token"}}),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await gateway.init(GATEWAY_URL)


async def test_init_raises_when_gateway_down(monkeypatch):
    def handler(req):
        raise httpx.ConnectError("connection refused", request=req)

    _patch_transport(monkeypatch, handler)

    with pytest.raises(httpx.ConnectError):
        await gateway.init(GATEWAY_URL)


async def test_registered_tool_dispatches_and_returns_text(monkeypatch):
    seen: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body)
        if body["method"] == "tools/list":
            return _rpc_result({"tools": TOOLS_LIST})
        return _rpc_result({"content": [{"type": "text", "text": "Standup at 10:00"}]})

    _patch_transport(monkeypatch, handler)
    await gateway.init(GATEWAY_URL)

    result = await dispatch_tool("list_calendar_events", '{"period": "today"}')

    assert result == "Standup at 10:00"
    call = seen[-1]
    assert call["method"] == "tools/call"
    assert call["params"] == {"name": "list_calendar_events", "arguments": {"period": "today"}}


async def test_tool_call_returns_error_message(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if body["method"] == "tools/list":
            return _rpc_result({"tools": TOOLS_LIST})
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "bad period"}},
        )

    _patch_transport(monkeypatch, handler)
    await gateway.init(GATEWAY_URL)

    result = await dispatch_tool("list_calendar_events", '{"period": "yesteryear"}')

    assert result == "bad period"


async def test_tool_call_error_without_message_stringifies(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if body["method"] == "tools/list":
            return _rpc_result({"tools": TOOLS_LIST})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -1}})

    _patch_transport(monkeypatch, handler)
    await gateway.init(GATEWAY_URL)

    result = await dispatch_tool("list_calendar_events", '{"period": "today"}')

    assert "-1" in result


async def test_tool_call_with_empty_content_returns_empty_string(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if body["method"] == "tools/list":
            return _rpc_result({"tools": TOOLS_LIST})
        return _rpc_result({"content": []})

    _patch_transport(monkeypatch, handler)
    await gateway.init(GATEWAY_URL)

    assert await dispatch_tool("list_calendar_events", '{"period": "today"}') == ""


async def test_tool_call_http_error_is_caught_by_dispatch(monkeypatch):
    """A gateway 500 mid-conversation must become a tool error, not kill the turn."""
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if body["method"] == "tools/list":
            return _rpc_result({"tools": TOOLS_LIST})
        return httpx.Response(500, text="boom")

    _patch_transport(monkeypatch, handler)
    await gateway.init(GATEWAY_URL)

    result = await dispatch_tool("list_calendar_events", '{"period": "today"}')

    assert "error" in json.loads(result)
