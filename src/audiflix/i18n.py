"""Translation support (gettext) for Audiflix.

All user-visible strings in the code base are written in **English** and wrapped
in :func:`_`. Translations live as ``.po`` files under ``locale/<lang>/
LC_MESSAGES/audiflix.po`` and are compiled to ``.mo`` files by
``tools/compile_catalogs.py``.

Usage in application modules::

    from audiflix.i18n import _, ngettext

    label = _("Settings")
    text = ngettext("%d chapter", "%d chapters", count) % count

The active language is chosen by :func:`install`:

* an explicit ``language`` argument (e.g. from the settings dialog),
* otherwise the ``AUDIFLIX_LANG`` environment variable,
* otherwise the operating system's UI language,
* falling back to untranslated English.
"""

from __future__ import annotations

import gettext as _gettext
import locale as _locale
import os
import sys
from pathlib import Path

DOMAIN = "audiflix"

#: Language code used when no translation is active (the source language).
SOURCE_LANGUAGE = "en"

_translation: _gettext.NullTranslations = _gettext.NullTranslations()
_active_language: str = SOURCE_LANGUAGE


def locale_dir() -> Path:
    """Directory holding the compiled catalogs.

    Works both from a source checkout / installed package and from a
    PyInstaller one-file bundle (which unpacks data next to ``sys._MEIPASS``).
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidate = Path(bundled) / "locale"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent / "locale"


def available_languages() -> list[str]:
    """Language codes that have a compiled catalog available."""
    base = locale_dir()
    if not base.is_dir():
        return [SOURCE_LANGUAGE]
    langs = [
        entry.name
        for entry in sorted(base.iterdir())
        if (entry / "LC_MESSAGES" / f"{DOMAIN}.mo").is_file()
    ]
    return [SOURCE_LANGUAGE] + [lang for lang in langs if lang != SOURCE_LANGUAGE]


def _system_language() -> str | None:
    env = os.environ.get("AUDIFLIX_LANG") or os.environ.get("LANGUAGE")
    if env:
        return env.split(":")[0].split(".")[0]
    try:
        code = _locale.getlocale()[0] or _locale.getdefaultlocale()[0]
    except (ValueError, TypeError):
        return None
    return code.split(".")[0] if code else None


def install(language: str | None = None) -> str:
    """Activate ``language`` (e.g. ``"de"``) and return the code actually used.

    ``language`` may be ``None`` or ``"auto"`` to auto-detect. Unknown or
    missing catalogs silently fall back to the untranslated English source
    strings, so the application never fails because of a missing translation.
    """
    global _translation, _active_language

    candidate = _system_language() if language in (None, "", "auto") else language

    languages = [candidate] if candidate else None
    _translation = _gettext.translation(
        DOMAIN, localedir=str(locale_dir()), languages=languages, fallback=True
    )
    info = _translation.info() if hasattr(_translation, "info") else {}
    _active_language = (info.get("language") or candidate or SOURCE_LANGUAGE).split("_")[0]
    return _active_language


def active_language() -> str:
    return _active_language


def _(message: str) -> str:
    """Translate ``message`` into the active language."""
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    """Plural-aware translation."""
    return _translation.ngettext(singular, plural, n)


def pgettext(context: str, message: str) -> str:
    """Translation with a disambiguating ``context``."""
    return _translation.pgettext(context, message)


def N_(message: str) -> str:
    """Mark ``message`` for extraction without translating it now.

    Used for module-level string tables that must be translated lazily at
    display time.
    """
    return message
