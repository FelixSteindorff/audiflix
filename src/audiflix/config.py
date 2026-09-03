"""Settings, paths and secure token storage for Audiflix.

All persistent data lives in ``%APPDATA%/audiflix`` (or the platform equivalent
config directory).

**Auth tokens are never written to disk by Audiflix.** They are stored through
``keyring`` (Windows Credential Manager, macOS Keychain, Secret Service). If no
keyring backend is available, the token is kept in memory for the current
session only and is gone when the application exits - the user simply has to
log in again next time. Any ``token.json`` left behind by an older version is
deleted on start-up.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from audiflix import APP_NAME
from audiflix.logging_setup import get_logger

try:  # keyring is optional at import time (tests, headless CI)
    import keyring
except Exception:  # noqa: BLE001 - any import failure means: no keyring
    # pragma: no cover - only when keyring is missing entirely
    keyring = None

log = get_logger(__name__)

_KEYRING_SERVICE = "audiflix"

#: Tokens held only for the lifetime of this process (no keyring available).
_session_tokens: dict[str, str] = {}

#: Set once we know the keyring backend does not work, to avoid retry storms.
_keyring_unavailable = False


def config_dir() -> Path:
    """Directory for settings and the download registry (created on demand).

    ``AUDIFLIX_CONFIG_DIR`` overrides the location outright (used by the tests
    and handy for portable installations); otherwise the platform config
    directory with an ``audiflix`` sub-folder is used.
    """
    override = os.environ.get("AUDIFLIX_CONFIG_DIR")
    if override:
        path = Path(override)
    else:
        base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
        if not base:
            base = str(Path.home() / ".config")
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_download_dir() -> Path:
    return Path.home() / "Audiflix"


# --- Defaults for every configurable feature -------------------------------

DEFAULT_SETTINGS: dict[str, Any] = {
    "server_url": "",
    "username": "",
    "language": "auto",
    "remember_login": True,
    "last_library": "",
    "skip_back_seconds": 15,
    "skip_forward_seconds": 30,
    "default_speed": 1.0,
    "default_volume": 100,
    "volume_step": 5,
    "sleep_timer_default_minutes": 15,
    #: Fade the volume out over the last seconds of the sleep timer (0 = off).
    "sleep_fade_seconds": 20,
    "download_dir": str(default_download_dir()),
    "announce_on_seek": True,
    "announce_chapter_change": True,
    "progress_sync_seconds": 15,
    "allow_insecure_http": False,
    #: Play/pause and track keys on a keyboard or headset, even when Audiflix
    #: is in the background (Windows only).
    "global_media_keys": True,
    #: Speed per title (item id -> rate), saved whenever the speed is changed
    #: while a title is playing. Titles without an entry use "default_speed".
    "remember_speed_per_title": True,
    "book_speeds": {},
    # Shortcuts are stored as strings in wx accelerator syntax and can be
    # overridden in the settings dialog. An empty value disables the shortcut.
    "shortcuts": {
        "play_pause": "Ctrl+Space",
        "skip_back": "Ctrl+Left",
        "skip_forward": "Ctrl+Right",
        "prev_chapter": "Ctrl+Shift+Left",
        "next_chapter": "Ctrl+Shift+Right",
        "chapter_list": "Ctrl+Shift+C",
        "prev_track": "Ctrl+Alt+Left",
        "next_track": "Ctrl+Alt+Right",
        "jump_to_time": "Ctrl+G",
        "speed_down": "Ctrl+-",
        "speed_up": "Ctrl++",
        "speed_reset": "Ctrl+0",
        "volume_up": "Ctrl+Up",
        "volume_down": "Ctrl+Down",
        "announce_time": "Ctrl+T",
        "sleep_timer": "Ctrl+L",
        "announce_sleep": "Ctrl+Alt+L",
        "add_bookmark": "Ctrl+B",
        "manage_bookmarks": "Ctrl+Shift+B",
        "media_info": "Ctrl+I",
        "select_library": "Ctrl+Shift+L",
        "settings": "Ctrl+,",
        "search": "Ctrl+F",
        "quit": "Ctrl+Q",
    },
}

DEFAULT_SHORTCUTS: dict[str, str] = dict(DEFAULT_SETTINGS["shortcuts"])


# Migrations of outdated default values. Only replaced when the stored value is
# exactly the old default (so a deliberate customisation is never overwritten).
_LEGACY_SHORTCUTS = {
    "speed_up": ("Ctrl+=", "Ctrl++"),
    "chapter_list": ("Ctrl+K", "Ctrl+Shift+C"),
}


class Settings:
    """Loaded settings with convenient access and saving."""

    def __init__(self, data: dict[str, Any] | None = None):
        self._data = _merge_defaults(DEFAULT_SETTINGS, data or {})
        self._migrate()

    def _migrate(self) -> None:
        shortcuts = self._data.get("shortcuts", {})
        for key, (old, new) in _LEGACY_SHORTCUTS.items():
            if shortcuts.get(key) == old:
                shortcuts[key] = new

    # dict-like access -----------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def shortcut(self, action: str) -> str:
        return self._data["shortcuts"].get(action, "")

    # persistence ----------------------------------------------------------
    @classmethod
    def path(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> Settings:
        path = cls.path()
        data: dict[str, Any] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
                else:
                    log.warning("settings.json does not contain an object - using defaults")
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not read settings.json (%s) - using defaults", exc)
        return cls(data)

    def save(self) -> bool:
        """Write settings to disk. Returns False (and logs) on failure."""
        path = self.path()
        try:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(path)
            return True
        except OSError as exc:
            log.error("Could not save settings: %s", exc)
            return False


def _merge_defaults(defaults: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Deep merge so newly added default keys appear in existing config files."""
    result: dict[str, Any] = {}
    for key, default_value in defaults.items():
        if isinstance(default_value, dict):
            existing = data.get(key)
            result[key] = _merge_defaults(default_value, existing if isinstance(existing, dict) else {})
        else:
            result[key] = data.get(key, default_value)
    # keep unknown keys from the file
    for key, value in data.items():
        if key not in result:
            result[key] = value
    return result


