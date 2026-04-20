# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Chives is a local-first ADHD executive assistant agent running on macOS. It accepts messages via Telegram and Open WebUI, runs an OpenAI-compatible tool-calling loop against a local Ollama LLM, and integrates with Apple Calendar, Reminders, Contacts (via PyObjC), and IMAP email. It runs as a macOS launchd service.

## Commands

```bash
# Install dependencies
uv sync

# Run in development
uv run python -m chives.main

# Run all tests
uv run pytest tests/

# Run a single test file
uv run pytest tests/test_agent.py

# Run a single test
uv run pytest tests/test_agent.py::test_name

# Install/uninstall as launchd service
./scripts/install_service.sh
./scripts/uninstall_service.sh
```

## Architecture

```
Message Sources: Telegram + Open WebUI
       ↓
  Message Bus (asyncio queue in bus.py)
       ↓
  Pipeline Middleware (rate limit, slash commands in pipeline.py)
       ↓
  Agent (tool-calling loop in agent.py)
       ├─→ LLM: openai.AsyncOpenAI → Ollama (configurable base_url)
       ├─→ Tool Dispatch: @tool-decorated functions in tools/
       └─→ Context: profile/ files + memory facts from SQLite
       ↓
  Store: SQLite (turns, memory, nudges, email_seen in store.py)
  Scheduler: APScheduler jobs (morning brief, nudges, event reminders in scheduler.py)
```

`main.py` wires everything together: `Config` → `Store` → `Agent` → `Bus` → connectors + `Scheduler`, then runs three concurrent async tasks (bus loop, Telegram polling, FastAPI server).

## Key Patterns

**Tool registry** — `@tool` in `tools/registry.py` auto-generates OpenAI JSON schema from the function signature and docstring. `dispatch_tool(name, args_json)` calls tools by name. This is the source of truth; no separate schema files. Tests must call `clear_registry()` between runs (use the `reset` fixture).

**Dependency injection** — Tools that need shared state expose an `init()` function (e.g. `memory_tools.init(store)`, `email_tools.init(config.imap)`). These are called in `main.py` at startup.

**Per-thread conversation isolation** — History, nudges, and memory are keyed on `(connector, thread_id)`. Telegram uses `str(chat_id)`; Open WebUI uses `"openwebui"`.

**Context assembly** — `context.py` builds the system prompt by joining `profile/PERSONALITY.md`, `profile/USER.md`, `profile/PROTOCOLS.md`, and recent memory facts (word-matched to the current message).

**Async-first** — All I/O is async. Connectors and scheduler run as concurrent asyncio tasks. Tool functions are sync but called via `asyncio.to_thread` where needed.

## Configuration

Uses pydantic-settings with `CHIVES_` prefix and `__` for nesting. Copy `.env.example` to `.env`:

```
CHIVES_LLM__BASE_URL=http://localhost:11434/v1
CHIVES_LLM__MODEL=llama3.2
CHIVES_TELEGRAM__BOT_TOKEN=...
CHIVES_TELEGRAM__ALLOWED_CHAT_IDS=[123456789]
CHIVES_IMAP__HOST=imap.example.com
CHIVES_MORNING_BRIEF_TIME=08:00
CHIVES_STATE_PATH=state
CHIVES_PROFILE_PATH=profile
```

## macOS-Specific Constraints

PyObjC integrations (`tools/calendar.py`, `tools/reminders.py`, `tools/contacts.py`) use EventKit and AddressBook frameworks — they only work on macOS and require the appropriate permissions granted to the Python process. These will fail silently or raise on Linux/Windows.

## Deployment

Runs as launchd service `com.chives.agent`. Logs go to `logs/chives.log` and `logs/chives.err`. The service uses `uv run python -m chives.main` from the repo root with KeepAlive and RunAtLoad.
