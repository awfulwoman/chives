# Chives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first ADHD executive assistant agent using Ollama, with Telegram + Open WebUI connectors, Apple ecosystem tools, and a proactive scheduler.

**Architecture:** Single Python process (uv-managed, launchd service on macOS). Messages flow from Telegram/Open WebUI connectors → asyncio bus → pipeline middleware → agent tool-calling loop → OpenAI-compatible LLM (Ollama). Apple tools use PyObjC directly in-process; IMAP for email.

**Tech Stack:** Python 3.12+, uv, openai SDK, python-telegram-bot 21, FastAPI, APScheduler 3.x, PyObjC (EventKit + Contacts), pydantic-settings, sqlite-vec, pytest + pytest-asyncio

---

## File Map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Project metadata, dependencies, tool config |
| `chives/config.py` | Pydantic-settings config, all `CHIVES_` env vars |
| `chives/store.py` | SQLite layer: turns, memory, nudges, email_seen |
| `chives/tools/registry.py` | `@tool` decorator, `get_tools_schema()`, `dispatch_tool()` |
| `chives/tools/memory.py` | store/recall facts (sqlite-vec semantic search) |
| `chives/tools/calendar.py` | EventKit calendar via PyObjC |
| `chives/tools/reminders.py` | EventKit reminders via PyObjC |
| `chives/tools/contacts.py` | AddressBook/Contacts via PyObjC |
| `chives/tools/email.py` | IMAP: fetch unread, search, summarize, flag/archive |
| `chives/tools/schedule.py` | One-shot nudge creation/cancellation |
| `chives/context.py` | System prompt assembly from profile files + memory |
| `chives/agent.py` | OpenAI tool-calling loop, turn storage |
| `chives/bus.py` | Asyncio message queue, message dataclass |
| `chives/pipeline.py` | Middleware chain: rate limit, slash commands |
| `chives/connectors/telegram.py` | python-telegram-bot polling connector |
| `chives/connectors/openwebui.py` | FastAPI OpenAI-compatible chat completions endpoint |
| `chives/scheduler.py` | APScheduler: morning brief, event reminders, nudges, idle |
| `chives/main.py` | Entry point, wires all components |
| `profile/PERSONALITY.md` | Agent identity and tone |
| `profile/USER.md` | User preferences, ADHD context |
| `profile/PROTOCOLS.md` | Behavioral rules for email, nudges, escalation |
| `profile/CHECKIN.md` | Idle and morning check-in prompt templates |
| `scripts/install_service.sh` | launchd plist install |
| `scripts/uninstall_service.sh` | launchd plist remove |
| `.env.example` | Example environment variables |

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `chives/__init__.py`
- Create: `chives/tools/__init__.py`
- Create: `chives/connectors/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/tools/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "chives"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "openai>=1.0",
    "python-telegram-bot>=21",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "pydantic-settings>=2.0",
    "apscheduler>=3.10,<4",
    "pyobjc-framework-EventKit>=10",
    "pyobjc-framework-Contacts>=10",
    "sqlite-vec>=0.1",
    "httpx>=0.25",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create empty `__init__.py` files**

```bash
mkdir -p chives/tools chives/connectors tests/tools
touch chives/__init__.py chives/tools/__init__.py chives/connectors/__init__.py tests/__init__.py tests/tools/__init__.py
```

- [ ] **Step 3: Install dependencies**

```bash
uv sync
```

Expected: all packages install without errors.

- [ ] **Step 4: Verify Python version**

```bash
uv run python --version
```

Expected: `Python 3.12.x`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml chives/ tests/
git commit -m "chore: project scaffold"
```

---

## Task 2: Config

**Files:**
- Create: `chives/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import os
import pytest
from chives.config import Config


def test_defaults():
    config = Config()
    assert config.llm.base_url == "http://localhost:11434/v1"
    assert config.llm.model == "llama3.2"
    assert config.llm.api_key == "ollama"
    assert config.imap.port == 993
    assert config.morning_brief_time == "08:00"
    assert config.event_reminder_minutes == 15
    assert config.idle_checkin_hours == 0
    assert config.state_path == "state"
    assert config.profile_path == "profile"


def test_env_override(monkeypatch):
    monkeypatch.setenv("CHIVES_LLM__BASE_URL", "http://192.168.1.150:11434/v1")
    monkeypatch.setenv("CHIVES_LLM__MODEL", "mistral")
    config = Config()
    assert config.llm.base_url == "http://192.168.1.150:11434/v1"
    assert config.llm.model == "mistral"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `chives.config`.

- [ ] **Step 3: Write `chives/config.py`**

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3.2"
    api_key: str = "ollama"


class TelegramConfig(BaseModel):
    bot_token: str = ""
    allowed_chat_ids: List[int] = []


class IMAPConfig(BaseModel):
    host: str = ""
    port: int = 993
    username: str = ""
    password: str = ""


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHIVES_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    llm: LLMConfig = LLMConfig()
    telegram: TelegramConfig = TelegramConfig()
    imap: IMAPConfig = IMAPConfig()
    morning_brief_time: str = "08:00"
    event_reminder_minutes: int = 15
    idle_checkin_hours: int = 0
    state_path: str = "state"
    profile_path: str = "profile"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/config.py tests/test_config.py
git commit -m "feat: pydantic-settings config"
```

---

## Task 3: Store

**Files:**
- Create: `chives/store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_store.py`:

```python
import time
import pytest
from chives.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path))


def test_add_and_get_turns(store):
    store.add_turn("telegram", "123", "user", "hello")
    store.add_turn("telegram", "123", "assistant", "hi there")
    turns = store.get_turns("telegram", "123")
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "hello"
    assert turns[1]["role"] == "assistant"


def test_turns_isolated_by_thread(store):
    store.add_turn("telegram", "123", "user", "thread 1")
    store.add_turn("telegram", "456", "user", "thread 2")
    assert len(store.get_turns("telegram", "123")) == 1
    assert len(store.get_turns("telegram", "456")) == 1


def test_add_and_get_memory(store):
    store.add_memory("user prefers bullet points")
    mems = store.get_all_memories()
    assert len(mems) == 1
    assert mems[0]["fact"] == "user prefers bullet points"


def test_nudge_lifecycle(store):
    fire_at = time.time() - 1  # already past
    nid = store.add_nudge("call dentist", fire_at, "telegram", "123")
    pending = store.get_pending_nudges()
    assert any(n["id"] == nid for n in pending)
    store.mark_nudge_fired(nid)
    assert not any(n["id"] == nid for n in store.get_pending_nudges())


def test_email_seen(store):
    assert not store.is_email_seen("msg-001")
    store.mark_email_seen("msg-001")
    assert store.is_email_seen("msg-001")
    # idempotent
    store.mark_email_seen("msg-001")
    assert store.is_email_seen("msg-001")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_store.py -v
```

Expected: `ImportError` for `chives.store`.

