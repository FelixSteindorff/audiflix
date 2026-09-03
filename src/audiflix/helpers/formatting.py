"""Single source of truth for display strings (columns, durations, announcements).

Every panel and the speech output use these functions so wording stays
consistent and screen-reader friendly across the whole application.

All texts are translatable. Because the active language is only known once the
application has started, column headers and status labels are exposed as
*functions* rather than module constants - a module-level constant would be
frozen to whatever language was active at import time.
"""

from __future__ import annotations

import datetime

from audiflix.api.models import Episode, LibraryItem
from audiflix.i18n import _, ngettext


def item_columns() -> list[str]:
    """Column headers of the item lists (NVDA reads them per cell)."""
    return [_("Title"), _("Author"), _("Narrator"), _("Series"), _("Status")]


def episode_columns() -> list[str]:
    return [_("Episode"), _("Published"), _("Duration"), _("Status")]


def downloaded_label() -> str:
    return _("Downloaded")


def not_downloaded_label() -> str:
    return _("Not downloaded")


def status_label(downloaded: bool, finished: bool = False) -> str:
    """Combined download/finished status for a list row."""
    base = downloaded_label() if downloaded else not_downloaded_label()
    if finished:
        return _("Finished, %s") % base.lower()
    return base


def item_row(item: LibraryItem, downloaded: bool, finished: bool = False) -> list[str]:
    """Values for one list row, matching :func:`item_columns`."""
    return [
        item.title,
        item.author or "-",
        item.narrator or "-",
        item.series or "-",
        status_label(downloaded, finished),
    ]


def item_announce(item: LibraryItem, downloaded: bool, finished: bool = False) -> str:
    """One-sentence description of a row for the speech output."""
    parts = [item.title]
    if item.author:
        parts.append(_("by %s") % item.author)
    if item.narrator:
        parts.append(_("narrated by %s") % item.narrator)
    if item.series:
        parts.append(_("series %s") % item.series)
    parts.append(
        _("finished") if finished
        else (downloaded_label().lower() if downloaded else not_downloaded_label().lower())
    )
    return ", ".join(parts)


def format_date(published_at_ms: int, fallback: str = "") -> str:
    """Millisecond timestamp as an ISO date (YYYY-MM-DD), or the fallback text."""
    if published_at_ms:
        try:
            dt = datetime.datetime.fromtimestamp(published_at_ms / 1000)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            # An out-of-range timestamp is not worth an error message; the
            # server's own pubDate string is the better answer anyway.
            pass
    return fallback


def episode_row(episode: Episode, downloaded: bool = False) -> list[str]:
    """Values for one episode row, matching :func:`episode_columns`."""
    return [
        episode.title,
        format_date(episode.published_at, episode.pub_date),
        format_clock(episode.duration) if episode.duration else "-",
        status_label(downloaded),
    ]


def format_duration(seconds: float) -> str:
    """Seconds as a spoken duration, e.g. '3 hours 12 minutes'."""
    seconds = int(max(0, seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(ngettext("%d hour", "%d hours", hours) % hours)
    if minutes:
        parts.append(ngettext("%d minute", "%d minutes", minutes) % minutes)
    if not hours and not minutes:
        parts.append(ngettext("%d second", "%d seconds", secs) % secs)
    return " ".join(parts)


def format_clock(seconds: float) -> str:
    """Seconds as H:MM:SS or MM:SS."""
    seconds = int(max(0, seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_position(position: float, duration: float) -> str:
    """Short form for the status bar: 'MM:SS / H:MM:SS'."""
    return f"{format_clock(position)} / {format_clock(duration)}"


def announce_position(position: float, duration: float) -> str:
    """Verbose speech output: position and remaining time."""
    remaining = max(0.0, duration - position)
    return _("Position %(position)s, %(remaining)s remaining") % {
        "position": format_duration(position),
        "remaining": format_duration(remaining),
    }


def format_speed(rate: float) -> str:
    """Playback rate as a spoken factor, e.g. '1.5x'."""
    number = f"{rate:.2f}".rstrip("0").rstrip(".")
    return _("%sx") % number
