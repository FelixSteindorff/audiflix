"""Checking GitHub for a newer Audiflix release, and the diagnostics report.

The check runs **only when the user asks for it** (Help -> Check for updates).
Audiflix never contacts GitHub on its own: the application talks to the user's
own server and to nothing else unless they say so.
"""

from __future__ import annotations

import platform
import re
import sys

import requests

from audiflix import APP_DISPLAY_NAME, __version__
from audiflix.i18n import _
from audiflix.logging_setup import get_logger

log = get_logger(__name__)

RELEASES_API = "https://api.github.com/repos/FelixSteindorff/audiflix/releases/latest"
RELEASES_PAGE = "https://github.com/FelixSteindorff/audiflix/releases"
TIMEOUT = 10


class UpdateCheckError(RuntimeError):
    """The release information could not be fetched."""


def parse_version(text: str) -> tuple[int, ...]:
    """Turn ``"v1.2.3"`` into ``(1, 2, 3)``; unparsable parts become 0.

    Anything after the numbers (``1.2.3-rc1``) is ignored, which is what makes
    a pre-release compare equal to the release it precedes - close enough for
    "is there something newer than what I run".
    """
    numbers = re.findall(r"\d+", (text or "").split("-")[0])
    return tuple(int(n) for n in numbers[:3]) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a higher version than ``current``."""
    return parse_version(candidate) > parse_version(current)


def latest_release() -> dict[str, str]:
    """Fetch the newest published release. Raises :class:`UpdateCheckError`."""
    try:
        response = requests.get(
            RELEASES_API,
            timeout=TIMEOUT,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{APP_DISPLAY_NAME}/{__version__}",
            },
        )
    except requests.RequestException as exc:
        raise UpdateCheckError(_("GitHub could not be reached: %s") % exc) from exc
    if response.status_code != 200:
        raise UpdateCheckError(
            _("GitHub answered with HTTP %d.") % response.status_code
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise UpdateCheckError(_("GitHub sent an answer Audiflix cannot read.")) from exc
    version = str(data.get("tag_name") or data.get("name") or "").strip()
    if not version:
        raise UpdateCheckError(_("GitHub did not report a version."))
    return {
        "version": version,
        "url": str(data.get("html_url") or RELEASES_PAGE),
        "notes": str(data.get("body") or ""),
    }


def check() -> tuple[bool, dict[str, str]]:
    """``(a newer version exists, release information)``."""
    release = latest_release()
    return is_newer(release["version"], __version__), release


def diagnostics(
    server_url: str = "",
    server_version: str = "",
    vlc_version: str = "",
    keyring_backend: str | None = None,
    speech_available: bool = False,
    language: str = "",
) -> str:
    """A short report to paste into a bug report.

    Deliberately free of anything private: no user name, no token, no library
    contents - only what is needed to tell one installation from another.
    """
    lines = [
        f"{APP_DISPLAY_NAME} {__version__}",
        f"Python {sys.version.split()[0]}",
        f"System: {platform.platform()}",
        f"Audio engine: {vlc_version or 'system VLC'}",
        f"Interface language: {language or 'auto'}",
        f"Screen reader output: {'yes' if speech_available else 'no'}",
        f"Credential store: {keyring_backend or 'none'}",
        f"Server reachable at: {'yes' if server_url else 'not signed in'}",
        f"Server version: {server_version or 'unknown'}",
    ]
    return "\n".join(lines)
