"""Status helpers: download registry and progress/finished state.

The download registry remembers which items exist locally (as JSON in
``%APPDATA%/audiflix``). An item's progress is derived from the ``mediaProgress``
of the signed-in user.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from audiflix.config import config_dir
from audiflix.logging_setup import get_logger

log = get_logger(__name__)


class DownloadRegistry:
    """Persistent mapping of item_id -> local path."""

    def __init__(self):
        self._path = config_dir() / "downloads.json"
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read download registry (%s) - starting empty", exc)
            return
        self._data = data if isinstance(data, dict) else {}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            log.error("Could not save download registry: %s", exc)

    def is_downloaded(self, item_id: str) -> bool:
        path = self._data.get(item_id)
        return bool(path) and Path(path).exists()

    def path_for(self, item_id: str) -> str | None:
        return self._data.get(item_id)

    def mark(self, item_id: str, path: str) -> None:
        self._data[item_id] = str(path)
        self._save()

    def remove(self, item_id: str) -> None:
        if item_id in self._data:
            del self._data[item_id]
            self._save()


class ProgressIndex:
    """Fast access to the user's mediaProgress (item_id -> dict)."""

    def __init__(self, user: dict[str, Any] | None = None):
        self._by_item: dict[str, dict[str, Any]] = {}
        if user:
            self.update(user)

    def update(self, user: dict[str, Any]) -> None:
        self._by_item.clear()
        for progress in (user or {}).get("mediaProgress", []) or []:
            item_id = progress.get("libraryItemId")
            if item_id:
                self._by_item[item_id] = progress

    def progress_for(self, item_id: str) -> float:
        progress = self._by_item.get(item_id)
        return float(progress.get("progress", 0.0)) if progress else 0.0

    def current_time(self, item_id: str) -> float:
        progress = self._by_item.get(item_id)
        return float(progress.get("currentTime", 0.0)) if progress else 0.0

    def is_finished(self, item_id: str) -> bool:
        progress = self._by_item.get(item_id)
        return bool(progress and progress.get("isFinished"))