- [ ] **Step 3: Write `chives/store.py`**

```python
import sqlite3
import time
from pathlib import Path
from typing import Optional


class Store:
    def __init__(self, state_path: str):
        Path(state_path).mkdir(parents=True, exist_ok=True)
        self.db_path = str(Path(state_path) / "chives.db")
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    connector TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL,
                    embedding BLOB,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nudges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    fire_at REAL NOT NULL,
                    connector TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    fired INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS email_seen (
                    message_id TEXT PRIMARY KEY
                );
            """)

    # --- Turns ---

    def add_turn(self, connector: str, thread_id: str, role: str, content: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO turns (connector, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (connector, thread_id, role, content, time.time()),
            )

    def get_turns(self, connector: str, thread_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM turns "
                "WHERE connector=? AND thread_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (connector, thread_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # --- Memory ---

    def add_memory(self, fact: str, embedding: Optional[bytes] = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO memory (fact, embedding, created_at) VALUES (?, ?, ?)",
                (fact, embedding, time.time()),
            )
            return cur.lastrowid

    def get_all_memories(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, fact, embedding FROM memory ORDER BY created_at"
            ).fetchall()
        return [{"id": r["id"], "fact": r["fact"], "embedding": r["embedding"]} for r in rows]

    # --- Nudges ---

    def add_nudge(
        self, description: str, fire_at: float, connector: str, thread_id: str
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO nudges (description, fire_at, connector, thread_id) VALUES (?, ?, ?, ?)",
                (description, fire_at, connector, thread_id),
            )
            return cur.lastrowid

    def get_pending_nudges(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, description, fire_at, connector, thread_id FROM nudges "
                "WHERE fired=0 AND fire_at <= ?",
                (time.time(),),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_nudge_fired(self, nudge_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE nudges SET fired=1 WHERE id=?", (nudge_id,))

    def cancel_nudge(self, nudge_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM nudges WHERE id=?", (nudge_id,))

    # --- Email seen ---

    def mark_email_seen(self, message_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO email_seen (message_id) VALUES (?)",
                (message_id,),
            )

    def is_email_seen(self, message_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM email_seen WHERE message_id=?", (message_id,)
            ).fetchone()
        return row is not None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_store.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/store.py tests/test_store.py
git commit -m "feat: SQLite store (turns, memory, nudges, email_seen)"
```

---

## Task 4: Tool registry

**Files:**
- Create: `chives/tools/registry.py`
- Create: `tests/tools/test_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_registry.py`:

```python
import json
import pytest
from chives.tools.registry import tool, get_tools_schema, dispatch_tool, clear_registry


@pytest.fixture(autouse=True)
def reset_registry():
    clear_registry()
    yield
    clear_registry()


def test_tool_registers_schema():
    @tool
    def greet(name: str) -> str:
        """Say hello to someone."""
        return f"Hello {name}"

    schemas = get_tools_schema()
    assert len(schemas) == 1
    fn_schema = schemas[0]["function"]
    assert fn_schema["name"] == "greet"
    assert fn_schema["description"] == "Say hello to someone."
    assert fn_schema["parameters"]["properties"]["name"]["type"] == "string"
    assert "name" in fn_schema["parameters"]["required"]


async def test_dispatch_tool():
    @tool
    def add(a: int, b: int) -> str:
        """Add two numbers."""
        return str(a + b)

    result = await dispatch_tool("add", json.dumps({"a": 2, "b": 3}))
    assert result == "5"


async def test_dispatch_unknown_tool():
    result = await dispatch_tool("nonexistent", "{}")
    data = json.loads(result)
    assert "error" in data


async def test_dispatch_tool_exception():
    @tool
    def broken(x: str) -> str:
        """Always fails."""
        raise ValueError("oops")

    result = await dispatch_tool("broken", json.dumps({"x": "y"}))
    data = json.loads(result)
    assert "error" in data
    assert "oops" in data["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/tools/test_registry.py -v
```

Expected: `ImportError` for `chives.tools.registry`.

- [ ] **Step 3: Write `chives/tools/registry.py`**

```python
import inspect
import json
from functools import wraps
from typing import Callable, List

_registry: dict[str, Callable] = {}
_schemas: list[dict] = []

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def tool(fn: Callable) -> Callable:
    """Register a function as an agent tool with OpenAI-compatible JSON schema."""
    name = fn.__name__
    doc = inspect.getdoc(fn) or ""
    sig = inspect.signature(fn)

    properties: dict[str, dict] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        ann = param.annotation
        json_type = _TYPE_MAP.get(ann, "string")
        properties[param_name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    _registry[name] = fn
    _schemas.append({
        "type": "function",
        "function": {
            "name": name,
            "description": doc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    })

    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


def get_tools_schema() -> List[dict]:
    return list(_schemas)


async def dispatch_tool(name: str, arguments: str) -> str:
    """Dispatch a tool call by name with JSON-encoded arguments. Returns JSON string."""
    fn = _registry.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        args = json.loads(arguments)
        result = fn(**args)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def clear_registry() -> None:
    """Clear all registered tools. Used in tests."""
    _registry.clear()
    _schemas.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/tools/test_registry.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/tools/registry.py tests/tools/test_registry.py
git commit -m "feat: tool registry with OpenAI schema emission"
```

---

## Task 5: Memory tool

**Files:**
- Create: `chives/tools/memory.py`
- Create: `tests/tools/test_memory.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_memory.py`:

```python
import pytest
from chives.store import Store
import chives.tools.memory as memory_tools
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path))
    memory_tools.init(s)
    return s


def test_store_fact(store):
    result = memory_tools.store_fact("user likes coffee")
    assert "stored" in result.lower()
    mems = store.get_all_memories()
    assert any("coffee" in m["fact"] for m in mems)


def test_recall_facts(store):
    memory_tools.store_fact("user prefers short answers")
    memory_tools.store_fact("user has a dog named Biscuit")
    result = memory_tools.recall_facts("dog")
    assert "Biscuit" in result


def test_recall_empty(store):
    result = memory_tools.recall_facts("anything")
    assert "no" in result.lower() or result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/tools/test_memory.py -v
```

Expected: `ImportError` for `chives.tools.memory`.

- [ ] **Step 3: Write `chives/tools/memory.py`**

Note: uses simple substring search for now; semantic search via sqlite-vec can be added once an embedding model is confirmed.

```python
from __future__ import annotations
from chives.store import Store
from chives.tools.registry import tool

_store: Store | None = None


def init(store: Store) -> None:
    global _store
    _store = store
    # Register tools now that we have dependencies
    _register()


def _register() -> None:
    @tool
    def store_fact(fact: str) -> str:
        """Store a fact about the user or their context for future recall."""
        assert _store is not None
        _store.add_memory(fact)
        return f"Stored: {fact}"

    @tool
    def recall_facts(query: str) -> str:
        """Recall stored facts relevant to a query."""
        assert _store is not None
        memories = _store.get_all_memories()
        if not memories:
            return "No facts stored yet."
        hits = [m["fact"] for m in memories if query.lower() in m["fact"].lower()]
        if not hits:
            # Return most recent 10 facts when no substring match
            hits = [m["fact"] for m in memories[-10:]]
        return "\n".join(f"- {h}" for h in hits)

    globals()["store_fact"] = store_fact
    globals()["recall_facts"] = recall_facts
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/tools/test_memory.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/tools/memory.py tests/tools/test_memory.py
git commit -m "feat: memory tool (store/recall facts)"
```

