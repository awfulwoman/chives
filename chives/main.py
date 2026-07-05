from __future__ import annotations
import asyncio
import logging
import yaml
import uvicorn
from pathlib import Path

from chives.config import Config
from chives.store import Store
from chives.bus import Bus
from chives.agent import Agent
from chives.pipeline import build_pipeline, rate_limit_middleware, slash_command_middleware
from chives.scheduler import Scheduler
from chives.connectors.telegram import TelegramConnector
from chives.connectors.openwebui import create_app

import chives.tools.memory as memory_tools
import chives.tools.gateway as gateway_tools
import chives.tools.schedule as sched_tools


async def main() -> None:
    config = Config()

    store = Store(config.state_path)

    memory_tools.init(store)

    mcp_servers: list[dict] = []
    if config.mcp_config_path:
        p = Path(config.mcp_config_path)
        if p.exists():
            with p.open() as f:
                mcp_config = yaml.safe_load(f)
            mcp_servers = mcp_config.get("mcp_servers", [])
        else:
            logging.getLogger(__name__).warning("MCP config not found: %s", config.mcp_config_path)
    await gateway_tools.init(mcp_servers)

    agent = Agent(config, store)
    bus = Bus()
    telegram = TelegramConnector(config, bus)

    # Schedule tool needs connector info for routing nudge replies
    default_thread = str(config.telegram.allowed_chat_ids[0]) if config.telegram.allowed_chat_ids else "0"
    sched_tools.init(store, connector="telegram", thread_id=default_thread)

    # Build pipeline: rate limit → slash commands → agent
    pipeline = build_pipeline(
        lambda msg: agent.run(msg.text, msg.connector, msg.thread_id),
        [rate_limit_middleware(min_seconds=0.5), slash_command_middleware()],
    )

    async def handle_message(msg):
        try:
            response = await pipeline(msg)
            if response:
                await telegram.send(msg.chat_id, response)
        except Exception as exc:
            logging.getLogger(__name__).exception("Error handling message: %s", exc)

    bus.add_handler(handle_message)

    scheduler = Scheduler(config, agent.run, store, telegram)
    scheduler.start()

    openwebui_app = create_app(agent.run, store, config)
    server = uvicorn.Server(
        uvicorn.Config(openwebui_app, host="0.0.0.0", port=8080, log_level="warning")
    )

    async with asyncio.TaskGroup() as tg:
        tg.create_task(bus.run())
        tg.create_task(telegram.run())
        tg.create_task(server.serve())


if __name__ == "__main__":
    asyncio.run(main())
