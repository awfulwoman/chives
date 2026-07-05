from __future__ import annotations
import json
import logging
import httpx
from chives.tools.registry import register_raw

log = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

# url -> mcp-session-id, populated during _register_from
_sessions: dict[str, str] = {}


def _parse_response(resp: httpx.Response) -> dict:
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise ValueError(f"No data line in SSE response: {resp.text!r}")
    return resp.json()


async def _init_session(client: httpx.AsyncClient, url: str, headers: dict) -> str | None:
    resp = await client.post(
        url,
        json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "chives", "version": "1.0"},
        }},
        headers=headers,
    )
    resp.raise_for_status()
    session_id = resp.headers.get("mcp-session-id")
    notif_headers = {**headers, **({"Mcp-Session-Id": session_id} if session_id else {})}
    await client.post(
        url,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=notif_headers,
    )
    return session_id


def _make_caller(tool_name: str, url: str, auth_key: str | None = None):
    base_headers = {**_HEADERS, **({"Authorization": f"Bearer {auth_key}"} if auth_key else {})}

    async def caller(**kwargs) -> str:
        session_id = _sessions.get(url)
        headers = {**base_headers, **({"Mcp-Session-Id": session_id} if session_id else {})}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": tool_name, "arguments": kwargs}},
                headers=headers,
            )
            resp.raise_for_status()
            data = _parse_response(resp)
            if "error" in data:
                return data["error"].get("message", str(data["error"]))
            content = data["result"]["content"]
            return content[0]["text"] if content else ""
    caller.__name__ = tool_name
    return caller


async def _register_from(url: str, auth_key: str | None = None) -> None:
    base_headers = {**_HEADERS, **({"Authorization": f"Bearer {auth_key}"} if auth_key else {})}
    async with httpx.AsyncClient(timeout=10) as client:
        session_id = await _init_session(client, url, base_headers)
        if session_id:
            _sessions[url] = session_id

        headers = {**base_headers, **({"Mcp-Session-Id": session_id} if session_id else {})}
        resp = await client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers=headers,
        )
        resp.raise_for_status()
        tools = _parse_response(resp)["result"]["tools"]

    for tool_def in tools:
        name = tool_def["name"]
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": tool_def.get("description", ""),
                "parameters": tool_def.get("inputSchema", {"type": "object", "properties": {}}),
            },
        }
        register_raw(name, schema, _make_caller(name, url, auth_key))
    log.info("Registered %d tools from %s", len(tools), url)


async def init(servers: list[dict]) -> None:
    """Discover tools from each MCP server and register them."""
    for server in servers:
        url = server["url"]
        auth_key = server.get("auth_key")
        try:
            await _register_from(url, auth_key)
        except Exception as exc:
            log.warning("Could not reach MCP server %s: %s", url, exc)
