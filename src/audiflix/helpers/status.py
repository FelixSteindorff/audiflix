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
from audiflix.helpers import downloads
from audiflix.logging_setup import get_logger

log = get_logger(__name__)


class DownloadRegistry:
    """Which titles exist locally, and where.

    Two kinds of entry live side by side:

    ``{"folder": "..."}``
        A title downloaded as single audio files plus a manifest. These can be
        played offline (see :mod:`audiflix.helpers.downloads`).

    ``"C:/.../Book.zip"``
        The zip archive Audiflix < 0.3 stored. It cannot be played, so it stays
        a marker only; downloading such a title again replaces the entry with a
        playable folder.
    """

    def __init__(self):
        self._path = config_dir() / "downloads.json"
        self._data: dict[str, Any] = {}
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

    # --- Queries -----------------------------------------------------------
    def is_downloaded(self, item_id: str) -> bool:
        folder = self.folder_for(item_id)
        if folder:
            return downloads.is_complete(folder)
        path = self.path_for(item_id)
        return bool(path) and Path(path).exists()

    def is_playable_offline(self, item_id: str) -> bool:
        """True for a download that can be played without the server."""
        folder = self.folder_for(item_id)
        return bool(folder) and downloads.is_complete(folder)

    def folder_for(self, item_id: str) -> str | None:
        """Folder of a title downloaded as single files, if there is one."""
        entry = self._data.get(item_id)
        if isinstance(entry, dict):
            folder = entry.get("folder")
            return str(folder) if folder else None
        return None

    def path_for(self, item_id: str) -> str | None:
        """Path recorded for a title: the folder, or the legacy zip archive."""
        entry = self._data.get(item_id)
        if isinstance(entry, dict):
            folder = entry.get("folder")
            return str(folder) if folder else None
        return str(entry) if entry else None

    def local_tracks(self, item_id: str) -> list[dict[str, Any]]:
        folder = self.folder_for(item_id)
        return downloads.local_tracks(folder) if folder else []

    def manifest(self, item_id: str) -> dict[str, Any] | None:
        folder = self.folder_for(item_id)
        return downloads.read_manifest(folder) if folder else None

    def items(self) -> list[str]:
        return list(self._data)

    # --- Updates -----------------------------------------------------------
    def mark(self, item_id: str, path: str) -> None:
        """Record a legacy single-file download (a zip archive)."""
        self._data[item_id] = str(path)
        self._save()

    def mark_folder(self, item_id: str, folder: str) -> None:
        """Record a title downloaded as playable single files."""
        self._data[item_id] = {"folder": str(folder)}
        self._save()

    def remove(self, item_id: str) -> None:
        if item_id in self._data:
            del self._data[item_id]
            self._save()

    def delete_files(self, item_id: str) -> bool:
        """Delete the downloaded files and forget the title."""
        folder = self.folder_for(item_id)
        legacy = None if folder else self.path_for(item_id)
        removed = downloads.remove(folder) if folder else True
        if legacy:
            try:
                Path(legacy).unlink(missing_ok=True)
            except OSError as exc:
                log.error("Could not delete %s: %s", legacy, exc)
                removed = False
        if removed:
            self.remove(item_id)
        return removed

    # --- Offline progress --------------------------------------------------
    def record_offline_position(self, item_id: str, position: float) -> None:
        """Remember a position that could not be sent to the server."""
        folder = self.folder_for(item_id)
        if folder:
            downloads.update_position(folder, position, synced=False)

    def clear_offline_position(self, item_id: str, position: float) -> None:
        """Mark the stored position as sent."""
        folder = self.folder_for(item_id)
        if folder:
            downloads.update_position(folder, position, synced=True)

    def pending_positions(self) -> dict[str, float]:
        """Positions played offline that the server does not know about yet."""
        pending: dict[str, float] = {}
        for item_id in self._data:
            folder = self.folder_for(item_id)
            if not folder:
                continue
            position = downloads.pending_position(folder)
            if position is not None:
                pending[item_id] = position
        return pending


class ProgressIndex:
    """Fast access to the user's mediaProgress.

    A podcast has one progress entry *per episode*, all of them carrying the
    same ``libraryItemId``. The index is therefore keyed by item **and**
    episode; without the episode every episode of a podcast would overwrite the
    one before it.
    """

    def __init__(self, user: dict[str, Any] | None = None):
        self._by_item: dict[tuple[str, str], dict[str, Any]] = {}
        if user:
            self.update(user)

    def update(self, user: dict[str, Any]) -> None:
        self._by_item.clear()
        for progress in (user or {}).get("mediaProgress", []) or []:
            item_id = progress.get("libraryItemId")
            if item_id:
                self._by_item[_key(item_id, progress.get("episodeId"))] = progress

    def entry(self, item_id: str, episode_id: str | None = None) -> dict[str, Any] | None:
        return self._by_item.get(_key(item_id, episode_id))

    def progress_for(self, item_id: str, episode_id: str | None = None) -> float:
        progress = self.entry(item_id, episode_id)
        return float(progress.get("progress", 0.0)) if progress else 0.0

    def current_time(self, item_id: str, episode_id: str | None = None) -> float:
        progress = self.entry(item_id, episode_id)
        return float(progress.get("currentTime", 0.0)) if progress else 0.0

    def is_finished(self, item_id: str, episode_id: str | None = None) -> bool:
        progress = self.entry(item_id, episode_id)
        return bool(progress and progress.get("isFinished"))


def _key(item_id: str, episode_id: str | None = None) -> tuple[str, str]:
    return (item_id, episode_id or "")
