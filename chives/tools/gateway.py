from __future__ import annotations
import json
import httpx
from chives.tools.registry import register_raw

_GATEWAY_URL = "http://127.0.0.1:4000/mcp"
_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def _parse_sse(resp: httpx.Response) -> dict:
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise ValueError(f"No data line in SSE response: {resp.text!r}")


def _make_caller(tool_name: str):
    async def caller(**kwargs) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _GATEWAY_URL,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": tool_name, "arguments": kwargs}},
                headers=_HEADERS,
            )
            resp.raise_for_status()
            data = _parse_sse(resp)
            if "error" in data:
                return data["error"].get("message", str(data["error"]))
            content = data["result"]["content"]
            return content[0]["text"] if content else ""
    caller.__name__ = tool_name
    return caller


async def init(gateway_url: str = _GATEWAY_URL) -> None:
    """Discover all gateway tools and register them in the chives tool registry."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            gateway_url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers=_HEADERS,
        )
        resp.raise_for_status()
        tools = _parse_sse(resp)["result"]["tools"]

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
        register_raw(name, schema, _make_caller(name))
