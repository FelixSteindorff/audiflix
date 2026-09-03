"""Downloaded titles: the folder layout and its manifest.

A downloaded title is a folder in the download directory holding one file per
audio file of the book plus ``audiflix.json``, the manifest:

.. code-block:: json

    {
      "version": 1,
      "item_id": "li_abc",
      "title": "A Book",
      "duration": 3600.0,
      "tracks": [{"file": "01.m4b", "ino": "123", "start_offset": 0.0,
                  "duration": 3600.0}],
      "chapters": [{"start": 0.0, "end": 60.0, "title": "One"}],
      "position": 0.0,
      "position_synced": true
    }

The manifest is what makes a download playable without a server: it carries the
track order and the chapter marks, which otherwise only come from the playback
session. ``position`` is the last position played offline and is pushed to the
server as soon as it can be reached again.

Nothing secret is written here - no token, no user name - because the download
directory is an ordinary folder the user may copy anywhere.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from audiflix.helpers.text import safe_file_name
from audiflix.logging_setup import get_logger

log = get_logger(__name__)

MANIFEST_NAME = "audiflix.json"
MANIFEST_VERSION = 1


def folder_for(download_dir: str | os.PathLike[str], title: str, item_id: str) -> Path:
    """Folder a title is downloaded into (not created).

    Two different books can carry the same title - a library with several
    editions of one work, most of all. When the obvious folder already holds a
    *different* title, the item id is appended rather than overwriting it. The
    same item always resolves to the same folder, so downloading it again
    replaces its own files.
    """
    base = Path(download_dir) / safe_file_name(title, fallback=item_id or "download")
    existing = read_manifest(base)
    if existing is None or existing.get("item_id") in (item_id, None):
        return base
    suffix = safe_file_name(item_id, fallback="2")[:12]
    return base.with_name(f"{base.name}-{suffix}")


def manifest_path(folder: str | os.PathLike[str]) -> Path:
    return Path(folder) / MANIFEST_NAME


def track_file_name(index: int, extension: str) -> str:
    """File name for track ``index``, numbered so the order stays visible."""
    return f"{index + 1:03d}{extension or '.mp3'}"


def write_manifest(
    folder: str | os.PathLike[str],
    item_id: str,
    title: str,
    duration: float,
    tracks: list[dict[str, Any]],
    chapters: list[dict[str, Any]] | None = None,
) -> Path:
    """Write the manifest of a finished download."""
    data = {
        "version": MANIFEST_VERSION,
        "item_id": item_id,
        "title": title,
        "duration": float(duration or 0.0),
        "tracks": tracks,
        "chapters": chapters or [],
        "position": 0.0,
        "position_synced": True,
    }
    return _write(folder, data)


def read_manifest(folder: str | os.PathLike[str]) -> dict[str, Any] | None:
    """Read the manifest, or ``None`` when it is missing or unreadable."""
    path = manifest_path(folder)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read %s (%s)", path, exc)
        return None
    if not isinstance(data, dict) or not data.get("tracks"):
        log.warning("%s is not a usable manifest", path)
        return None
    return data


def _write(folder: str | os.PathLike[str], data: dict[str, Any]) -> Path:
    path = manifest_path(folder)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def is_complete(folder: str | os.PathLike[str]) -> bool:
    """True when the manifest is present and every file it lists exists."""
    manifest = read_manifest(folder)
    if manifest is None:
        return False
    base = Path(folder)
    return all((base / track.get("file", "")).exists() for track in manifest["tracks"])


def local_tracks(folder: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Player tracks pointing at the downloaded files.

    Returns an empty list when a file is missing, so a half-deleted download
    falls back to streaming instead of failing halfway through the book.
    """
    manifest = read_manifest(folder)
    if manifest is None:
        return []
    base = Path(folder)
    tracks = []
    for track in manifest["tracks"]:
        path = base / track.get("file", "")
        if not path.exists():
            log.warning("Downloaded file %s is missing - streaming instead", path)
            return []
        tracks.append(
            {
                "content_url": str(path),
                "url": str(path),
                "start_offset": float(track.get("start_offset") or 0.0),
                "duration": float(track.get("duration") or 0.0),
                "local": True,
            }
        )
    return tracks


def update_position(
    folder: str | os.PathLike[str], position: float, synced: bool
) -> None:
    """Remember where the listener is in a downloaded title.

    ``synced=False`` marks the position as still owed to the server, which is
    the normal case while offline.
    """
    manifest = read_manifest(folder)
    if manifest is None:
        return
    manifest["position"] = float(max(0.0, position))
    manifest["position_synced"] = bool(synced)
    try:
        _write(folder, manifest)
    except OSError as exc:
        log.warning("Could not record the offline position in %s (%s)", folder, exc)


def pending_position(folder: str | os.PathLike[str]) -> float | None:
    """Position that was played offline and never reached the server."""
    manifest = read_manifest(folder)
    if manifest is None or manifest.get("position_synced", True):
        return None
    position = float(manifest.get("position") or 0.0)
    return position if position > 0 else None


def remove(folder: str | os.PathLike[str]) -> bool:
    """Delete a downloaded title. True when the folder is gone afterwards."""
    path = Path(folder)
    if not path.exists():
        return True
    try:
        shutil.rmtree(path)
        return True
    except OSError as exc:
        log.error("Could not delete the download folder %s: %s", path, exc)
        return False


def folder_size(folder: str | os.PathLike[str]) -> int:
    """Bytes used by a downloaded title (0 when it does not exist)."""
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total
