"""Durable, account-scoped progress awaiting delivery to Audiobookshelf."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PendingProgress:
    item_id: str
    episode_id: str
    position: float
    duration: float
    finished: bool
    updated_at: int
    revision: str

    def server_is_newer(self, progress: dict | None) -> bool:
        """Latest listening event wins, including an intentional rewind."""
        return bool(progress and int(progress.get("lastUpdate") or 0) > self.updated_at)


class ProgressOutbox:
    """Transactions prevent partial writes and acknowledgements losing new data.

    Each operation owns its connection, so player and UI workers can use this
    object without sharing a SQLite connection across threads.
    """

    def __init__(self, path: Path, server: str, user: str) -> None:
        self.path = path
        identity = json.dumps([server.rstrip("/"), user], ensure_ascii=False)
        self.scope = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        with closing(self._connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS pending (
                scope TEXT NOT NULL, item_id TEXT NOT NULL, episode_id TEXT NOT NULL,
                position REAL NOT NULL, duration REAL NOT NULL, finished INTEGER NOT NULL,
                updated_at INTEGER NOT NULL, revision TEXT NOT NULL,
                PRIMARY KEY (scope, item_id, episode_id))""")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def record(self, item_id: str, episode_id: str | None, position: float,
               duration: float, finished: bool = False, *, updated_at: int | None = None) -> PendingProgress:
        entry = PendingProgress(item_id, episode_id or "", max(0.0, position), max(0.0, duration),
                                finished, updated_at if updated_at is not None else time.time_ns() // 1_000_000,
                                uuid.uuid4().hex)
        with closing(self._connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO pending VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (self.scope, entry.item_id, entry.episode_id, entry.position, entry.duration,
                        entry.finished, entry.updated_at, entry.revision))
        return entry

    def pending(self) -> list[PendingProgress]:
        with closing(self._connect()) as db:
            rows = db.execute("""SELECT item_id, episode_id, position, duration, finished, updated_at, revision
                                 FROM pending WHERE scope = ? ORDER BY updated_at""", (self.scope,)).fetchall()
        return [PendingProgress(*row) for row in rows]

    def contains(self, entry: PendingProgress) -> bool:
        with closing(self._connect()) as db:
            return db.execute("SELECT 1 FROM pending WHERE scope = ? AND revision = ?",
                              (self.scope, entry.revision)).fetchone() is not None

    def acknowledge(self, entry: PendingProgress) -> bool:
        with closing(self._connect()) as db, db:
            return db.execute("DELETE FROM pending WHERE scope = ? AND revision = ?",
                              (self.scope, entry.revision)).rowcount > 0