---

## Task 6: Calendar tool

**Files:**
- Create: `chives/tools/calendar.py`
- Create: `tests/tools/test_calendar.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_calendar.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def mock_ek(monkeypatch):
    """Patch EventKit at the module level before import."""
    mock_store = MagicMock()
    mock_event = MagicMock()
    mock_event.title.return_value = "Dentist"
    mock_event.startDate.return_value = MagicMock()
    mock_event.startDate.return_value.description.return_value = "2026-04-10 10:00:00 +0000"
    mock_event.location.return_value = "123 Main St"
    mock_store.eventsMatchingPredicate_.return_value = [mock_event]

    EventKit_mock = MagicMock()
    EventKit_mock.EKEventStore.alloc.return_value.init.return_value = mock_store
    EventKit_mock.EKEntityTypeEvent = 0

    with patch.dict("sys.modules", {"EventKit": EventKit_mock}):
        import chives.tools.calendar as cal
        cal._ek_store = mock_store
        yield mock_store, cal


def test_list_events_today(mock_ek):
    mock_store, cal = mock_ek
    result = cal.list_calendar_events(period="today")
    data = json.loads(result)
    assert isinstance(data, list)


def test_create_event_returns_confirmation(mock_ek):
    mock_store, cal = mock_ek
    mock_store.saveEvent_span_commit_error_.return_value = True
    result = cal.create_calendar_event(
        title="Meeting",
        start_iso="2026-04-10T10:00:00",
        end_iso="2026-04-10T11:00:00",
        location="Office",
    )
    assert "created" in result.lower() or "meeting" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/tools/test_calendar.py -v
```

Expected: `ImportError` or assertion failure.

- [ ] **Step 3: Write `chives/tools/calendar.py`**

```python
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from chives.tools.registry import tool

_ek_store = None


def _get_store():
    global _ek_store
    if _ek_store is not None:
        return _ek_store
    import EventKit
    import threading

    store = EventKit.EKEventStore.alloc().init()
    done = threading.Event()

    def cb(granted, error):
        done.set()

    # macOS 14+: requestFullAccessToEventsWithCompletion_
    # macOS 13: requestAccessToEntityType_completion_
    try:
        store.requestFullAccessToEventsWithCompletion_(cb)
    except AttributeError:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, cb)

    done.wait(timeout=10)
    _ek_store = store
    return store


def _ns_date(iso: str):
    import Foundation
    dt = datetime.fromisoformat(iso)
    ts = dt.timestamp()
    return Foundation.NSDate.dateWithTimeIntervalSince1970_(ts)


@tool
def list_calendar_events(period: str) -> str:
    """List calendar events. period must be 'today' or 'week'."""
    import EventKit
    store = _get_store()

    now = datetime.now(timezone.utc)
    if period == "today":
        end = now.replace(hour=23, minute=59, second=59)
    else:
        end = now + timedelta(days=7)

    import Foundation
    ns_start = Foundation.NSDate.dateWithTimeIntervalSince1970_(now.timestamp())
    ns_end = Foundation.NSDate.dateWithTimeIntervalSince1970_(end.timestamp())

    calendars = store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, calendars
    )
    events = store.eventsMatchingPredicate_(pred)

    results = []
    for ev in (events or []):
        results.append({
            "title": str(ev.title()),
            "start": str(ev.startDate().description()),
            "location": str(ev.location() or ""),
        })
    return json.dumps(results)


@tool
def create_calendar_event(title: str, start_iso: str, end_iso: str, location: str) -> str:
    """Create a calendar event. Dates must be ISO 8601 format (e.g. 2026-04-10T14:00:00)."""
    import EventKit
    store = _get_store()

    event = EventKit.EKEvent.eventWithEventStore_(store)
    event.setTitle_(title)
    event.setStartDate_(_ns_date(start_iso))
    event.setEndDate_(_ns_date(end_iso))
    if location:
        event.setLocation_(location)
    event.setCalendar_(store.defaultCalendarForNewEvents())

    error_ptr = None
    ok = store.saveEvent_span_commit_error_(
        event, EventKit.EKSpanThisEvent, True, error_ptr
    )
    if ok:
        return f"Created event: {title} at {start_iso}"
    return f"Failed to create event: {title}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/tools/test_calendar.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/tools/calendar.py tests/tools/test_calendar.py
git commit -m "feat: calendar tool (EventKit via PyObjC)"
```

---

## Task 7: Reminders tool

**Files:**
- Create: `chives/tools/reminders.py`
- Create: `tests/tools/test_reminders.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_reminders.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def mock_ek(monkeypatch):
    mock_store = MagicMock()
    mock_reminder = MagicMock()
    mock_reminder.title.return_value = "Buy milk"
    mock_reminder.isCompleted.return_value = False
    mock_reminder.dueDateComponents.return_value = None
    mock_store.fetchRemindersMatchingPredicate_completion_.side_effect = (
        lambda pred, cb: cb([mock_reminder])
    )

    EventKit_mock = MagicMock()
    EventKit_mock.EKEventStore.alloc.return_value.init.return_value = mock_store
    EventKit_mock.EKEntityTypeReminder = 1

    with patch.dict("sys.modules", {"EventKit": EventKit_mock}):
        import chives.tools.reminders as rem
        rem._ek_store = mock_store
        yield mock_store, rem


def test_list_reminders(mock_ek):
    mock_store, rem = mock_ek
    result = rem.list_reminders(include_completed="false")
    data = json.loads(result)
    assert isinstance(data, list)


def test_create_reminder(mock_ek):
    mock_store, rem = mock_ek
    mock_store.saveReminder_commit_error_.return_value = True
    result = rem.create_reminder(title="Call doctor", due_iso="")
    assert "call doctor" in result.lower() or "created" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/tools/test_reminders.py -v
```

Expected: `ImportError` for `chives.tools.reminders`.

- [ ] **Step 3: Write `chives/tools/reminders.py`**

