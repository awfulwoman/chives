# Chives — Design Spec

**Date:** 2026-04-09
**Status:** Approved

---

## Overview

Chives is a local-first ADHD executive assistant agent running on a Mac Mini M4 (192.168.1.150). It uses an OpenAI-compatible protocol abstraction to talk to a local Ollama instance, making the LLM provider swappable via config. It communicates via Telegram and Open WebUI, integrates with Apple Calendar, Reminders, Contacts, and IMAP email, and proactively fills in executive-function gaps for a user with ADHD.

---

## Architecture

```
User
  ├── Telegram Bot ──────────────┐
  └── Open WebUI Agent API ──────┤
                                 ▼
                           Message Bus (asyncio queue)
                                 │
                           Pipeline (middleware)
                           ├── rate limiter
                           ├── typing indicator
                           └── slash command parser
                                 │
                           Agent (tool-calling loop)
                           ├── OpenAI SDK → Ollama (base_url configurable)
                           ├── Tool Registry (in-process Python functions)
                           │   ├── calendar   (EventKit via PyObjC)
                           │   ├── reminders  (EventKit via PyObjC)
                           │   ├── email      (IMAP)
                           │   ├── contacts   (AddressBook via PyObjC)
                           │   ├── memory     (SQLite + sqlite-vec)
                           │   └── schedule   (one-shot nudges)
                           └── Context builder (profile + history)
                                 │
                    ┌────────────┴─────────────┐
                 Store (SQLite)          Scheduler (APScheduler)
                 ├── turns               ├── proactive nudges
                 ├── memory              ├── event reminders
                 └── nudge queue         └── idle check-ins
```

Single Python process, `uv`-managed, runs as a `launchd` service on macOS.

---

## Components

### LLM Backend

OpenAI Python SDK with configurable `base_url`, `model`, and `api_key`. Default points at local Ollama (`http://localhost:11434/v1`). Swapping providers requires only config changes — no code changes.

### Tool Registry

Python functions decorated with a `@tool` descriptor that emits OpenAI-compatible JSON schema. Tools are invoked directly in-process (no MCP bridge).

| Domain | Operations |
|---|---|
| `calendar` | list events (today/week), create event, update event |
| `reminders` | list due/overdue, create reminder, mark complete |
| `email` | fetch unread, search, summarize thread, flag/archive |
| `contacts` | lookup by name/email |
| `memory` | store fact, recall facts (semantic search via sqlite-vec) |
| `schedule` | set one-shot follow-up nudge, cancel nudge |

Apple integrations (calendar, reminders, contacts) use PyObjC to call EventKit and AddressBook frameworks directly.

### Connectors

- **Telegram**: `python-telegram-bot`, polling mode. Restricted to `ALLOWED_CHAT_IDS`.
- **Open WebUI**: FastAPI endpoint implementing the Open WebUI agent API spec (streaming SSE responses).

### Agent Loop

Standard OpenAI tool-calling loop: send messages + tool schemas → receive response → if tool calls present, execute and append results → repeat until final text response. Turn history stored in SQLite per connector+thread.

### Context Builder

Assembles the system prompt from:
1. `profile/PERSONALITY.md` — agent identity and tone
2. `profile/USER.md` — user's name, preferences, ADHD context
3. `profile/PROTOCOLS.md` — rules (email handling, nudge thresholds, etc.)
4. Recent memory facts (retrieved via semantic search on the current message)

### Scheduler

APScheduler with AsyncIO executor. Handles:
- **Morning brief** — fires daily at configured time, summarizes calendar + overdue reminders + flagged email, sends to Telegram unprompted
- **Event reminders** — fires N minutes before calendar events with a short context message
- **Commitment nudges** — one-shot follow-ups created when user commits to a task ("I'll do X by Thursday")
- **Idle check-in** — optional; sends a gentle check-in after N hours of inactivity

### Store

Single SQLite file at `state/chives.db`.

