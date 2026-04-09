from __future__ import annotations
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from chives.bus import Bus, Message
from chives.config import Config


class TelegramConnector:
    def __init__(self, config: Config, bus: Bus) -> None:
        self.config = config
        self.bus = bus
        self.app = Application.builder().token(config.telegram.bot_token).build()
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        self.app.add_handler(
            MessageHandler(filters.COMMAND, self._on_message)
        )

    async def send(self, chat_id: int, text: str) -> None:
        await self.app.bot.send_message(chat_id=chat_id, text=text)

    async def _on_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat_id = update.effective_chat.id
        if chat_id not in self.config.telegram.allowed_chat_ids:
            return
        msg = Message(
            connector="telegram",
            thread_id=str(chat_id),
            chat_id=chat_id,
            text=update.message.text or "",
        )
        await self.bus.put(msg)

    async def run(self) -> None:
        async with self.app:
            await self.app.start()
            await self.app.updater.start_polling()
            await asyncio.Event().wait()  # run until cancelled
