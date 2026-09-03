"""Small, defensive accessors for Audiobookshelf data structures.

Depending on the server version the ABS API returns slightly different fields.
Instead of strict data classes the access is wrapped in thin classes that use
``.get()`` throughout and never crash because of a missing key.
"""

from __future__ import annotations

from typing import Any

from audiflix.i18n import _


class LibraryItem:
    """Wrapper around an ABS ``libraryItem`` dict (book or podcast)."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw or {}

    # Basics ---------------------------------------------------------------
    @property
    def id(self) -> str:
        return self.raw.get("id") or self.raw.get("libraryItemId") or ""

    @property
    def library_id(self) -> str:
        return self.raw.get("libraryId", "")

    @property
    def media_type(self) -> str:
        return self.raw.get("mediaType", "book")

    @property
    def is_podcast(self) -> bool:
        return self.media_type == "podcast"

    @property
    def added_at(self) -> int:
        return int(self.raw.get("addedAt") or 0)

    # Media / metadata -----------------------------------------------------
    @property
    def _media(self) -> dict[str, Any]:
        return self.raw.get("media") or {}

    @property
    def _metadata(self) -> dict[str, Any]:
        return self._media.get("metadata") or {}

    @property
    def title(self) -> str:
        return self._metadata.get("title") or self.raw.get("title") or _("(untitled)")

    @property
    def subtitle(self) -> str:
        return self._metadata.get("subtitle") or ""

    @property
    def author(self) -> str:
        md = self._metadata
        if md.get("authorName"):
            return md["authorName"]
        authors = md.get("authors") or []
        names = [a.get("name", "") for a in authors if isinstance(a, dict)]
        return ", ".join(n for n in names if n)

    @property
    def narrator(self) -> str:
        md = self._metadata
        if md.get("narratorName"):
            return md["narratorName"]
        narrators = md.get("narrators") or []
        if isinstance(narrators, list):
            return ", ".join(n for n in narrators if isinstance(n, str))
        return ""

    @property
    def series(self) -> str:
        md = self._metadata
        if md.get("seriesName"):
            return md["seriesName"]
        series = md.get("series") or []
        parts = []
        for s in series:
            if not isinstance(s, dict):
                continue
            name = s.get("name", "")
            seq = s.get("sequence")
            parts.append(f"{name} {seq}".strip() if seq else name)
        return ", ".join(p for p in parts if p)

    @property
    def description(self) -> str:
        return self._metadata.get("description") or ""

    @property
    def publisher(self) -> str:
        return self._metadata.get("publisher") or ""

    @property
    def published_year(self) -> str:
        return str(self._metadata.get("publishedYear") or "")

    @property
    def genres(self) -> list[str]:
        return [g for g in (self._metadata.get("genres") or []) if isinstance(g, str)]

    @property
    def language(self) -> str:
        return self._metadata.get("language") or ""

    @property
    def duration(self) -> float:
        """Total duration in seconds (0 when unknown)."""
        return float(self._media.get("duration") or 0.0)

    @property
    def num_tracks(self) -> int:
        return int(self._media.get("numTracks") or len(self._media.get("tracks") or []))

    @property
    def chapters(self) -> list[Chapter]:
        return [Chapter(c) for c in (self._media.get("chapters") or [])]

    @property
    def audio_files(self) -> list[AudioFile]:
        """The audio files of a book, in playback order.

        Only an item loaded with ``expanded=1`` carries them; this is what a
        download needs, because every file is fetched on its own.
        """
        files = [
            AudioFile(f)
            for f in (self._media.get("audioFiles") or [])
            if isinstance(f, dict)
        ]
        return sorted(files, key=lambda f: f.index)

    @property
    def episodes(self) -> list[Episode]:
        return [Episode(e, self.id) for e in (self._media.get("episodes") or [])]

    @property
    def num_episodes(self) -> int:
        return int(self._media.get("numEpisodes") or len(self._media.get("episodes") or []))

    @property
    def auto_download_episodes(self) -> bool:
        """Podcasts only: does ABS download new episodes automatically?"""
        return bool(self._media.get("autoDownloadEpisodes"))

    @property
    def recent_episode(self) -> Episode | None:
        """For podcasts from items-in-progress: the most recently played episode."""
        raw = self.raw.get("recentEpisode")
        return Episode(raw, self.id) if raw else None

    @property
    def author_ids(self) -> list[str]:
        return [
            a.get("id", "")
            for a in (self._metadata.get("authors") or [])
            if isinstance(a, dict) and a.get("id")
        ]

    @property
    def size(self) -> int:
        return int(self.raw.get("size") or self._media.get("size") or 0)

    def to_info_lines(self) -> list[tuple[str, str]]:
        """(label, value) pairs for the media info dialog."""
        lines: list[tuple[str, str]] = [
            (_("Title"), self.title),
            (_("Subtitle"), self.subtitle),
            (_("Author"), self.author),
            (_("Narrator"), self.narrator),
            (_("Series"), self.series),
            (_("Publisher"), self.publisher),
            (_("Published"), self.published_year),
            (_("Language"), self.language),
            (_("Genres"), ", ".join(self.genres)),
        ]
        return [(label, value) for label, value in lines if value]


class Episode:
    """Wrapper around a podcast episode (inside ``media.episodes``)."""

    def __init__(self, raw: dict[str, Any], parent_item_id: str = ""):
        self.raw = raw or {}
        self.parent_item_id = parent_item_id

    @property
    def id(self) -> str:
        return self.raw.get("id", "")

    @property
    def title(self) -> str:
        return self.raw.get("title") or _("(untitled)")

    @property
    def subtitle(self) -> str:
        return self.raw.get("subtitle") or ""

    @property
    def description(self) -> str:
        return self.raw.get("description") or ""

    @property
    def published_at(self) -> int:
        return int(self.raw.get("publishedAt") or 0)

    @property
    def pub_date(self) -> str:
        return self.raw.get("pubDate") or ""

    @property
    def duration(self) -> float:
        audio = self.raw.get("audioFile") or {}
        return float(self.raw.get("duration") or audio.get("duration") or 0.0)

    @property
    def episode_number(self) -> str:
        return str(self.raw.get("episode") or "")


class AudioFile:
    """One audio file of a book (inside ``media.audioFiles``).

    ``ino`` is the file's inode on the server and the only handle the download
    endpoint accepts.
    """

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw or {}

    @property
    def ino(self) -> str:
        return str(self.raw.get("ino") or "")

    @property
    def index(self) -> int:
        return int(self.raw.get("index") or 0)

    @property
    def duration(self) -> float:
        return float(self.raw.get("duration") or 0.0)

    @property
    def filename(self) -> str:
        metadata = self.raw.get("metadata") or {}
        return str(metadata.get("filename") or self.raw.get("filename") or "")

    @property
    def extension(self) -> str:
        metadata = self.raw.get("metadata") or {}
        ext = str(metadata.get("ext") or "")
        if ext:
            return ext if ext.startswith(".") else f".{ext}"
        _stem, _dot, suffix = self.filename.rpartition(".")
        return f".{suffix}" if suffix else ".mp3"


class Chapter:
    """Wrapper around an ABS chapter (in ``media.chapters`` or the play session).

    ``start``/``end`` are global seconds across the whole audiobook.
    """

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw or {}

    @property
    def id(self) -> Any:
        return self.raw.get("id")

    @property
    def title(self) -> str:
        return self.raw.get("title") or _("(untitled)")

    @property
    def start(self) -> float:
        return float(self.raw.get("start") or 0.0)

    @property
    def end(self) -> float:
        return float(self.raw.get("end") or 0.0)


class Bookmark:
    """Wrapper around an ABS bookmark (inside ``user.bookmarks``)."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw or {}

    @property
    def item_id(self) -> str:
        return self.raw.get("libraryItemId", "")

    @property
    def title(self) -> str:
        return self.raw.get("title") or ""

    @property
    def time(self) -> int:
        return int(self.raw.get("time") or 0)

    @property
    def created_at(self) -> int:
        return int(self.raw.get("createdAt") or 0)


