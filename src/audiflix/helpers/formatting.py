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
    return [
        _("Title"), _("Author"), _("Narrator"), _("Series"), _("Progress"), _("Status")
    ]


def episode_columns() -> list[str]:
    return [_("Episode"), _("Published"), _("Duration"), _("Status")]


def downloaded_label() -> str:
    return _("Downloaded")


def not_downloaded_label() -> str:
    return _("Not downloaded")


def progress_label(progress: float, finished: bool = False) -> str:
    """Listening state as a short status text, e.g. '42% played'."""
    if finished:
        return _("Finished")
    percent = round(max(0.0, min(progress, 1.0)) * 100)
    if percent <= 0:
        return _("Not started")
    return _("%d%% played") % percent


def status_label(downloaded: bool, finished: bool = False) -> str:
    """Combined download/finished status for a list row."""
    base = downloaded_label() if downloaded else not_downloaded_label()
    if finished:
        return _("Finished, %s") % base.lower()
    return base


def download_label(downloaded: bool, playable_offline: bool = False) -> str:
    """Status column of a book row: is the title available without a server?"""
    if downloaded and playable_offline:
        return _("Available offline")
    if downloaded:
        # An archive downloaded by an older version: on disk, but not playable.
        return _("Downloaded (archive)")
    return not_downloaded_label()


def progress_column(
    progress: float, finished: bool, duration: float = 0.0, current_time: float = 0.0
) -> str:
    """Progress column of a list row: how far in, and how much is left.

    The remaining time is what a listener actually plans with ("do I still fit
    this in tonight?"), so it is spelled out whenever the length is known.
    """
    label = progress_label(progress, finished)
    if finished or duration <= 0:
        return label
    remaining = duration - (current_time or duration * progress)
    if remaining < 60:
        return label
    return _("%(progress)s, %(remaining)s left") % {
        "progress": label,
        "remaining": format_duration(remaining),
    }


def item_row(item: LibraryItem, progress: str = "", status: str = "") -> list[str]:
    """Values for one list row, matching :func:`item_columns`."""
    return [
        item.title,
        item.author or "-",
        item.narrator or "-",
        item.series or "-",
        progress or progress_label(0.0),
        status or not_downloaded_label(),
    ]


def item_announce(item: LibraryItem, progress: str = "", status: str = "") -> str:
    """One-sentence description of a row for the speech output."""
    parts = [item.title]
    if item.author:
        parts.append(_("by %s") % item.author)
    if item.narrator:
        parts.append(_("narrated by %s") % item.narrator)
    if item.series:
        parts.append(_("series %s") % item.series)
    if progress:
        parts.append(progress.lower())
    if status:
        parts.append(status.lower())
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


def episode_row(episode: Episode, status: str = "") -> list[str]:
    """Values for one episode row, matching :func:`episode_columns`.

    ``status`` is the listening state of this episode, which is what the column
    is about: episodes are streamed from the server, so "downloaded" - the
    status a book row shows - says nothing useful about them.
    """
    return [
        episode.title,
        format_date(episode.published_at, episode.pub_date),
        format_clock(episode.duration) if episode.duration else "-",
        status or progress_label(0.0),
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


def parse_position(text: str, duration: float = 0.0) -> float | None:
    """Read a position a listener typed, in seconds. ``None`` when unusable.

    Understands ``1:23:45``, ``23:45``, ``90`` and ``90m`` as times and ``45%``
    as a share of ``duration``. Both a dot and a comma work as the decimal mark,
    because a German keyboard produces the comma.
    """
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None

    if text.endswith("%"):
        if duration <= 0:
            return None
        try:
            percent = float(text[:-1].strip())
        except ValueError:
            return None
        return duration * max(0.0, min(percent, 100.0)) / 100.0

    unit = 60.0 if text[-1:].lower() == "m" else (3600.0 if text[-1:].lower() == "h" else None)
    if unit is not None:
        try:
            return max(0.0, float(text[:-1].strip()) * unit)
        except ValueError:
            return None

    parts = text.split(":")
    if len(parts) > 3:
        return None
    try:
        values = [float(part) for part in parts]
    except ValueError:
        return None
    if any(value < 0 for value in values):
        return None
    seconds = 0.0
    for value in values:  # h:m:s, m:s or plain seconds
        seconds = seconds * 60 + value
    return seconds


def format_speed(rate: float) -> str:
    """Playback rate as a spoken factor, e.g. '1.5x'."""
    number = f"{rate:.2f}".rstrip("0").rstrip(".")
    return _("%sx") % number