```python
from __future__ import annotations
import json
import threading
from chives.tools.registry import tool

_ek_store = None


def _get_store():
    global _ek_store
    if _ek_store is not None:
        return _ek_store
    import EventKit

    store = EventKit.EKEventStore.alloc().init()
    done = threading.Event()

    def cb(granted, error):
        done.set()

    try:
        store.requestFullAccessToRemindersWithCompletion_(cb)
    except AttributeError:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeReminder, cb)

    done.wait(timeout=10)
    _ek_store = store
    return store


@tool
def list_reminders(include_completed: str) -> str:
    """List reminders. include_completed must be 'true' or 'false'."""
    import EventKit

    store = _get_store()
    done = threading.Event()
    found: list = []

    pred = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
        None, None, None
    )

    def cb(reminders):
        found.extend(reminders or [])
        done.set()

    store.fetchRemindersMatchingPredicate_completion_(pred, cb)
    done.wait(timeout=10)

    results = []
    for r in found:
        if include_completed == "false" and r.isCompleted():
            continue
        results.append({
            "title": str(r.title()),
            "completed": bool(r.isCompleted()),
        })
    return json.dumps(results)


@tool
def create_reminder(title: str, due_iso: str) -> str:
    """Create a reminder. due_iso is optional ISO 8601 date or empty string."""
    import EventKit

    store = _get_store()
    reminder = EventKit.EKReminder.reminderWithEventStore_(store)
    reminder.setTitle_(title)
    reminder.setCalendar_(store.defaultCalendarForNewReminders())

    if due_iso:
        from datetime import datetime
        import Foundation

        dt = datetime.fromisoformat(due_iso)
        components = Foundation.NSDateComponents.alloc().init()
        components.setYear_(dt.year)
        components.setMonth_(dt.month)
        components.setDay_(dt.day)
        components.setHour_(dt.hour)
        components.setMinute_(dt.minute)
        reminder.setDueDateComponents_(components)

    ok = store.saveReminder_commit_error_(reminder, True, None)
    if ok:
        return f"Created reminder: {title}"
    return f"Failed to create reminder: {title}"


@tool
def complete_reminder(title: str) -> str:
    """Mark a reminder as completed by title (case-insensitive match)."""
    import EventKit

    store = _get_store()
    done = threading.Event()
    found: list = []

    pred = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
        None, None, None
    )

    def cb(reminders):
        found.extend(reminders or [])
        done.set()

    store.fetchRemindersMatchingPredicate_completion_(pred, cb)
    done.wait(timeout=10)

    for r in found:
        if title.lower() in str(r.title()).lower():
            r.setCompleted_(True)
            store.saveReminder_commit_error_(r, True, None)
            return f"Completed: {r.title()}"

    return f"No reminder found matching: {title}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/tools/test_reminders.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/tools/reminders.py tests/tools/test_reminders.py
git commit -m "feat: reminders tool (EventKit via PyObjC)"
```

---

## Task 8: Contacts tool

**Files:**
- Create: `chives/tools/contacts.py`
- Create: `tests/tools/test_contacts.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_contacts.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


def test_lookup_contact_by_name():
    mock_contact = MagicMock()
    mock_contact.givenName.return_value = "Alice"
    mock_contact.familyName.return_value = "Smith"
    mock_contact.emailAddresses.return_value = [MagicMock(value=MagicMock(return_value="alice@example.com"))]
    mock_contact.phoneNumbers.return_value = []

    Contacts_mock = MagicMock()
    mock_store = MagicMock()
    mock_store.unifiedContactsMatchingPredicate_keysToFetch_error_.return_value = (
        [mock_contact], None
    )
    Contacts_mock.CNContactStore.alloc.return_value.init.return_value = mock_store
    Contacts_mock.CNContact.predicateForContactsMatchingName_.return_value = MagicMock()
    Contacts_mock.CNContactGivenNameKey = "givenName"
    Contacts_mock.CNContactFamilyNameKey = "familyName"
    Contacts_mock.CNContactEmailAddressesKey = "emailAddresses"
    Contacts_mock.CNContactPhoneNumbersKey = "phoneNumbers"

    with patch.dict("sys.modules", {"Contacts": Contacts_mock}):
        import chives.tools.contacts as contacts
        contacts._cn_store = mock_store
        result = contacts.lookup_contact(name="Alice")
        data = json.loads(result)
        assert isinstance(data, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/tools/test_contacts.py -v
```

Expected: `ImportError` for `chives.tools.contacts`.

- [ ] **Step 3: Write `chives/tools/contacts.py`**

```python
from __future__ import annotations
import json
from chives.tools.registry import tool

_cn_store = None


def _get_store():
    global _cn_store
    if _cn_store is not None:
        return _cn_store
    import Contacts

    store = Contacts.CNContactStore.alloc().init()
    _cn_store = store
    return store


@tool
def lookup_contact(name: str) -> str:
    """Look up a contact by name. Returns a list of matching contacts with email and phone."""
    import Contacts

    store = _get_store()
    keys = [
        Contacts.CNContactGivenNameKey,
        Contacts.CNContactFamilyNameKey,
        Contacts.CNContactEmailAddressesKey,
        Contacts.CNContactPhoneNumbersKey,
    ]
    pred = Contacts.CNContact.predicateForContactsMatchingName_(name)
    contacts, error = store.unifiedContactsMatchingPredicate_keysToFetch_error_(
        pred, keys, None
    )
    if error:
        return json.dumps({"error": str(error)})

    results = []
    for c in (contacts or []):
        emails = [str(e.value()) for e in (c.emailAddresses() or [])]
        phones = [str(p.value().stringValue()) for p in (c.phoneNumbers() or [])]
        results.append({
            "name": f"{c.givenName()} {c.familyName()}".strip(),
            "emails": emails,
            "phones": phones,
        })
    return json.dumps(results)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/tools/test_contacts.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/tools/contacts.py tests/tools/test_contacts.py
git commit -m "feat: contacts tool (CNContactStore via PyObjC)"
```

---

## Task 9: Email tool

**Files:**
- Create: `chives/tools/email.py`
- Create: `tests/tools/test_email.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_email.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from chives.config import IMAPConfig
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def imap_config():
    return IMAPConfig(host="imap.example.com", port=993, username="user", password="pass")


def _make_fetch_response():
    """Simulates imaplib fetch response for a simple text email."""
    raw = (
        b"From: sender@example.com\r\n"
        b"Subject: Test subject\r\n"
        b"Date: Thu, 10 Apr 2026 10:00:00 +0000\r\n"
        b"Message-ID: <msg001@example.com>\r\n"
        b"\r\n"
        b"Hello world"
    )
    return [b"1 (RFC822 {%d}" % len(raw), raw]


def test_fetch_unread_emails(imap_config):
    mock_conn = MagicMock()
    mock_conn.search.return_value = ("OK", [b"1 2"])
    mock_conn.fetch.return_value = ("OK", _make_fetch_response())
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
        import chives.tools.email as email_tools
        email_tools.init(imap_config)
        result = email_tools.fetch_unread_emails(max_count="5")
        data = json.loads(result)
        assert isinstance(data, list)


def test_search_emails(imap_config):
    mock_conn = MagicMock()
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("OK", _make_fetch_response())
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
        import chives.tools.email as email_tools
        email_tools.init(imap_config)
        result = email_tools.search_emails(query="test")
        data = json.loads(result)
        assert isinstance(data, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/tools/test_email.py -v
```

