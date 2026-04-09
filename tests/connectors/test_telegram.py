import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from chives.config import Config, TelegramConfig
from chives.bus import Bus, Message


async def test_message_from_allowed_chat_goes_to_bus():
    config = Config()
    config.telegram = TelegramConfig(bot_token="tok", allowed_chat_ids=[42])
    bus = Bus()
    received = []

    async def capture(msg: Message) -> str:
        received.append(msg)
        return "ok"

    bus.add_handler(capture)

    with patch("telegram.ext.Application.builder") as mock_builder:
        mock_app = MagicMock()
        mock_builder.return_value.token.return_value.build.return_value = mock_app

        from chives.connectors.telegram import TelegramConnector
        connector = TelegramConnector(config, bus)

        update = MagicMock()
        update.effective_chat.id = 42
        update.message.text = "hello bot"

        await connector._on_message(update, MagicMock())
        await bus.run_once()

    assert len(received) == 1
    assert received[0].text == "hello bot"


async def test_message_from_unknown_chat_ignored():
    config = Config()
    config.telegram = TelegramConfig(bot_token="tok", allowed_chat_ids=[42])
    bus = Bus()
    received = []
    bus.add_handler(lambda m: received.append(m))

    with patch("telegram.ext.Application.builder") as mock_builder:
        mock_app = MagicMock()
        mock_builder.return_value.token.return_value.build.return_value = mock_app

        from chives.connectors.telegram import TelegramConnector
        connector = TelegramConnector(config, bus)

        update = MagicMock()
        update.effective_chat.id = 99  # not in allowed list
        update.message.text = "intruder"

        await connector._on_message(update, MagicMock())

    assert len(received) == 0
