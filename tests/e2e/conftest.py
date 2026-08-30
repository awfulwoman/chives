"""Fixtures for end-to-end tests against a live OpenAI-compatible endpoint.

These tests talk to a real LLM. They are deselected by default (see the
``live`` marker in pyproject.toml) and run with::

    uv run pytest -m live

Override the target with environment variables::

    E2E_LLM_BASE_URL=http://192.168.1.99:11434/v1
    E2E_LLM_MODEL=gemma4:31b-cloud
    E2E_LLM_TIMEOUT=180
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import openai
import pytest

import chives.tools.memory as memory_tools
import chives.tools.schedule as sched_tools
from chives.agent import Agent
from chives.config import Config, LLMConfig, TelegramConfig
from chives.store import Store
from chives.tools.registry import clear_registry, register_raw

BASE_URL = os.environ.get("E2E_LLM_BASE_URL", "http://192.168.1.99:11434/v1")
MODEL = os.environ.get("E2E_LLM_MODEL", "gemma4:31b-cloud")
TIMEOUT = float(os.environ.get("E2E_LLM_TIMEOUT", "180"))

REPO_ROOT = Path(__file__).resolve().parents[2]
THREAD_ID = "888261035"


@pytest.fixture(scope="session")
def live_endpoint() -> str:
    """Skip the whole live suite unless the endpoint is up and serving MODEL."""
    try:
        resp = httpx.get(f"{BASE_URL}/models", timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        pytest.skip(f"live LLM endpoint {BASE_URL} unreachable: {exc}")

    served = {m["id"] for m in resp.json().get("data", [])}
    if MODEL not in served:
        pytest.skip(f"model {MODEL!r} not served by {BASE_URL}; available: {sorted(served)}")
    return BASE_URL


class ToolRecorder:
    """Stand-in for the MCP gateway.

    Registers the tool names PROTOCOLS.md tells the model to use, returns
    fixed payloads, and records every invocation so tests can assert on what
    the model actually decided to call.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def called(self, name: str) -> bool:
        return name in self.names

    def args_for(self, name: str) -> dict:
        for called_name, args in self.calls:
            if called_name == name:
                return args
        raise AssertionError(f"{name} was never called; got {self.names}")

    def register(self, name: str, description: str, params: dict, result: str) -> None:
        async def caller(**kwargs) -> str:
            self.calls.append((name, kwargs))
            return result

        caller.__name__ = name
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {k: {"type": "string"} for k in params},
                    "required": list(params),
                },
            },
        }
        register_raw(name, schema, caller)


# Distinctive sentinels — if these show up in a reply, the model genuinely
# routed the tool result into its answer rather than inventing content.
CALENDAR_SENTINEL = "Zorblatt Quarterly Sync"
REMINDER_SENTINEL = "descale the kettle"
EMAIL_SENTINEL = "Wobblefish Invoice 88213"


@pytest.fixture
def gateway(tmp_path) -> ToolRecorder:
    """Fake gateway tool surface, mirroring the real gateway's tool names."""
    rec = ToolRecorder()
    rec.register(
        "list_calendar_events",
        "List calendar events for a period (today, tomorrow, week).",
        ["period"],
        f'[{{"title": "{CALENDAR_SENTINEL}", "start": "2026-08-25T14:00:00+00:00", "location": "Room 3"}}]',
    )
    rec.register(
        "list_reminders",
        "List the user's reminders, optionally filtered to overdue ones.",
        ["filter"],
        f'[{{"title": "{REMINDER_SENTINEL}", "due": "2026-08-24T09:00:00+00:00", "overdue": true}}]',
    )
    rec.register(
        "fetch_unread_emails",
        "Fetch unread emails from the user's inbox.",
        ["limit"],
        f'[{{"subject": "{EMAIL_SENTINEL}", "from": "billing@wobblefish.example", "needs_action": true}}]',
    )
    rec.register(
        "lookup_contact",
        "Look up a contact by name.",
        ["name"],
        '[{"name": "Annisa", "phone": "+44 7700 900123"}]',
    )
    return rec


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "state"))


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(
        llm=LLMConfig(base_url=BASE_URL, model=MODEL, api_key="ollama"),
        telegram=TelegramConfig(bot_token="", allowed_chat_ids=[int(THREAD_ID)]),
        state_path=str(tmp_path / "state"),
        profile_path=str(REPO_ROOT / "profile"),
    )


@pytest.fixture
def agent(live_endpoint, config, store, gateway) -> Agent:
    """Agent wired to the live endpoint, the real profile, and fake gateway tools.

    ``gateway`` is requested (not just used) so its tools are registered before
    the agent reads the schema list.
    """
    memory_tools.init(store)
    sched_tools.init(store, connector="telegram", thread_id=THREAD_ID)

    agent = Agent(config, store)
    # The Agent builds its own client with a 5s connect timeout; cloud-backed
    # models need a far longer read budget than that default allows.
    agent.client = openai.AsyncOpenAI(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        timeout=TIMEOUT,
        max_retries=1,
    )
    return agent


@pytest.fixture(autouse=True)
def reset_registry():
    clear_registry()
    yield
    clear_registry()
