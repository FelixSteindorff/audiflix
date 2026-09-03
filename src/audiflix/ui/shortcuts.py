"""Parsing, validating and comparing keyboard shortcuts.

Shortcuts are stored as strings in wx accelerator syntax (``Ctrl+Shift+C``).
``wx.AcceleratorEntry.FromString`` is forgiving to the point of being unusable
for validation - it happily accepts ``Blah+X`` and silently drops the unknown
modifier - so the modifier part is checked here first and only the key itself is
handed to wx.

The normalised ``(flags, keycode)`` pair is also what conflict detection uses,
so ``ctrl+a`` and ``Ctrl+A`` are correctly recognised as the same shortcut.
"""

from __future__ import annotations

import wx

from audiflix.i18n import _

MODIFIERS: dict[str, int] = {
    "ctrl": wx.ACCEL_CTRL,
    "control": wx.ACCEL_CTRL,
    "shift": wx.ACCEL_SHIFT,
    "alt": wx.ACCEL_ALT,
    "cmd": wx.ACCEL_CMD,
    "rawctrl": wx.ACCEL_RAW_CTRL,
}


def split_shortcut(text: str) -> tuple[list[str], str]:
    """Split ``"Ctrl+Shift+C"`` into ``(["Ctrl", "Shift"], "C")``.

    Handles ``Ctrl++`` (the key *is* a plus sign) and a bare ``+``.
    """
    text = (text or "").strip()
    if not text:
        return [], ""
    if text == "+":
        return [], "+"
    if text.endswith("++"):
        return [part for part in text[:-2].split("+") if part], "+"
    parts = text.split("+")
    return [part for part in parts[:-1] if part], parts[-1]


def parse(text: str) -> tuple[int, int] | None:
    """Return ``(flags, keycode)`` for a shortcut string, or ``None`` if invalid."""
    modifiers, key = split_shortcut(text)
    if not key:
        return None
    if len(key) == 1:
        # wx reports different key codes for 'a' and 'A'; normalising here makes
        # "ctrl+a" and "Ctrl+A" the same shortcut for conflict detection.
        key = key.upper()
    flags = 0
    for modifier in modifiers:
        value = MODIFIERS.get(modifier.strip().lower())
        if value is None:
            return None
        flags |= value
    entry = wx.AcceleratorEntry()
    if not entry.FromString(key) or not entry.GetKeyCode():
        return None
    return flags, entry.GetKeyCode()


def is_valid(text: str) -> bool:
    """True when ``text`` is a shortcut wx can install."""
    return parse(text) is not None


def to_entry(text: str, command_id: int) -> wx.AcceleratorEntry | None:
    """Build an :class:`wx.AcceleratorEntry` for ``command_id``."""
    parsed = parse(text)
    if parsed is None:
        return None
    flags, keycode = parsed
    entry = wx.AcceleratorEntry()
    entry.Set(flags, keycode, command_id)
    return entry


def normalize(text: str) -> str | None:
    """Canonical spelling of a shortcut (``ctrl+a`` -> ``Ctrl+A``)."""
    parsed = parse(text)
    if parsed is None:
        return None
    flags, keycode = parsed
    entry = wx.AcceleratorEntry(flags, keycode, wx.ID_ANY)
    return entry.ToString() or text


def find_conflicts(shortcuts: dict[str, str]) -> dict[str, list[str]]:
    """Group action keys that share the same shortcut.

    Returns ``{normalised shortcut: [action, action, ...]}`` containing only
    entries used more than once. Empty (disabled) shortcuts are ignored.
    """
    seen: dict[tuple[int, int], list[str]] = {}
    for action, text in shortcuts.items():
        parsed = parse(text)
        if parsed is None:
            continue
        seen.setdefault(parsed, []).append(action)
    conflicts: dict[str, list[str]] = {}
    for (flags, keycode), actions in seen.items():
        if len(actions) > 1:
            label = wx.AcceleratorEntry(flags, keycode, wx.ID_ANY).ToString()
            conflicts[label] = actions
    return conflicts


def describe(text: str) -> str:
    """Human readable form used in announcements ('not set' when empty)."""
    return normalize(text) or (text or _("not set"))
