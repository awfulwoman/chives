#!/usr/bin/env python
"""Post-deploy smoke check for chives.

Verifies the three external dependencies the agent cannot start without, plus
its own HTTP surface. Reads the same .env the service does.

    uv run python scripts/smoke.py
    uv run python scripts/smoke.py --skip-self   # before the service is up

Exit code 0 = all good, 1 = at least one check failed.
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

from chives.config import Config

OK = "\033[32m✓\033[0m"
BAD = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class Results:
    def __init__(self) -> None:
        self.failed = False

    def ok(self, label: str, detail: str = "") -> None:
        print(f"  {OK} {label}" + (f" — {detail}" if detail else ""))

    def warn(self, label: str, detail: str) -> None:
        print(f"  {WARN} {label} — {detail}")

    def fail(self, label: str, detail: str) -> None:
        print(f"  {BAD} {label} — {detail}")
        self.failed = True


def check_llm(cfg: Config, r: Results) -> None:
    print(f"\nLLM  {cfg.llm.base_url}")
    try:
        resp = httpx.get(f"{cfg.llm.base_url}/models", timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        r.fail("reachable", str(exc))
        return
    r.ok("reachable")

    served = sorted(m["id"] for m in resp.json().get("data", []))
    if cfg.llm.model in served:
        r.ok(f"serving {cfg.llm.model}")
    else:
        r.fail(f"model {cfg.llm.model!r} not served", f"available: {', '.join(served) or 'none'}")
        return

    try:
        chat = httpx.post(
            f"{cfg.llm.base_url}/chat/completions",
            json={
                "model": cfg.llm.model,
                "messages": [{"role": "user", "content": "Reply with just: ok"}],
                "max_tokens": 16,
            },
            headers={"Authorization": f"Bearer {cfg.llm.api_key}"},
            timeout=120,
        )
        chat.raise_for_status()
        content = chat.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        r.fail("generation", str(exc))
        return
    r.ok("generation", repr((content or "").strip()[:40]))


def check_gateway(cfg: Config, r: Results) -> None:
    print(f"\nGateway  {cfg.gateway_url}")
    try:
        resp = httpx.post(
            cfg.gateway_url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers=MCP_HEADERS,
            timeout=10,
        )
    except Exception as exc:
        r.fail("reachable", str(exc))
        return
    r.ok("reachable")

    if resp.status_code == 401:
        r.fail(
            "authorised",
            "401 — gateway wants a bearer token but chives/tools/gateway.py sends none; "
            "startup will crash and the agent will have zero tools",
        )
        return
    if resp.status_code != 200:
        r.fail("tools/list", f"HTTP {resp.status_code}: {resp.text[:120]}")
        return

    try:
        tools = resp.json()["result"]["tools"]
    except Exception:
        r.fail("tools/list", f"unexpected body: {resp.text[:120]}")
        return

    if not tools:
        r.fail("tools/list", "gateway advertised zero tools")
        return
    r.ok(f"{len(tools)} tools", ", ".join(t["name"] for t in tools[:6]) + ("…" if len(tools) > 6 else ""))

    expected = {"list_calendar_events", "list_reminders", "fetch_unread_emails"}
    missing = expected - {t["name"] for t in tools}
    if missing:
        r.warn("core tools", f"missing: {', '.join(sorted(missing))} — PROTOCOLS.md references these")
    else:
        r.ok("core tools present")


def check_self(r: Results, port: int = 8080) -> None:
    print(f"\nOpen WebUI surface  http://127.0.0.1:{port}")
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        r.fail("reachable", f"{exc} — is the launchd service running?")
        return
    ids = [m["id"] for m in resp.json().get("data", [])]
    r.ok("/v1/models", ", ".join(ids))


def check_profile(cfg: Config, r: Results) -> None:
    from pathlib import Path

    print(f"\nProfile  {cfg.profile_path}")
    for fname in ("PERSONALITY.md", "USER.md", "PROTOCOLS.md"):
        path = Path(cfg.profile_path) / fname
        if path.exists() and path.read_text().strip():
            r.ok(fname)
        elif path.exists():
            r.warn(fname, "empty")
        else:
            r.warn(fname, "missing — silently dropped from the system prompt")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-self", action="store_true", help="don't check the local HTTP surface")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    cfg = Config()
    r = Results()

    check_llm(cfg, r)
    check_gateway(cfg, r)
    check_profile(cfg, r)
    if not args.skip_self:
        check_self(r, args.port)

    print()
    if r.failed:
        print(f"{BAD} smoke check FAILED")
        return 1
    print(f"{OK} smoke check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
