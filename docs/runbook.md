# Chives Runbook

## Development Setup

The repo lives at `~/Code/awfulwoman/chives`. The service always runs from this directory — there is no separate deploy copy.

```bash
uv sync                        # install dependencies
cp .env.example .env           # then edit with real credentials
./scripts/install_service.sh   # install as launchd service + grant TCC permissions
```

---

## Service Management

```bash
# Install / reinstall (also re-grants TCC permissions)
./scripts/install_service.sh

# Uninstall
./scripts/uninstall_service.sh

# Restart
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.chives.agent.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.chives.agent.plist

# Check status (PID + last exit code)
launchctl list | grep chives

# Logs
tail -f logs/chives.log   # stdout
tail -f logs/chives.err   # stderr (errors, debug output)
```

Exit code `0` in `launchctl list` = healthy. Non-zero = last run crashed.

---

## Interactive Debugging

Use `scripts/chat.py` to talk to the agent directly without going through Telegram:

```bash
uv run python scripts/chat.py
```

- Tool calls and LLM `finish_reason` print to stderr in real time.
- Uses a separate `cli` thread so it won't pollute Telegram conversation history.
- If the model behaves strangely, check whether stale history is the cause (see below).

To add temporary debug logging to the service itself, add to the top of `chives/main.py`:

```python
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
```

Remove it when done — it floods the logs.

---

## macOS Permissions (TCC)

Chives needs Calendar, Reminders, and Contacts access. `install_service.sh` grants these automatically by writing to `~/Library/Application Support/com.apple.TCC/TCC.db`.

**Two entries are required for each service** — one for `org.python.python` (the Python process) and one for the real path to `uv` (the responsible process that macOS evaluates for launchd agents):

| TCC Service             | Grants access to       |
|-------------------------|------------------------|
| `kTCCServiceCalendar`   | Apple Calendar         |
| `kTCCServiceReminders`  | Apple Reminders        |
| `kTCCServiceAddressBook`| Apple Contacts         |

### Why the dialog never appears

macOS uses a "responsible process" model. When the service runs as a launchd agent, `uv` is the responsible process — not Python. Since `uv` has no `NSCalendarsUsageDescription`, macOS silently refuses to show a permission dialog. The workaround is to write TCC entries directly.

### Why SSH sessions always return `granted: False`

`sshd-keygen-wrapper` becomes the responsible process for any process launched over SSH. macOS auto-denies platform binaries regardless of TCC entries. **Always test EventKit access via Telegram or a GUI terminal, never over SSH.**

### After `brew upgrade uv`

The TCC entry for uv uses the versioned Cellar path (e.g. `/opt/homebrew/Cellar/uv/0.11.7/bin/uv`). After upgrading uv, re-run `install_service.sh` to update the TCC entry.

### Resetting and re-granting manually

```bash
tccutil reset Calendar
tccutil reset Reminders
# Then re-run:
./scripts/install_service.sh
```

---

## Common Problems

### "0 unread emails" / empty reminders when data exists

**Cause A — RFC822 fetch marks emails as read.** The original email tool used `(RFC822)` which sets `\Seen` on the server. Fixed: now uses `(BODY.PEEK[])`.

**Cause B — EKEventStore is cached from before iCloud sync completed.** Restart the service after syncing calendars or reminders for the first time on a new machine.

**Cause C — TCC permission denied.** If running from SSH, always returns empty (see above). From the GUI session, check TCC entries:

```bash
sqlite3 ~/Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT service, client, auth_value FROM access WHERE service LIKE 'kTCCService%';"
```

`auth_value=2` = allowed, `auth_value=0` = denied.

### Model not calling tools / hallucinating data

**Cause A — Poisoned conversation history.** If the model previously gave a wrong answer (e.g. "I don't have calendar access"), it will repeat that from history. Clear the thread:

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from chives.config import Config
from chives.store import Store
import sqlite3
s = Store(Config().state_path)
conn = sqlite3.connect(s.db_path)
conn.execute(\"DELETE FROM turns WHERE connector='telegram'\")
conn.commit(); conn.close()
print('cleared')
"
```

**Cause B — Wrong model.** Not all Ollama models support tool calling. Known working: `qwen3:14b`, `qwen3.5:4b`, `llama3.1`, `llama3.2`. Known broken: `gemma3:4b`.

To check what model is configured: `grep CHIVES_LLM__MODEL .env`

### Service starts then immediately crashes

Check `logs/chives.err`. Common causes:

- **Invalid Telegram token** — `telegram.error.InvalidToken`: wrong or placeholder token in `.env`
- **Port 8080 in use** — another process (often a leftover from a previous crash) is holding the port: `lsof -i :8080`
- **Ollama unreachable** — check `CHIVES_LLM__BASE_URL` in `.env` and that Ollama is running

### `uv` not found during install

```bash
brew install uv
```

---

## Configuration Reference

All settings use the `CHIVES_` prefix with `__` for nesting. See `.env.example` for the full list.

| Key | Description |
|-----|-------------|
| `CHIVES_LLM__BASE_URL` | Ollama endpoint, e.g. `http://192.168.1.150:11434/v1` |
| `CHIVES_LLM__MODEL` | Model name, must support tool calling |
| `CHIVES_TELEGRAM__BOT_TOKEN` | Token from @BotFather |
| `CHIVES_TELEGRAM__ALLOWED_CHAT_IDS` | JSON array of permitted chat IDs |
| `CHIVES_IMAP__HOST/PORT/USERNAME/PASSWORD` | IMAP credentials |
| `CHIVES_MORNING_BRIEF_TIME` | `HH:MM` for daily morning brief |
| `CHIVES_STATE_PATH` | Directory for SQLite db and state (default: `state/`) |
| `CHIVES_PROFILE_PATH` | Directory for personality/user/protocol markdown (default: `profile/`) |
