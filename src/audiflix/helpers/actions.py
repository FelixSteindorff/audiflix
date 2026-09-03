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
from audiflix.helpers.status import DownloadRegistry
from audiflix.helpers.text import safe_file_name
from audiflix.i18n import _


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
    """Download an item and record it in the registry."""
    os.makedirs(download_dir, exist_ok=True)
    safe = safe_file_name(item.title, fallback=item.id or "download")
    dest = os.path.join(download_dir, f"{safe}.zip")
    client.download_item(item.id, dest, progress_cb=progress_cb)
    registry.mark(item.id, dest)
    return _("%s downloaded.") % item.title


def update_metadata(
    client: AudiobookshelfClient, item: LibraryItem, metadata: dict
) -> str:
    client.update_media(item.id, metadata)
    return _("Media details for %s saved.") % item.title
