#!/usr/bin/env python
"""Interactive CLI to chat directly with the agent for debugging."""
import asyncio
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

from chives.config import Config
from chives.store import Store
from chives.agent import Agent
from chives.tools.registry import clear_registry
import chives.tools.calendar  # noqa: F401
import chives.tools.reminders  # noqa: F401
import chives.tools.contacts  # noqa: F401
import chives.tools.memory as memory_tools
import chives.tools.email as email_tools
import chives.tools.schedule as sched_tools


async def main() -> None:
    clear_registry()
    config = Config()
    store = Store(config.state_path)
    memory_tools.init(store)
    email_tools.init(config.imap)
    sched_tools.init(store, connector="cli", thread_id="cli")

    agent = Agent(config, store)
    print(f"Chatting with {config.llm.model} — Ctrl-C or blank line to quit\n")

    while True:
        try:
            msg = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            break
        response = await agent.run(msg, "cli", "cli")
        print(f"chives: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
