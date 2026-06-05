"""MessageStore — SQLite-backed cache for MAP message handles.

Keyed by OBEX message path (the 'path' key from poll_inbox()).
Used by MapBackend to filter polled messages down to only new ones
on each poll cycle and across daemon restarts (incremental reconciliation
for tincan-vehs).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class MessageStore:
    """Persist seen message handles in a local SQLite database.

    On first connect the cache is empty, so all polled messages are
    treated as new (same behaviour as today).  On subsequent polls —
    and after daemon restarts — only handles not yet in the DB are
    returned by filter_new(), eliminating duplicate signals and
    notification replay for historical messages.
    """

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS messages (
            handle      TEXT PRIMARY KEY,
            conv_id     TEXT NOT NULL DEFAULT '',
            timestamp   TEXT NOT NULL DEFAULT '',
            seen_at     REAL NOT NULL
        ) STRICT;
    """

    def __init__(self, db_path: str | Path) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute(self._SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def contains(self, handle: str) -> bool:
        """Return True if *handle* is already recorded in the store."""
        row = self._conn.execute(
            "SELECT 1 FROM messages WHERE handle = ?", (handle,)
        ).fetchone()
        return row is not None

    def is_empty(self) -> bool:
        """Return True when the store has no recorded handles."""
        return self._conn.execute("SELECT 1 FROM messages LIMIT 1").fetchone() is None

    def filter_new(self, messages: list[dict]) -> list[dict]:
        """Return only messages whose 'path' handle is not in the store."""
        return [m for m in messages if not self.contains(m.get("path", ""))]

    def add_messages(self, messages: list[dict]) -> None:
        """Insert messages by 'path' handle.  Already-known handles are ignored."""
        now = time.time()
        self._conn.executemany(
            "INSERT OR IGNORE INTO messages (handle, conv_id, timestamp, seen_at) "
            "VALUES (?, ?, ?, ?)",
            [
                (
                    m.get("path", ""),
                    m.get("sender", ""),
                    m.get("timestamp", ""),
                    now,
                )
                for m in messages
                if m.get("path")
            ],
        )
        self._conn.commit()
