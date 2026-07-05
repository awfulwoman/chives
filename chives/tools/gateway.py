from __future__ import annotations
import json
import logging
import httpx
from chives.tools.registry import register_raw

log = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def _parse_sse(resp: httpx.Response) -> dict:
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise ValueError(f"No data line in SSE response: {resp.text!r}")


def _make_caller(tool_name: str, url: str):
    async def caller(**kwargs) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
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


async def _register_from(url: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
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
        register_raw(name, schema, _make_caller(name, url))
    log.info("Registered %d tools from %s", len(tools), url)


async def init(urls: list[str]) -> None:
    """Discover tools from each MCP server URL and register them."""
    for url in urls:
        try:
            await _register_from(url)
        except Exception as exc:
            log.warning("Could not reach MCP server %s: %s", url, exc)
