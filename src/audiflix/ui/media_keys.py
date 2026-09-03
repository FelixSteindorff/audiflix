"""Media keys that work while Audiflix is in the background.

Listening to a book usually happens *next to* something else, so the play key
on a keyboard or a headset has to work without bringing the window to the
front. Windows only hands those keys to the focused window unless they are
registered as system-wide hotkeys, which is what this module does.

``RegisterHotKey`` exists only on wxMSW. Everywhere else - and whenever another
application has already claimed a key - registration simply does not happen and
the menu shortcuts remain the way to control playback.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

import wx

from audiflix.logging_setup import get_logger

log = get_logger(__name__)

#: Action -> key code. wx defines these regardless of the platform.
MEDIA_KEYS: dict[str, int] = {
    "play_pause": wx.WXK_MEDIA_PLAY_PAUSE,
    "next_track": wx.WXK_MEDIA_NEXT_TRACK,
    "prev_track": wx.WXK_MEDIA_PREV_TRACK,
    "stop": wx.WXK_MEDIA_STOP,
}

#: Hotkey ids have to be unique per window; these are ours.
_FIRST_ID = 0xB000


def is_supported() -> bool:
    """True when this platform can register system-wide hotkeys."""
    return sys.platform == "win32" and hasattr(wx.Frame, "RegisterHotKey")


class MediaKeys:
    """Registers the media keys for a frame and routes them to handlers."""

    def __init__(self, frame: wx.Frame, handlers: dict[str, Callable[[], None]]):
        self._frame = frame
        self._handlers = handlers
        self._registered: dict[int, str] = {}

    def register(self) -> int:
        """Register the keys. Returns how many were actually claimed."""
        if not is_supported():
            log.info("Global media keys are not available on this platform")
            return 0
        self.unregister()
        # A media key another player already owns makes wx log an error, and a
        # log target that is a message box would greet the user with one dialog
        # per key at start-up. Losing a key to another application is normal,
        # not something to report.
        no_log = wx.LogNull()
        try:
            self._claim_all()
        finally:
            del no_log
        if self._registered:
            self._frame.Bind(wx.EVT_HOTKEY, self._on_hotkey)
            log.info("Registered %d global media key(s)", len(self._registered))
        return len(self._registered)

    def _claim_all(self) -> None:
        for offset, (action, keycode) in enumerate(MEDIA_KEYS.items()):
            if action not in self._handlers:
                continue
            hotkey_id = _FIRST_ID + offset
            try:
                claimed = self._frame.RegisterHotKey(hotkey_id, 0, keycode)
            except Exception:  # pragma: no cover - depends on the platform
                log.exception("Registering the media key for %s failed", action)
                continue
            if claimed:
                self._registered[hotkey_id] = action
            else:
                # Another player already owns the key; that is its right.
                log.info("The media key for %s is used by another application", action)

    def unregister(self) -> None:
        no_log = wx.LogNull()
        try:
            for hotkey_id in list(self._registered):
                try:
                    self._frame.UnregisterHotKey(hotkey_id)
                except Exception:  # pragma: no cover - platform dependent
                    log.debug("Could not release hotkey %d", hotkey_id, exc_info=True)
        finally:
            del no_log
        self._registered.clear()

    def _on_hotkey(self, event: wx.KeyEvent) -> None:
        action = self._registered.get(event.GetId())
        handler = self._handlers.get(action) if action else None
        if handler is None:
            event.Skip()
            return
        try:
            handler()
        except Exception:
            log.exception("Media key action '%s' failed", action)
