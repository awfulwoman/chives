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

    def update_memory(self, memory_id: int, fact: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE memory SET fact=? WHERE id=?", (fact, memory_id)
            )
            return cur.rowcount > 0

    def delete_memory(self, memory_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM memory WHERE id=?", (memory_id,))
            return cur.rowcount > 0

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
