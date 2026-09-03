"""Shared item actions.

These functions wrap the server side of the actions that can be triggered from
the context menu, the menu bar and keyboard shortcuts alike. They are
synchronous and each returns a short, screen-reader friendly confirmation.
The UI calls them from worker threads and owns dialogs and threading.
"""

from __future__ import annotations

import os

from audiflix.api.client import AudiobookshelfClient
from audiflix.api.models import LibraryItem
from audiflix.helpers import downloads
from audiflix.helpers.status import DownloadRegistry
from audiflix.i18n import _, ngettext


def mark_finished(
    client: AudiobookshelfClient, item: LibraryItem, finished: bool = True
) -> str:
    client.mark_finished(item.id, finished)
    return (
        _("%s marked as finished.") % item.title
        if finished
        else _("%s marked as not finished.") % item.title
    )


def add_bookmark(
    client: AudiobookshelfClient, item: LibraryItem, time: float, title: str = ""
) -> str:
    from audiflix.helpers.formatting import format_clock

    client.add_bookmark(item.id, time, title or "")
    return _("Bookmark set at %s.") % format_clock(time)


def add_to_collection(
    client: AudiobookshelfClient,
    collection_id: str,
    collection_name: str,
    item: LibraryItem,
) -> str:
    client.add_to_collection(collection_id, item.id)
    return _("%(title)s added to collection %(collection)s.") % {
        "title": item.title,
        "collection": collection_name,
    }


def create_collection_with(
    client: AudiobookshelfClient, library_id: str, name: str, item: LibraryItem
) -> str:
    client.create_collection(library_id, name, [item.id])
    return _("Collection %(collection)s created with %(title)s.") % {
        "collection": name,
        "title": item.title,
    }


def download(
    client: AudiobookshelfClient,
    item: LibraryItem,
    registry: DownloadRegistry,
    download_dir: str,
    progress_cb=None,
) -> str:
    """Download a title for offline listening.

    Every audio file is fetched on its own into a folder of the title's name,
    together with a manifest holding the track order and the chapter marks.
    That is what makes the download playable without a server; the
    ``/download`` endpoint returns a zip archive, which nothing can play.
    """
    full = client.item(item.id)  # only an expanded item carries audioFiles
    audio_files = full.audio_files
    if not audio_files:
        raise DownloadError(_("%s has no audio files to download.") % item.title)

    folder = downloads.folder_for(download_dir, full.title or item.title, item.id)
    os.makedirs(folder, exist_ok=True)

    total_files = len(audio_files)
    tracks: list[dict] = []
    start_offset = 0.0
    for index, audio in enumerate(audio_files):
        name = downloads.track_file_name(index, audio.extension)
        dest = os.fspath(folder / name)
        client.download_audio_file(
            item.id,
            audio.ino,
            dest,
            progress_cb=_file_progress(progress_cb, index, total_files),
        )
        tracks.append(
            {
                "file": name,
                "ino": audio.ino,
                "start_offset": start_offset,
                "duration": audio.duration,
            }
        )
        start_offset += audio.duration

    chapters = [
        {"start": chapter.start, "end": chapter.end, "title": chapter.title}
        for chapter in full.chapters
    ]
    downloads.write_manifest(
        folder,
        item_id=item.id,
        title=full.title or item.title,
        duration=full.duration or start_offset,
        tracks=tracks,
        chapters=chapters,
    )
    registry.mark_folder(item.id, os.fspath(folder))
    return ngettext(
        "%(title)s downloaded (%(count)d file).",
        "%(title)s downloaded (%(count)d files).",
        total_files,
    ) % {"title": item.title, "count": total_files}


class DownloadError(RuntimeError):
    """A title cannot be downloaded (no audio files, for example)."""


def _file_progress(progress_cb, index: int, total: int):
    """Turn per-file progress into progress across the whole title."""
    if progress_cb is None or total <= 0:
        return None

    def report(done: int, size: int) -> None:
        share = (done / size) if size else 0.0
        progress_cb(int((index + share) / total * 100), 100)

    return report


def remove_download(
    item: LibraryItem, registry: DownloadRegistry
) -> str:
    """Delete the downloaded files of a title."""
    if not registry.path_for(item.id):
        return _("%s is not downloaded.") % item.title
    if registry.delete_files(item.id):
        return _("Download of %s deleted.") % item.title
    return _("The downloaded files of %s could not be deleted.") % item.title


def update_metadata(
    client: AudiobookshelfClient, item: LibraryItem, metadata: dict
) -> str:
    client.update_media(item.id, metadata)
    return _("Media details for %s saved.") % item.title