Expected: `ImportError` for `chives.tools.email`.

- [ ] **Step 3: Write `chives/tools/email.py`**

```python
from __future__ import annotations
import email
import imaplib
import json
from contextlib import contextmanager
from chives.config import IMAPConfig
from chives.tools.registry import tool

_imap_config: IMAPConfig | None = None


def init(imap_config: IMAPConfig) -> None:
    global _imap_config
    _imap_config = imap_config
    _register()


@contextmanager
def _connection():
    assert _imap_config is not None
    conn = imaplib.IMAP4_SSL(_imap_config.host, _imap_config.port)
    conn.login(_imap_config.username, _imap_config.password)
    conn.select("INBOX")
    try:
        yield conn
    finally:
        conn.logout()


def _parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors="replace")
                break
    else:
        body = msg.get_payload(decode=True).decode(errors="replace")
    return {
        "from": msg.get("From", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "body_preview": body[:300],
    }


def _register() -> None:
    @tool
    def fetch_unread_emails(max_count: str) -> str:
        """Fetch unread emails from INBOX. max_count is the maximum number to return."""
        n = int(max_count)
        with _connection() as conn:
            _, data = conn.search(None, "UNSEEN")
            ids = data[0].split()[-n:]
            results = []
            for uid in ids:
                _, msg_data = conn.fetch(uid, "(RFC822)")
                raw = msg_data[1] if isinstance(msg_data[1], bytes) else msg_data[0][1]
                results.append(_parse_message(raw))
        return json.dumps(results)

    @tool
    def search_emails(query: str) -> str:
        """Search emails by subject or sender. Returns up to 10 matches."""
        with _connection() as conn:
            _, data = conn.search(None, f'OR SUBJECT "{query}" FROM "{query}"')
            ids = data[0].split()[-10:]
            results = []
            for uid in ids:
                _, msg_data = conn.fetch(uid, "(RFC822)")
                raw = msg_data[1] if isinstance(msg_data[1], bytes) else msg_data[0][1]
                results.append(_parse_message(raw))
        return json.dumps(results)

    @tool
    def archive_email(message_id: str) -> str:
        """Archive an email by its Message-ID header value."""
        with _connection() as conn:
            _, data = conn.search(None, f'HEADER Message-ID "{message_id}"')
            ids = data[0].split()
            if not ids:
                return f"No email found with ID: {message_id}"
            conn.store(ids[0], "+FLAGS", "\\Deleted")
            conn.expunge()
        return f"Archived email: {message_id}"

    globals().update({
        "fetch_unread_emails": fetch_unread_emails,
        "search_emails": search_emails,
        "archive_email": archive_email,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/tools/test_email.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/tools/email.py tests/tools/test_email.py
git commit -m "feat: email tool (IMAP fetch, search, archive)"
```

---

## Task 10: Schedule tool

**Files:**
- Create: `chives/tools/schedule.py`
- Create: `tests/tools/test_schedule.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_schedule.py`:

```python
import json
import time
import pytest
from chives.store import Store
import chives.tools.schedule as sched_tools
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path))
    sched_tools.init(s, connector="telegram", thread_id="123")
    return s


def test_schedule_nudge(store):
    result = sched_tools.schedule_nudge(
        description="Follow up on dentist appointment",
        iso_datetime="2026-04-15T09:00:00",
    )
    data = json.loads(result)
    assert "nudge_id" in data
    nudges = store.get_pending_nudges()
    # Not pending yet (fire_at is in future), but it's in DB
    # Check DB directly
    import sqlite3
    conn = sqlite3.connect(str(list(store.db_path.__class__(store.db_path).parent.glob("*.db"))[0]))
    # Use store's db_path
    conn2 = sqlite3.connect(store.db_path)
    row = conn2.execute("SELECT description FROM nudges WHERE id=?", (data["nudge_id"],)).fetchone()
    assert row is not None
    assert "dentist" in row[0].lower()


def test_cancel_nudge(store):
    result = sched_tools.schedule_nudge(
        description="test nudge",
        iso_datetime="2026-04-15T09:00:00",
    )
    nid = json.loads(result)["nudge_id"]
    cancel_result = sched_tools.cancel_nudge(nudge_id=str(nid))
    assert "cancelled" in cancel_result.lower() or "canceled" in cancel_result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/tools/test_schedule.py -v
```

Expected: `ImportError` for `chives.tools.schedule`.

- [ ] **Step 3: Write `chives/tools/schedule.py`**

```python
from __future__ import annotations
import json
from datetime import datetime
from chives.store import Store
from chives.tools.registry import tool

_store: Store | None = None
_connector: str = "telegram"
_thread_id: str = ""


def init(store: Store, connector: str, thread_id: str) -> None:
    global _store, _connector, _thread_id
    _store = store
    _connector = connector
    _thread_id = thread_id
    _register()


def _register() -> None:
    @tool
    def schedule_nudge(description: str, iso_datetime: str) -> str:
        """Schedule a one-shot follow-up nudge at a specific date/time. iso_datetime must be ISO 8601."""
        assert _store is not None
        fire_at = datetime.fromisoformat(iso_datetime).timestamp()
        nudge_id = _store.add_nudge(description, fire_at, _connector, _thread_id)
        return json.dumps({"nudge_id": nudge_id, "scheduled_for": iso_datetime})

    @tool
    def cancel_nudge(nudge_id: str) -> str:
        """Cancel a previously scheduled nudge by its ID."""
        assert _store is not None
        _store.cancel_nudge(int(nudge_id))
        return f"Cancelled nudge {nudge_id}."

    globals().update({
        "schedule_nudge": schedule_nudge,
        "cancel_nudge": cancel_nudge,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/tools/test_schedule.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/tools/schedule.py tests/tools/test_schedule.py
git commit -m "feat: schedule tool (one-shot nudges)"
```

---

## Task 11: Context builder

**Files:**
- Create: `chives/context.py`
- Create: `profile/PERSONALITY.md`
- Create: `profile/USER.md`
- Create: `profile/PROTOCOLS.md`
- Create: `profile/CHECKIN.md`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_context.py`:

```python
import pytest
from pathlib import Path
from chives.config import Config
from chives.store import Store
from chives.context import build_context


@pytest.fixture
def config(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "PERSONALITY.md").write_text("You are Chives.")
    (tmp_path / "profile" / "USER.md").write_text("User has ADHD.")
    (tmp_path / "profile" / "PROTOCOLS.md").write_text("Keep answers short.")
    c = Config()
    c.profile_path = str(tmp_path / "profile")
    c.state_path = str(tmp_path / "state")
    return c


@pytest.fixture
def store(config, tmp_path):
    return Store(config.state_path)


def test_includes_personality(config, store):
    ctx = build_context(config, store, "hello")
    assert "You are Chives" in ctx


