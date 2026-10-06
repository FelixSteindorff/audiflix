"""Speech and braille output for Audiflix.

Uses ``accessible_output2`` to send text straight to the active screen reader
(NVDA in particular). It fails silently when no output is available so the
application also runs without a screen reader; the UI mirrors the same text in
the status bar.

Identical messages repeated within :data:`DEDUPE_WINDOW` seconds are dropped.
Several code paths (status bar update, action confirmation, focus change) can
describe the same event, and hearing it twice is worse than not hearing it at
all.
"""

from __future__ import annotations

import threading
import time

from audiflix.logging_setup import get_logger

log = get_logger(__name__)

#: Suppress an identical announcement repeated within this many seconds.
DEDUPE_WINDOW = 1.0

_speaker = None
_initialised = False
_lock = threading.Lock()
_last_message = ("", "")
_last_time = 0.0


def _get_speaker():
    global _speaker, _initialised
    if _initialised:
        return _speaker
    _initialised = True
    try:
        from accessible_output2.outputs.auto import Auto

        _speaker = Auto()
        log.info("Speech output initialised: %s", type(_speaker).__name__)
    except Exception as exc:  # noqa: BLE001 - any failure means: no speech output
        log.info("No screen-reader output available (%s) - running silently", exc)
        _speaker = None
    return _speaker


def announce(
    text: str, interrupt: bool = False, force: bool = False, *, braille_text: str | None = None,
) -> None:
    """Speak and braille ``text`` through the screen reader, if available.

    ``force=True`` bypasses the duplicate suppression for messages the user
    explicitly asked to repeat (for example the "announce position" shortcut).
    ``braille_text`` optionally supplies a compact version for the braille display.
    """
    if not text:
        return
    global _last_message, _last_time
    braille_text = text if braille_text is None else braille_text
    message = (text, braille_text)
    now = time.monotonic()
    with _lock:
        if not force and message == _last_message and now - _last_time < DEDUPE_WINDOW:
            return
        _last_message, _last_time = message, now
    speaker = _get_speaker()
    if speaker is None:
        return
    try:
        speaker.speak(text, interrupt=interrupt)
    except Exception:
        log.exception("Screen-reader speech output failed")
    try:
        speaker.braille(braille_text)
    except Exception:
        log.exception("Screen-reader braille output failed")


def reset_dedupe() -> None:
    """Forget the last announcement (used when a dialog opens or closes)."""
    global _last_message, _last_time
    with _lock:
        _last_message, _last_time = ("", ""), 0.0


def is_available() -> bool:
    return _get_speaker() is not None
