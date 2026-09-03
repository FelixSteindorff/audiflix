"""Pure text helpers shared by UI and background code.

These functions must stay free of wx and network imports: they are used by the
podcast dialog and the download logic alike, and the test suite exercises them
without a GUI toolkit installed.
"""

from __future__ import annotations

import re

#: Characters Windows forbids in file and folder names, plus control characters.
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Reserved device names on Windows (case-insensitive, with or without suffix).
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MAX_NAME_LENGTH = 120


def safe_folder_name(name: str, fallback: str = "Podcast") -> str:
    """Turn a podcast title into a name that is valid on every file system.

    Illegal characters are removed (not replaced), trailing dots and spaces are
    stripped because Windows silently drops them, and reserved device names are
    prefixed. Returns ``fallback`` when nothing usable remains.
    """
    cleaned = _ILLEGAL_CHARS.sub("", name or "").strip().rstrip(". ")
    cleaned = cleaned[:MAX_NAME_LENGTH].rstrip(". ")
    if not cleaned:
        return fallback
    if cleaned.split(".")[0].upper() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def safe_file_name(name: str, fallback: str = "download") -> str:
    """Like :func:`safe_folder_name` but for files; illegal characters become ``_``."""
    cleaned = _ILLEGAL_CHARS.sub("_", name or "").strip().rstrip(". ")
    cleaned = cleaned[:MAX_NAME_LENGTH].strip().rstrip(". ")
    if not cleaned:
        return fallback
    if cleaned.split(".")[0].upper() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def truncate(text: str, limit: int = 200, ellipsis: str = "...") -> str:
    """Shorten ``text`` for status lines and error messages."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(ellipsis))].rstrip() + ellipsis
