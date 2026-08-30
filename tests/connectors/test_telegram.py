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


async def test_send_forwards_to_bot():
    from chives.connectors.telegram import TelegramConnector

    config = Config()
    config.telegram = TelegramConfig(bot_token="tok", allowed_chat_ids=[42])

    with patch("telegram.ext.Application.builder") as mock_builder:
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        mock_builder.return_value.token.return_value.build.return_value = mock_app

        conn = TelegramConnector(config, Bus())
        await conn.send(42, "hello there")

    mock_app.bot.send_message.assert_awaited_once_with(chat_id=42, text="hello there")


async def test_handlers_registered_for_text_and_commands():
    """Slash commands must reach the bus too — the pipeline handles them, not PTB."""
    from chives.connectors.telegram import TelegramConnector

    config = Config()
    config.telegram = TelegramConfig(bot_token="tok", allowed_chat_ids=[42])

    with patch("telegram.ext.Application.builder") as mock_builder:
        mock_app = MagicMock()
        mock_builder.return_value.token.return_value.build.return_value = mock_app

        TelegramConnector(config, Bus())

    assert mock_app.add_handler.call_count == 2
