#!/usr/bin/env python
"""Interactive CLI to chat directly with the agent for debugging.

Wires up the same stack main.py does, minus the connectors and scheduler.
Config comes from .env (via pydantic-settings); override the LLM per-run:

    uv run python scripts/chat.py
    uv run python scripts/chat.py --base-url http://192.168.1.99:11434/v1 --model gemma4:31b-cloud
    uv run python scripts/chat.py --no-tools    # skip the gateway entirely
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

from chives.agent import Agent
from chives.config import Config
from chives.store import Store
from chives.tools.registry import get_tools_schema

import chives.tools.gateway as gateway_tools
import chives.tools.memory as memory_tools
import chives.tools.schedule as sched_tools

THREAD = "cli"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", help="override CHIVES_LLM__BASE_URL")
    p.add_argument("--model", help="override CHIVES_LLM__MODEL")
    p.add_argument("--no-tools", action="store_true", help="skip gateway tool discovery")
    p.add_argument("--debug", action="store_true", help="log every LLM round trip")
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    if args.debug:
        logging.getLogger("chives").setLevel(logging.DEBUG)

    config = Config()
    if args.base_url:
        config.llm.base_url = args.base_url
    if args.model:
        config.llm.model = args.model

    store = Store(config.state_path)
    memory_tools.init(store)
    sched_tools.init(store, connector="cli", thread_id=THREAD)

    if not args.no_tools:
        # A gateway outage shouldn't make the debug CLI unusable — that's often
        # exactly what you're here to debug.
        try:
            await gateway_tools.init(config.gateway_url)
        except Exception as exc:
            print(f"! gateway unavailable ({exc}) — continuing with local tools only\n", file=sys.stderr)

    agent = Agent(config, store)
    print(f"Chatting with {config.llm.model} at {config.llm.base_url}")
    print(f"{len(get_tools_schema())} tools available — Ctrl-C or blank line to quit\n")

    while True:
        try:
            msg = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            break
        try:
            response = await agent.run(msg, "cli", THREAD)
        except Exception as exc:
            print(f"chives: [error] {exc}\n", file=sys.stderr)
            continue
        print(f"chives: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