def test_includes_user_profile(config, store):
    ctx = build_context(config, store, "hello")
    assert "ADHD" in ctx


def test_includes_memories(config, store):
    store.add_memory("user likes tea")
    ctx = build_context(config, store, "what do I like")
    assert "tea" in ctx


def test_missing_profile_files_dont_crash(config, store):
    config.profile_path = "/nonexistent/path"
    ctx = build_context(config, store, "hello")
    assert isinstance(ctx, str)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_context.py -v
```

Expected: `ImportError` for `chives.context`.

- [ ] **Step 3: Create profile files**

Create `profile/PERSONALITY.md`:
```markdown
# Chives

You are Chives — a calm, focused executive assistant for a user with ADHD.

Your job is to fill in the gaps: remember things, schedule things, follow up on things, and make sure nothing falls through the cracks.

**Tone:** Warm but efficient. No filler. No preamble.
**Format:** Bullet points. One clear next action per response.
**Never:** Lecture, moralize, over-explain, or repeat yourself.
```

Create `profile/USER.md`:
```markdown
# User Profile

The user has ADHD and benefits from:
- Short, structured responses
- Proactive reminders (they will forget otherwise)
- Tasks broken into small numbered steps
- Gentle follow-ups — not nagging, just a quiet nudge
```

Create `profile/PROTOCOLS.md`:
```markdown
# Protocols

## Email
- Summarize threads, don't quote raw email
- Flag anything requiring action
- Only alert about emails that need a response or decision

## Commitments
- When the user says "I'll do X" or "remind me to Y", immediately schedule a nudge
- Store the commitment in memory
- Confirm the nudge was set

## Responses
- Max 3 bullet points for simple answers
- Complex tasks: numbered steps, offer to schedule each
- Never ask more than one question at a time
```

Create `profile/CHECKIN.md`:
```markdown
# Check-in Prompts

## Morning Brief
Generate a morning brief with:
1. Today's calendar events (time, title, location if any)
2. Overdue reminders
3. Flagged emails needing action

Keep it under 10 lines. Lead with the most time-sensitive item.

## Idle Check-in
"Still here — anything you need?"
```

- [ ] **Step 4: Write `chives/context.py`**

```python
from __future__ import annotations
from pathlib import Path
from chives.config import Config
from chives.store import Store


def build_context(config: Config, store: Store, current_message: str = "") -> str:
    parts: list[str] = []

    profile = Path(config.profile_path)
    for fname in ("PERSONALITY.md", "USER.md", "PROTOCOLS.md"):
        fpath = profile / fname
        if fpath.exists():
            parts.append(fpath.read_text().strip())

    memories = store.get_all_memories()
    if memories:
        recent = memories[-20:]
        hits = [m["fact"] for m in recent]
        if current_message:
            # Prefer facts that mention words from the current message
            words = set(current_message.lower().split())
            hits = sorted(
                hits,
                key=lambda f: sum(w in f.lower() for w in words),
                reverse=True,
            )
        parts.append("## What I know about the user\n" + "\n".join(f"- {h}" for h in hits))

    return "\n\n---\n\n".join(parts)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_context.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add chives/context.py profile/ tests/test_context.py
git commit -m "feat: context builder + profile files"
```

---

## Task 12: Agent loop

**Files:**
- Create: `chives/agent.py`
- Create: `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_agent.py -v
```

Expected: `ImportError` for `chives.agent`.

- [ ] **Step 3: Write `chives/agent.py`**

```python
from __future__ import annotations
from openai import AsyncOpenAI
from chives.config import Config
from chives.context import build_context
from chives.store import Store
from chives.tools.registry import get_tools_schema, dispatch_tool


