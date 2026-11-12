# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Chives is a local-first ADHD executive assistant agent. It accepts messages via Telegram and Open WebUI, runs an OpenAI-compatible tool-calling loop against a local Ollama LLM, and reaches Calendar, Reminders, Contacts and email through an MCP gateway (or direct IMAP). Behaviour and persona are configured via profile files. It runs as a macOS launchd service or Docker container.

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

**Dependency injection** — Tools that need shared state expose an `init()` function (e.g. `memory_tools.init(store)`, `sched_tools.init(store, ...)`). These are called in `main.py` at startup. `gateway_tools.init(url)` is async — it discovers the gateway's tools over MCP and registers them dynamically via `register_raw`.

**Per-thread conversation isolation** — History, nudges, and memory are keyed on `(connector, thread_id)`. Telegram uses `str(chat_id)`; Open WebUI uses `"openwebui"`.

**Context assembly** — `context.py` builds the system prompt by joining `profile/PERSONALITY.md`, `profile/USER.md`, `profile/PROTOCOLS.md`, and recent memory facts (word-matched to the current message). Files are read from disk on every request, so edits to the profile files take effect on the very next message with no restart or cache invalidation needed.

**Profile editor** — `connectors/editor.py` mounts basic-auth-protected `GET/POST /editor` routes on the Open WebUI FastAPI app for editing `profile/*.md` files from a browser. Credentials come from `CHIVES_EDITOR__USERNAME`/`CHIVES_EDITOR__PASSWORD`; leaving either unset disables the editor (all requests 401).

**Async-first** — All I/O is async. Connectors and scheduler run as concurrent asyncio tasks. Tool functions are sync but called via `asyncio.to_thread` where needed.

## Configuration

Uses pydantic-settings with `CHIVES_` prefix and `__` for nesting. Copy `.env.example` to `.env`:

```
CHIVES_LLM__BASE_URL=http://localhost:11434/v1
CHIVES_LLM__MODEL=llama3.2
CHIVES_TELEGRAM__BOT_TOKEN=...  # optional — omit to run without Telegram
CHIVES_TELEGRAM__ALLOWED_CHAT_IDS=[123456789]
CHIVES_GATEWAY_URL=http://127.0.0.1:4000/mcp  # optional — supplies calendar, reminders, contacts, email
CHIVES_IMAP__HOST=imap.example.com  # fallback if no gateway
CHIVES_EDITOR__USERNAME=admin  # optional — omit to disable the /editor web editor
CHIVES_EDITOR__PASSWORD=change_me
CHIVES_MORNING_BRIEF_TIME=08:00
CHIVES_STATE_PATH=state
CHIVES_PROFILE_PATH=profile
```

## Tests

```bash
uv run pytest tests/              # hermetic suite (live tests deselected)
uv run pytest -m live             # end-to-end against a real LLM endpoint
uv run python scripts/smoke.py    # post-deploy dependency check
```

`tests/conftest.py` strips `CHIVES_*` from the environment and detaches
pydantic-settings from `.env`, so the suite never picks up local config.

Live e2e tests (`tests/e2e/`) drive the full stack against a real endpoint —
default `http://192.168.1.99:11434/v1` with `gemma4:31b-cloud`, overridable via
`E2E_LLM_BASE_URL` / `E2E_LLM_MODEL` / `E2E_LLM_TIMEOUT`. They skip cleanly when
the endpoint is unreachable. They assert on model *behaviour*: that PROTOCOLS.md's
"always use tools" rules are actually obeyed, not just acknowledged.

## macOS-Specific Constraints

Calendar, Reminders and Contacts come from the MCP gateway rather than
in-process PyObjC, so the agent itself is portable. The gateway is the component
that needs EventKit/AddressBook permissions on macOS.

## Deployment

Runs as a macOS launchd service or Docker container via `compose.yml`. Logs via `docker compose logs -f` or `logs/chives.log`.
