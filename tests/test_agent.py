import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from chives.config import Config
from chives.store import Store
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def config(tmp_path):
    c = Config()
    c.state_path = str(tmp_path / "state")
    c.profile_path = str(tmp_path / "profile")
    (tmp_path / "profile").mkdir()
    return c


@pytest.fixture
def store(config):
    return Store(config.state_path)


def _mock_openai_response(content: str):
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = content
    choice.message.tool_calls = None
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _mock_tool_response(tool_name: str, tool_id: str, args: dict, then_content: str):
    """First response triggers a tool call; second returns final content."""
    tool_call = MagicMock()
    tool_call.id = tool_id
    tool_call.function.name = tool_name
    tool_call.function.arguments = json.dumps(args)

    first = MagicMock()
    first.finish_reason = "tool_calls"
    first.message.tool_calls = [tool_call]
    first.message.content = None

    second = MagicMock()
    second.finish_reason = "stop"
    second.message.content = then_content
    second.message.tool_calls = None

    resp1, resp2 = MagicMock(), MagicMock()
    resp1.choices = [first]
    resp2.choices = [second]
    return resp1, resp2


async def test_simple_response(config, store):
    from chives.agent import Agent

    mock_create = AsyncMock(return_value=_mock_openai_response("Hello!"))
    with patch("openai.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = mock_create
        agent = Agent(config, store)
        result = await agent.run("hi", "telegram", "123")

    assert result == "Hello!"


async def test_turn_stored_in_db(config, store):
    from chives.agent import Agent

    mock_create = AsyncMock(return_value=_mock_openai_response("Got it."))
    with patch("openai.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = mock_create
        agent = Agent(config, store)
        await agent.run("test message", "telegram", "abc")

    turns = store.get_turns("telegram", "abc")
    assert any(t["role"] == "user" and t["content"] == "test message" for t in turns)
    assert any(t["role"] == "assistant" and t["content"] == "Got it." for t in turns)


async def test_tool_call_dispatched(config, store):
    from chives.tools.registry import tool
    from chives.agent import Agent

    @tool
    def ping(msg: str) -> str:
        """Ping."""
        return "pong"

    resp1, resp2 = _mock_tool_response("ping", "call_1", {"msg": "hi"}, "Done.")
    mock_create = AsyncMock(side_effect=[resp1, resp2])

    with patch("openai.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = mock_create
        agent = Agent(config, store)
        result = await agent.run("ping test", "telegram", "t1")

    assert result == "Done."
    assert mock_create.call_count == 2