class Author:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw or {}

    @property
    def id(self) -> str:
        return self.raw.get("id", "")

    @property
    def name(self) -> str:
        return self.raw.get("name") or _("(unknown)")

    @property
    def num_books(self) -> int:
        return int(self.raw.get("numBooks") or len(self.raw.get("libraryItems") or []))

    @property
    def added_at(self) -> int:
        return int(self.raw.get("addedAt") or 0)


class Series:
    """Wrapper around an ABS series (``/api/libraries/:id/series``)."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw or {}

    @property
    def id(self) -> str:
        return self.raw.get("id", "")

    @property
    def name(self) -> str:
        return self.raw.get("name") or _("(unnamed)")

    @property
    def books(self) -> list[LibraryItem]:
        return [LibraryItem(b) for b in (self.raw.get("books") or [])]

    @property
    def num_books(self) -> int:
        return int(self.raw.get("numBooks") or len(self.raw.get("books") or []))

    @property
    def added_at(self) -> int:
        return int(self.raw.get("addedAt") or 0)


class Collection:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw or {}

    @property
    def id(self) -> str:
        return self.raw.get("id", "")

    @property
    def name(self) -> str:
        return self.raw.get("name") or _("(unnamed)")

    @property
    def description(self) -> str:
        return self.raw.get("description") or ""

    @property
    def books(self) -> list[LibraryItem]:
        return [LibraryItem(b) for b in (self.raw.get("books") or [])]

    @property
    def num_books(self) -> int:
        return len(self.raw.get("books") or [])