# --- Token storage ---------------------------------------------------------

def _keyring_available() -> bool:
    global _keyring_unavailable
    if keyring is None or _keyring_unavailable:
        return False
    try:
        from keyring.backends.fail import Keyring as FailKeyring

        if isinstance(keyring.get_keyring(), FailKeyring):
            _keyring_unavailable = True
            return False
    except Exception:  # pragma: no cover - very old keyring versions
        log.debug("Could not inspect keyring backend", exc_info=True)
    return True


def keyring_backend_name() -> str | None:
    """Name of the active keyring backend, or ``None`` when unavailable."""
    if not _keyring_available():
        return None
    try:
        return type(keyring.get_keyring()).__name__
    except Exception:
        log.debug("Could not read keyring backend name", exc_info=True)
        return None


def token_storage_is_persistent() -> bool:
    """True when a token survives a restart (i.e. a keyring backend works)."""
    return _keyring_available()


def save_token(server_url: str, username: str, token: str) -> bool:
    """Store the token in the system keyring.

    Returns True when it was stored persistently. When no keyring backend is
    available the token is kept **in memory for this session only** and False is
    returned so the UI can tell the user they will have to log in again.
    Audiflix never writes the token to a file.
    """
    account = _account(server_url, username)
    global _keyring_unavailable
    if _keyring_available():
        try:
            keyring.set_password(_KEYRING_SERVICE, account, token)
            _session_tokens.pop(account, None)
            return True
        except Exception as exc:  # noqa: BLE001 - backends raise all sorts of errors
            _keyring_unavailable = True
            log.warning("Keyring unavailable, keeping token in memory only: %s", exc)
    _session_tokens[account] = token
    return False


def load_token(server_url: str, username: str) -> str | None:
    """Read the stored token, preferring the keyring over the session cache."""
    account = _account(server_url, username)
    if _keyring_available():
        try:
            token = keyring.get_password(_KEYRING_SERVICE, account)
            if token:
                return token
        except Exception as exc:  # noqa: BLE001 - backends raise all sorts of errors
            log.warning("Could not read token from keyring: %s", exc)
    return _session_tokens.get(account)


def clear_token(server_url: str, username: str) -> None:
    """Delete the token from the keyring and the session cache."""
    account = _account(server_url, username)
    _session_tokens.pop(account, None)
    if _keyring_available():
        try:
            keyring.delete_password(_KEYRING_SERVICE, account)
        except Exception as exc:  # noqa: BLE001 - backends raise all sorts of errors
            # Deleting a token that was never stored is not an error.
            log.debug("Could not delete token from keyring: %s", exc)


def clear_session_tokens() -> None:
    """Drop all in-memory tokens (called on logout and shutdown)."""
    _session_tokens.clear()


def purge_legacy_token_file() -> bool:
    """Delete a plaintext ``token.json`` written by Audiflix < 0.1.0.

    Returns True when such a file existed and was removed.
    """
    path = config_dir() / "token.json"
    if not path.exists():
        return False
    try:
        path.unlink()
        log.warning("Removed legacy plaintext token file %s", path)
        return True
    except OSError as exc:
        log.error("Could not remove legacy token file %s: %s", path, exc)
        return False


def save_tokens(
    server_url: str, username: str, access_token: str, refresh_token: str | None
) -> bool:
    """Store access and refresh token. Returns True when stored persistently."""
    persistent = save_token(server_url, username, access_token)
    if refresh_token:
        persistent = save_token(server_url, _refresh_account(username), refresh_token) and persistent
    else:
        clear_token(server_url, _refresh_account(username))
    return persistent


def load_tokens(server_url: str, username: str) -> tuple[str | None, str | None]:
    """Return ``(access_token, refresh_token)`` for the account."""
    return (
        load_token(server_url, username),
        load_token(server_url, _refresh_account(username)),
    )


def clear_tokens(server_url: str, username: str) -> None:
    """Remove access and refresh token for the account."""
    clear_token(server_url, username)
    clear_token(server_url, _refresh_account(username))


def _refresh_account(username: str) -> str:
    return f"{username}#refresh"


def _account(server_url: str, username: str) -> str:
    return f"{server_url.rstrip('/')}|{username}"