| Table | Purpose |
|---|---|
| `turns` | Full conversation history per connector+thread |
| `memory` | Key facts with vector embeddings (sqlite-vec) |
| `nudges` | Scheduled one-shot follow-ups |
| `email_seen` | Processed message IDs to avoid re-processing |

---

## ADHD-Specific Design

These behaviors are baked into the system prompt and scheduler, not bolted on:

- **Morning brief**: unprompted daily summary — calendar, overdue reminders, flagged emails
- **Event reminders**: proactive heads-up N minutes before events with relevant context
- **Commitment tracking**: when user says "I'll do X", agent schedules a follow-up and stores the commitment in memory
- **Response style**: system prompt enforces short bullet-point answers, no preamble, one clear next action per response
- **Task decomposition**: complex requests broken into numbered steps with offer to schedule each one
- **Idle check-in**: gentle "still here" message after configurable inactivity window (off by default)

---

## Configuration

`.env` file, all variables prefixed `CHIVES_`. Loaded via `pydantic-settings`.

| Variable | Default | Description |
|---|---|---|
| `CHIVES_LLM__BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `CHIVES_LLM__MODEL` | `llama3.2` | Model name |
| `CHIVES_LLM__API_KEY` | `ollama` | API key (ignored by Ollama) |
| `CHIVES_TELEGRAM__BOT_TOKEN` | — | Telegram bot token |
| `CHIVES_TELEGRAM__ALLOWED_CHAT_IDS` | — | JSON array of allowed chat IDs |
| `CHIVES_IMAP__HOST` | — | IMAP server hostname |
| `CHIVES_IMAP__PORT` | `993` | IMAP port |
| `CHIVES_IMAP__USERNAME` | — | IMAP username |
| `CHIVES_IMAP__PASSWORD` | — | IMAP password |
| `CHIVES_MORNING_BRIEF_TIME` | `08:00` | Local time for daily brief |
| `CHIVES_EVENT_REMINDER_MINUTES` | `15` | Minutes before event to send reminder |
| `CHIVES_IDLE_CHECKIN_HOURS` | `0` | Hours before idle check-in (0 = disabled) |
| `CHIVES_STATE_PATH` | `state` | Directory for SQLite database |
| `CHIVES_PROFILE_PATH` | `profile` | Directory for personality/protocol markdown |

---

## Package Layout

```
chives/
├── connectors/
│   ├── telegram.py       # python-telegram-bot polling connector
│   └── openwebui.py      # FastAPI agent API endpoint
├── tools/
│   ├── registry.py       # @tool decorator and schema emission
│   ├── calendar.py       # EventKit calendar via PyObjC
│   ├── reminders.py      # EventKit reminders via PyObjC
│   ├── email.py          # IMAP email
│   ├── contacts.py       # AddressBook via PyObjC
│   ├── memory.py         # SQLite + sqlite-vec memory
│   └── schedule.py       # One-shot nudge scheduling
├── agent.py              # Tool-calling loop
├── bus.py                # Asyncio message queue
├── pipeline.py           # Middleware chain
├── scheduler.py          # APScheduler wrapper + proactive jobs
├── store.py              # SQLite layer
├── context.py            # System prompt assembly
├── config.py             # pydantic-settings config
└── main.py               # Entry point
profile/
├── PERSONALITY.md
├── USER.md
├── PROTOCOLS.md
└── CHECKIN.md
scripts/
├── install_service.sh    # launchd install
└── uninstall_service.sh
pyproject.toml
.env.example
```

---

## Running

```bash
# Install as launchd service (runs at login, restarts on crash)
scripts/install_service.sh

# Remove service
scripts/uninstall_service.sh

# Run directly (dev/debug)
uv run python -m chives.main
```

---

## Testing

```bash
uv run pytest
```

Unit tests for tools (mocked PyObjC/IMAP), integration tests for the agent loop with a stubbed LLM backend.