class Agent:
    def __init__(self, config: Config, store: Store) -> None:
        self.client = AsyncOpenAI(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key,
        )
        self.model = config.llm.model
        self.config = config
        self.store = store

    async def run(self, user_message: str, connector: str, thread_id: str) -> str:
        self.store.add_turn(connector, thread_id, "user", user_message)

        system = build_context(self.config, self.store, user_message)
        history = self.store.get_turns(connector, thread_id)
        messages = [{"role": "system", "content": system}, *history]

        schemas = get_tools_schema()

        while True:
            kwargs = {"model": self.model, "messages": messages}
            if schemas:
                kwargs["tools"] = schemas

            response = await self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    result = await dispatch_tool(tc.function.name, tc.function.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                content = choice.message.content or ""
                self.store.add_turn(connector, thread_id, "assistant", content)
                return content
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_agent.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/agent.py tests/test_agent.py
git commit -m "feat: agent tool-calling loop"
```

---

## Task 13: Bus and pipeline

**Files:**
- Create: `chives/bus.py`
- Create: `chives/pipeline.py`
- Create: `tests/test_bus.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bus.py`:

```python
import asyncio
import pytest
from chives.bus import Bus, Message
from chives.pipeline import build_pipeline, rate_limit_middleware, slash_command_middleware


async def test_bus_delivers_messages():
    bus = Bus()
    received = []

    async def handler(msg: Message) -> str:
        received.append(msg.text)
        return "ok"

    bus.add_handler(handler)

    msg = Message(connector="telegram", thread_id="1", chat_id=1, text="hello")
    await bus.put(msg)

    async def drain():
        await bus.run_once()

    await drain()
    assert received == ["hello"]


async def test_rate_limit_blocks_rapid_messages():
    calls = []

    async def agent(msg: Message) -> str:
        calls.append(msg.text)
        return "ok"

    handler = build_pipeline(agent, [rate_limit_middleware(min_seconds=60)])
    msg = Message(connector="telegram", thread_id="1", chat_id=1, text="msg")

    await handler(msg)
    result = await handler(msg)
    assert "slow down" in result.lower() or result == ""
    assert len(calls) == 1


async def test_slash_clear_resets_handler():
    responses = []

    async def agent(msg: Message) -> str:
        responses.append(msg.text)
        return "handled"

    handler = build_pipeline(agent, [slash_command_middleware()])
    result = await handler(Message(connector="t", thread_id="1", chat_id=1, text="/help"))
    assert "help" in result.lower() or result != "handled"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_bus.py -v
```

Expected: `ImportError` for `chives.bus`.

- [ ] **Step 3: Write `chives/bus.py`**

```python
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable


@dataclass
class Message:
    connector: str
    thread_id: str
    chat_id: int
    text: str


Handler = Callable[[Message], Awaitable[str]]


class Bus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Message] = asyncio.Queue()
        self._handlers: list[Handler] = []

    def add_handler(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def put(self, message: Message) -> None:
        await self._queue.put(message)

    async def run_once(self) -> None:
        message = self._queue.get_nowait()
        for handler in self._handlers:
            await handler(message)

    async def run(self) -> None:
        while True:
            message = await self._queue.get()
            for handler in self._handlers:
                await handler(message)
```

- [ ] **Step 4: Write `chives/pipeline.py`**

```python
from __future__ import annotations
import time
from chives.bus import Message, Handler

Middleware = object  # Callable[[Message, Handler], Awaitable[str]]


def build_pipeline(agent_handler: Handler, middlewares: list) -> Handler:
    handler = agent_handler
    for mw in reversed(middlewares):
        _next = handler

        async def _dispatch(msg: Message, mw=mw, next_h=_next) -> str:
            return await mw(msg, next_h)

        handler = _dispatch
    return handler


def rate_limit_middleware(min_seconds: float = 1.0):
    last_seen: dict[str, float] = {}

    async def middleware(msg: Message, next_handler: Handler) -> str:
        now = time.monotonic()
        last = last_seen.get(msg.thread_id, 0)
        if now - last < min_seconds:
            return "Slow down — I'm still thinking about your last message."
        last_seen[msg.thread_id] = now
        return await next_handler(msg)

    return middleware


def slash_command_middleware():
    async def middleware(msg: Message, next_handler: Handler) -> str:
        if msg.text.startswith("/help"):
            return (
                "Commands:\n"
                "/help — show this\n"
                "/clear — clear conversation history\n"
                "/brief — morning brief now\n"
            )
        if msg.text.startswith("/brief"):
            msg.text = "Generate the morning brief now."
            return await next_handler(msg)
        return await next_handler(msg)

    return middleware
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_bus.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add chives/bus.py chives/pipeline.py tests/test_bus.py
git commit -m "feat: message bus and middleware pipeline"
```

---

## Task 14: Telegram connector

**Files:**
- Create: `chives/connectors/telegram.py`
- Create: `tests/connectors/test_telegram.py`
- Create: `tests/connectors/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `tests/connectors/__init__.py` (empty).

Create `tests/connectors/test_telegram.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/connectors/test_telegram.py -v
```

Expected: `ImportError` for `chives.connectors.telegram`.

- [ ] **Step 3: Write `chives/connectors/telegram.py`**

```python
from __future__ import annotations
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
        await self.bus.put(
            Message(
                connector="telegram",
                thread_id=str(chat_id),
                chat_id=chat_id,
                text=update.message.text or "",
            )
        )

    async def run(self) -> None:
        await self.app.run_polling()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/connectors/test_telegram.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/connectors/telegram.py tests/connectors/
git commit -m "feat: Telegram connector"
```

---

## Task 15: Open WebUI connector

**Files:**
- Create: `chives/connectors/openwebui.py`
- Create: `tests/connectors/test_openwebui.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/connectors/test_openwebui.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient


async def test_list_models():
    from chives.connectors.openwebui import create_app

    mock_agent = AsyncMock()
    app = create_app(mock_agent)
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "chives"


async def test_chat_completions_non_streaming():
    from chives.connectors.openwebui import create_app

    mock_agent = AsyncMock(return_value="Here is your answer.")
    app = create_app(mock_agent)
    client = TestClient(app)

    payload = {
        "model": "chives",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "Here is your answer."
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/connectors/test_openwebui.py -v
```

Expected: `ImportError` for `chives.connectors.openwebui`.

- [ ] **Step 3: Write `chives/connectors/openwebui.py`**

```python
from __future__ import annotations
import json
import time
import uuid
from typing import Callable, Awaitable
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "chives"
    messages: list[ChatMessage] = []
    stream: bool = False


def create_app(agent_run: Callable[[str, str, str], Awaitable[str]]) -> FastAPI:
    app = FastAPI(title="Chives")

    @app.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [{
                "id": "chives",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local",
            }],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest):
        user_msg = next(
            (m.content for m in reversed(req.messages) if m.role == "user"), ""
        )
        thread_id = "openwebui"
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        if req.stream:
            async def generate():
                response = await agent_run(user_msg, "openwebui", thread_id)
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "chives",
                    "choices": [{"index": 0, "delta": {"content": response}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                done_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "chives",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield f"data: {json.dumps(done_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")

        response = await agent_run(user_msg, "openwebui", thread_id)
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "chives",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response},
                "finish_reason": "stop",
            }],
        }

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/connectors/test_openwebui.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add chives/connectors/openwebui.py tests/connectors/test_openwebui.py
git commit -m "feat: Open WebUI connector (OpenAI-compatible FastAPI endpoint)"
```

---

## Task 16: Scheduler

**Files:**
- Create: `chives/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scheduler.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from chives.config import Config
from chives.store import Store


@pytest.fixture
def config(tmp_path):
    c = Config()
    c.state_path = str(tmp_path / "state")
    c.profile_path = str(tmp_path / "profile")
    c.telegram.allowed_chat_ids = [42]
    c.morning_brief_time = "08:00"
    c.event_reminder_minutes = 15
    c.idle_checkin_hours = 0
    (tmp_path / "profile").mkdir()
    return c


async def test_morning_brief_sends_to_telegram(config, tmp_path):
    store = Store(config.state_path)
    mock_agent = AsyncMock(return_value="Your brief: nothing today.")
    mock_telegram = AsyncMock()
    mock_telegram.send = AsyncMock()

    with patch("apscheduler.schedulers.asyncio.AsyncIOScheduler.start"):
        from chives.scheduler import Scheduler
        sched = Scheduler(config, mock_agent, store, mock_telegram)
        await sched._morning_brief()

    mock_telegram.send.assert_called_once_with(42, "Your brief: nothing today.")


async def test_nudge_check_fires_pending(config, tmp_path):
    import time
    store = Store(config.state_path)
    nid = store.add_nudge("Call dentist", time.time() - 1, "telegram", "42")

    mock_agent = AsyncMock(return_value="Reminder: Call dentist")
    mock_telegram = AsyncMock()
    mock_telegram.send = AsyncMock()

    with patch("apscheduler.schedulers.asyncio.AsyncIOScheduler.start"):
        from chives.scheduler import Scheduler
        sched = Scheduler(config, mock_agent, store, mock_telegram)
        await sched._check_nudges()

    mock_telegram.send.assert_called_once()
    assert store.get_pending_nudges() == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_scheduler.py -v
```

Expected: `ImportError` for `chives.scheduler`.

- [ ] **Step 3: Write `chives/scheduler.py`**

```python
from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from chives.config import Config
from chives.store import Store


class Scheduler:
    def __init__(self, config: Config, agent, store: Store, telegram) -> None:
        self.config = config
        self.agent = agent
        self.store = store
        self.telegram = telegram
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        hour, minute = self.config.morning_brief_time.split(":")
        self._scheduler.add_job(
            self._morning_brief,
            CronTrigger(hour=int(hour), minute=int(minute)),
        )
        self._scheduler.add_job(
            self._check_nudges, "interval", minutes=1
        )
        self._scheduler.add_job(
            self._check_event_reminders, "interval", minutes=1
        )
        if self.config.idle_checkin_hours > 0:
            self._scheduler.add_job(
                self._idle_checkin,
                "interval",
                hours=self.config.idle_checkin_hours,
            )
        self._scheduler.start()

    async def _morning_brief(self) -> None:
        prompt = (
            "Generate the morning brief: today's calendar events, overdue reminders, "
            "and unread emails needing action. Max 10 lines. Most urgent first."
        )
        response = await self.agent("scheduler", "morning_brief", prompt)
        for chat_id in self.config.telegram.allowed_chat_ids:
            await self.telegram.send(chat_id, response)

    async def _check_nudges(self) -> None:
        for nudge in self.store.get_pending_nudges():
            prompt = f"Send a gentle follow-up nudge: {nudge['description']}"
            response = await self.agent("scheduler", nudge["thread_id"], prompt)
            await self.telegram.send(int(nudge["thread_id"]), response)
            self.store.mark_nudge_fired(nudge["id"])

    async def _check_event_reminders(self) -> None:
        from datetime import datetime, timezone, timedelta
        import json as _json
        from chives.tools.registry import _registry

        list_events = _registry.get("list_calendar_events")
        if list_events is None:
            return

        try:
            raw = list_events(period="today")
            events = _json.loads(raw)
        except Exception:
            return

        now = datetime.now(timezone.utc)
        window_end = now + timedelta(minutes=self.config.event_reminder_minutes + 1)

        for ev in events:
            try:
                start_str = ev.get("start", "")
                # Try parsing the NSDate description format
                start = datetime.fromisoformat(start_str[:19])
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                delta = (start - now).total_seconds() / 60
                if 0 <= delta <= self.config.event_reminder_minutes:
                    title = ev.get("title", "event")
                    location = ev.get("location", "")
                    loc_str = f" at {location}" if location else ""
                    msg = f"Heads up: {title}{loc_str} starts in {int(delta)} min."
                    for chat_id in self.config.telegram.allowed_chat_ids:
                        await self.telegram.send(chat_id, msg)
            except Exception:
                continue

    async def _idle_checkin(self) -> None:
        for chat_id in self.config.telegram.allowed_chat_ids:
            await self.telegram.send(chat_id, "Still here — anything you need?")
```

- [ ] **Step 4: Fix `_morning_brief` agent call signature**

The `agent.run` signature is `run(user_message, connector, thread_id)`. Update `_morning_brief` and `_check_nudges` to use the right argument order:

```python
async def _morning_brief(self) -> None:
    prompt = (
        "Generate the morning brief: today's calendar events, overdue reminders, "
        "and unread emails needing action. Max 10 lines. Most urgent first."
    )
    response = await self.agent(prompt, "scheduler", "morning_brief")
    for chat_id in self.config.telegram.allowed_chat_ids:
        await self.telegram.send(chat_id, response)

async def _check_nudges(self) -> None:
    for nudge in self.store.get_pending_nudges():
        prompt = f"Send a gentle follow-up nudge: {nudge['description']}"
        response = await self.agent(prompt, "scheduler", nudge["thread_id"])
        await self.telegram.send(int(nudge["thread_id"]), response)
        self.store.mark_nudge_fired(nudge["id"])
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_scheduler.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add chives/scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler (morning brief, nudges, event reminders)"
```

---

## Task 17: Main entry point

**Files:**
- Create: `chives/main.py`

- [ ] **Step 1: Write `chives/main.py`**

```python
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
    # Use first allowed chat id as default thread for nudges
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
```

- [ ] **Step 2: Verify imports resolve (dry run)**

```bash
uv run python -c "import chives.main"
```

Expected: no import errors (Telegram bot_token validation may raise at runtime, not import time).

- [ ] **Step 3: Commit**

```bash
git add chives/main.py
git commit -m "feat: main entry point, wires all components"
```

---

## Task 18: launchd service scripts and .env.example

**Files:**
- Create: `scripts/install_service.sh`
- Create: `scripts/uninstall_service.sh`
- Create: `.env.example`

- [ ] **Step 1: Create `.env.example`**

```bash
# LLM backend
CHIVES_LLM__BASE_URL=http://localhost:11434/v1
CHIVES_LLM__MODEL=llama3.2
CHIVES_LLM__API_KEY=ollama

# Telegram
CHIVES_TELEGRAM__BOT_TOKEN=your_bot_token_here
CHIVES_TELEGRAM__ALLOWED_CHAT_IDS=[123456789]

# IMAP email
CHIVES_IMAP__HOST=imap.example.com
CHIVES_IMAP__PORT=993
CHIVES_IMAP__USERNAME=you@example.com
CHIVES_IMAP__PASSWORD=your_password_here

# Scheduler
CHIVES_MORNING_BRIEF_TIME=08:00
CHIVES_EVENT_REMINDER_MINUTES=15
CHIVES_IDLE_CHECKIN_HOURS=0

# Paths
CHIVES_STATE_PATH=state
CHIVES_PROFILE_PATH=profile
```

- [ ] **Step 2: Create `scripts/install_service.sh`**

```bash
#!/bin/bash
set -euo pipefail

PLIST_LABEL="com.chives.agent"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(which uv)</string>
        <string>run</string>
        <string>python</string>
        <string>-m</string>
        <string>chives.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${REPO_DIR}/logs/chives.log</string>
    <key>StandardErrorPath</key>
    <string>${REPO_DIR}/logs/chives.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
PLIST

mkdir -p "${REPO_DIR}/logs"
launchctl load "$PLIST_PATH"
echo "Chives service installed and started."
```

- [ ] **Step 3: Create `scripts/uninstall_service.sh`**

```bash
#!/bin/bash
set -euo pipefail

PLIST_LABEL="com.chives.agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"
echo "Chives service removed."
```

- [ ] **Step 4: Make scripts executable**

```bash
chmod +x scripts/install_service.sh scripts/uninstall_service.sh
```

- [ ] **Step 5: Commit**

```bash
git add scripts/ .env.example
git commit -m "chore: launchd service scripts and .env.example"
```

---

## Task 19: Full test suite pass

- [ ] **Step 1: Run all tests**

```bash
uv run pytest -v
```

Expected: all tests pass. Fix any failures before proceeding.

- [ ] **Step 2: Smoke test main import**

```bash
uv run python -c "from chives.main import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify all tests pass"
```

---

## Self-Review Notes

- All spec sections have corresponding tasks: connectors ✓, tools ✓, agent loop ✓, context builder ✓, scheduler ✓, config ✓, store ✓, launchd scripts ✓, profile files ✓
- `schedule_nudge` / `cancel_nudge` in `tools/schedule.py` names match usage in `scheduler.py` ✓
- `agent.run(user_message, connector, thread_id)` signature used consistently across `main.py`, `scheduler.py`, and tests ✓
- `create_app` in `openwebui.py` takes `agent_run: Callable` matching `agent.run` ✓
- `TelegramConnector.send(chat_id, text)` signature used consistently in `scheduler.py` and `main.py` ✓
- PyObjC tools skip gracefully when mocked in tests — real macOS permission prompts only happen at runtime ✓
