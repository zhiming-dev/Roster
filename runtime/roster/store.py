"""SQLite persistence — conversations and their full event streams.

Embedded SQLite via the stdlib :mod:`sqlite3`. Every conversation (= one run) and
every bus event it produced is persisted so the dashboard can list past chats in a
sidebar and reopen one to view its transcript and inter-agent activity.

All DB work runs in a worker thread through :func:`asyncio.to_thread`, so the FastAPI
event loop never blocks on disk I/O. The single shared connection is opened with
``check_same_thread=False`` and guarded by a lock.

The DB file location is configurable with ``ROSTER_DB_PATH`` (legacy
``CONCLAVE_DB_PATH``), defaulting to ``data/roster.db`` — the path mounted as a Docker
volume in ``docker-compose.yml`` so history survives container restarts.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "data/roster.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    ts              REAL NOT NULL,
    kind            TEXT NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_conv ON events(conversation_id, seq);
"""

# Bus event kinds that are pure UI noise and not worth persisting.
_SKIP_KINDS = frozenset({"run.started"})

_WS_RE = re.compile(r"\s+")


def db_path() -> Path:
    """Resolve the SQLite file path from env, defaulting to ``data/roster.db``."""
    raw = os.environ.get("ROSTER_DB_PATH") or os.environ.get(
        "CONCLAVE_DB_PATH", DEFAULT_DB_PATH
    )
    return Path(raw).resolve()


def _derive_title(content: str) -> str:
    text = _WS_RE.sub(" ", (content or "").strip())
    if len(text) > 60:
        text = text[:60].rstrip() + "…"
    return text or "New conversation"


class Store:
    """Thread-safe SQLite wrapper. Sync internals; async public surface."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- sync internals (each acquires the lock; run via asyncio.to_thread) ---

    def _ensure_conversation(self, conv_id: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO conversations (id, title, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?)",
                (conv_id, now, now),
            )
            self._conn.commit()

    def _add_event(self, conv_id: str, evt: dict[str, Any]) -> None:
        kind = str(evt.get("kind") or "event")
        if kind in _SKIP_KINDS:
            return
        ts = float(evt.get("ts") or time.time())
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO conversations (id, title, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?)",
                (conv_id, now, now),
            )
            self._conn.execute(
                "INSERT INTO events (conversation_id, ts, kind, payload) "
                "VALUES (?, ?, ?, ?)",
                (conv_id, ts, kind, json.dumps(evt, ensure_ascii=False)),
            )
            # Title comes from the first principal message; updated_at always bumps.
            if kind == "user.message":
                row = self._conn.execute(
                    "SELECT title FROM conversations WHERE id = ?", (conv_id,)
                ).fetchone()
                if row is not None and not row["title"]:
                    self._conn.execute(
                        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                        (_derive_title(str(evt.get("content", ""))), ts, conv_id),
                    )
                else:
                    self._conn.execute(
                        "UPDATE conversations SET updated_at = ? WHERE id = ?",
                        (ts, conv_id),
                    )
            else:
                self._conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conv_id)
                )
            self._conn.commit()

    def _list_conversations(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at,
                       (SELECT COUNT(*) FROM events e
                          WHERE e.conversation_id = c.id
                            AND e.kind = 'user.message') AS messages
                  FROM conversations c
                 ORDER BY c.updated_at DESC
                """
            ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"] or "New conversation",
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "messages": r["messages"],
            }
            for r in rows
            # Hide empty shells (a run created but never used).
            if r["messages"] or r["title"]
        ]

    def _get_events(self, conv_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM events WHERE conversation_id = ? ORDER BY seq",
                (conv_id,),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def _exists(self, conv_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
        return row is not None

    def _delete(self, conv_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM events WHERE conversation_id = ?", (conv_id,)
            )
            self._conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            self._conn.commit()

    def _close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- async public surface ------------------------------------------------

    async def ensure_conversation(self, conv_id: str) -> None:
        await asyncio.to_thread(self._ensure_conversation, conv_id)

    async def add_event(self, conv_id: str, evt: dict[str, Any]) -> None:
        await asyncio.to_thread(self._add_event, conv_id, evt)

    async def list_conversations(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_conversations)

    async def get_events(self, conv_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_events, conv_id)

    async def exists(self, conv_id: str) -> bool:
        return await asyncio.to_thread(self._exists, conv_id)

    async def delete_conversation(self, conv_id: str) -> None:
        await asyncio.to_thread(self._delete, conv_id)

    async def aclose(self) -> None:
        await asyncio.to_thread(self._close)
