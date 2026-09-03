"""Locating bundled resource files (application icon, ...).

Works from a source checkout, an installed package and a PyInstaller bundle,
which unpacks its data files next to ``sys._MEIPASS``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ICON_NAME = "audiflix.ico"


def resource_dir() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidate = Path(bundled) / "resources"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent / "resources"


def app_icon_path() -> Path | None:
    """Path of the application icon, or ``None`` when it is not bundled."""
    path = resource_dir() / ICON_NAME
    return path if path.is_file() else None
