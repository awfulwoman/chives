# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Chives is a local-first general-purpose agent. It accepts messages via Telegram and Open WebUI, runs an OpenAI-compatible tool-calling loop against a local Ollama LLM, and integrates with external tools via MCP servers. Behaviour and persona are configured via profile files. It runs as a Docker container.

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

# Run via Docker
docker compose up -d
docker compose logs -f
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
  Scheduler: APScheduler jobs (nudges, event reminders in scheduler.py)
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
CHIVES_TELEGRAM__BOT_TOKEN=...  # optional — omit to run without Telegram
CHIVES_TELEGRAM__ALLOWED_CHAT_IDS=[123456789]
CHIVES_IMAP__HOST=imap.example.com
CHIVES_STATE_PATH=state
CHIVES_PROFILE_PATH=profile
```

## Deployment

Runs as a Docker container via `compose.yml`. Logs via `docker compose logs -f`.
