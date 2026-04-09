from __future__ import annotations
import asyncio
import uvicorn
from chives.config import Config
from chives.store import Store
from chives.bus import Bus
from chives.agent import Agent
from chives.pipeline import build_pipeline, rate_limit_middleware, slash_command_middleware
from chives.scheduler import Scheduler
from chives.connectors.telegram import TelegramConnector
from chives.connectors.openwebui import create_app

# Tool modules — imported to register @tool functions
import chives.tools.calendar  # noqa: F401
import chives.tools.reminders  # noqa: F401
import chives.tools.contacts  # noqa: F401
import chives.tools.memory as memory_tools
import chives.tools.email as email_tools
import chives.tools.schedule as sched_tools


async def main() -> None:
    config = Config()

    store = Store(config.state_path)

    # Inject dependencies into tools that need them
    memory_tools.init(store)
    email_tools.init(config.imap)

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
        response = await pipeline(msg)
        if response:
            await telegram.send(msg.chat_id, response)

    bus.add_handler(handle_message)

    scheduler = Scheduler(config, agent.run, store, telegram)
    scheduler.start()

    openwebui_app = create_app(agent.run)
    server = uvicorn.Server(
        uvicorn.Config(openwebui_app, host="0.0.0.0", port=8080, log_level="warning")
    )

    async with asyncio.TaskGroup() as tg:
        tg.create_task(bus.run())
        tg.create_task(telegram.run())
        tg.create_task(server.serve())


if __name__ == "__main__":
    asyncio.run(main())
