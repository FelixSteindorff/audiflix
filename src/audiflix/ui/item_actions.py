"""Shared UI actions for a single book/item.

These functions combine the plain server actions from
:mod:`audiflix.helpers.actions` with the dialogs and navigation they need. They
are used by the list context menus *and* by the "Item" menu, so both routes
behave identically.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from audiflix.api.models import LibraryItem
from audiflix.helpers import actions
from audiflix.i18n import _
from audiflix.logging_setup import get_logger
from audiflix.ui.dialogs.add_to_collection_dialog import AddToCollectionDialog
from audiflix.ui.dialogs.edit_metadata_dialog import EditMetadataDialog
from audiflix.ui.dialogs.media_info_dialog import MediaInfoDialog

log = get_logger(__name__)


def context_actions(frame, item: LibraryItem) -> list[tuple[str, Callable[[], None]]]:
    """List of (label, callback) for the context menu and the Item menu."""
    if item.is_podcast:
        return podcast_context_actions(frame, item)
    return [
        (_("Add to collection..."), lambda: add_to_collection(frame, item)),
        (_("Mark as finished"), lambda: mark_finished(frame, item)),
        (_("Item details"), lambda: show_info(frame, item)),
        (_("Go to author"), lambda: go_to_author(frame, item)),
        (_("Edit media details..."), lambda: edit_metadata(frame, item)),
        (_("Download"), lambda: download(frame, item)),
    ]


def podcast_context_actions(frame, item: LibraryItem) -> list[tuple[str, Callable[[], None]]]:
    """Context menu for a podcast (instead of the book actions)."""
    return [
        (_("Check for new episodes"), lambda: check_new_episodes(frame, item)),
        (_("Toggle automatic episode download"), lambda: toggle_auto_download(frame, item)),
        (_("Podcast details"), lambda: show_info(frame, item)),
        (_("Add to collection..."), lambda: add_to_collection(frame, item)),
    ]


def author_context_actions(frame, author) -> list[tuple[str, Callable[[], None]]]:
    """Context menu of the author list."""
    return [
        (_("Show books"), lambda: frame.authors.show_author(author.id, author.name)),
    ]


def check_new_episodes(frame, item: LibraryItem) -> None:
    """Look for new episodes in the feed (ABS downloads them)."""
    ctx = frame.ctx
    ctx.notify(_("Checking %s for new episodes...") % item.title)

    def done(episodes):
        count = len(episodes)
        if count:
            ctx.notify(
                _("%(title)s: %(count)d new episode(s) found - the server is downloading them.")
                % {"title": item.title, "count": count}
            )
        else:
            ctx.notify(_("%s: no new episodes.") % item.title)
        frame.refresh_active_panel()

    ctx.run_async(
        lambda: ctx.client.check_new_episodes(item.id),
        on_done=done,
        description="check-new-episodes",
    )


def toggle_auto_download(frame, item: LibraryItem) -> None:
    """Read the current auto-download state and flip it."""
    ctx = frame.ctx
    ctx.notify(_("Updating the setting for %s...") % item.title)

    def do():
        full = ctx.client.item(item.id)
        new_state = not full.auto_download_episodes
        ctx.client.set_auto_download(item.id, new_state)
        return new_state

    def done(new_state):
        ctx.notify(
            _("%s: automatic episode download turned on.") % item.title
            if new_state
            else _("%s: automatic episode download turned off.") % item.title
        )

    ctx.run_async(do, on_done=done, description="toggle-auto-download")


def mark_finished(frame, item: LibraryItem) -> None:
    ctx = frame.ctx
    ctx.run_async(
        lambda: actions.mark_finished(ctx.client, item, True),
        on_done=lambda msg: _after_finished(frame, msg),
        description="mark-finished",
    )


def _after_finished(frame, message: str) -> None:
    frame.ctx.notify(message)
    frame.ctx.run_async(
        lambda: frame.ctx.progress.update(frame.ctx.client.fetch_me()),
        description="refresh-progress",
    )
    frame.refresh_active_panel()


def show_info(frame, item: LibraryItem) -> None:
    ctx = frame.ctx
    position = duration = None
    if ctx.current_item and ctx.current_item.id == item.id:
        position, duration = ctx.player.position, ctx.player.duration

    def show(full: LibraryItem):
        dlg = MediaInfoDialog(frame, full, position, duration)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    def on_error(exc: Exception):
        # Showing the data we already have beats showing nothing.
        log.info("Could not load full item details (%s) - showing the cached data", exc)
        show(item)

    ctx.run_async(
        lambda: ctx.client.item(item.id),
        on_done=show,
        on_error=on_error,
        description="item-details",
    )


def go_to_author(frame, item: LibraryItem) -> None:
    # Navigate directly when the author id is already known.
    if item.author_ids:
        frame.open_author(item.author_ids[0], item.author)
        return

    # Items in lists (overview/search) are minified and carry no author ids,
    # so load the full item and fall back to resolving by name.
    ctx = frame.ctx
    ctx.notify(_("Looking up the author..."))

    def resolve():
        full = ctx.client.item(item.id)
        name = full.author or item.author
        if full.author_ids:
            return (full.author_ids[0], name)
        if name:
            lib_ids = ctx.active_library_ids or [item.library_id]
            for author in ctx.client.authors_all(lib_ids):
                if author.name.lower() == name.lower():
                    return (author.id, author.name)
        return None

    def navigate(result):
        if result:
            frame.open_author(result[0], result[1])
        else:
            ctx.notify(_("No author is linked to this item."))

    ctx.run_async(resolve, on_done=navigate, description="resolve-author")


def edit_metadata(frame, item: LibraryItem) -> None:
    ctx = frame.ctx
    dlg = EditMetadataDialog(frame, item)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return
        metadata = dlg.get_metadata()
    finally:
        dlg.Destroy()
    ctx.run_async(
        lambda: actions.update_metadata(ctx.client, item, metadata),
        on_done=lambda msg: _notify_and_refresh(frame, msg),
        description="update-metadata",
    )


def add_to_collection(frame, item: LibraryItem) -> None:
    ctx = frame.ctx

    def load_collections():
        ids = ctx.active_library_ids or [item.library_id]
        return ctx.client.collections_all(ids)

    def choose(collections):
        dlg = AddToCollectionDialog(frame, collections)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            result = dlg.result()
        finally:
            dlg.Destroy()
        if result:
            _apply_collection(frame, item, result)

    ctx.run_async(load_collections, on_done=choose, description="load-collections")


def _apply_collection(frame, item: LibraryItem, result) -> None:
    ctx = frame.ctx
    kind, value = result
    if kind == "existing":
        ctx.run_async(
            lambda: actions.add_to_collection(ctx.client, value.id, value.name, item),
            on_done=ctx.notify,
            description="add-to-collection",
        )
    else:  # a new collection
        library_id = (ctx.active_library_ids or [item.library_id])[0]
        ctx.run_async(
            lambda: actions.create_collection_with(ctx.client, library_id, value, item),
            on_done=ctx.notify,
            description="create-collection",
        )


def download(frame, item: LibraryItem) -> None:
    ctx = frame.ctx
    if ctx.registry.is_downloaded(item.id):
        ctx.notify(_("%s has already been downloaded.") % item.title)
        return
    ctx.notify(_("Downloading %s...") % item.title)
    download_dir = ctx.settings.get("download_dir", "")
    ctx.run_async(
        lambda: actions.download(ctx.client, item, ctx.registry, download_dir),
        on_done=lambda msg: _notify_and_refresh(frame, msg),
        description="download-item",
    )


def _notify_and_refresh(frame, message: str) -> None:
    frame.ctx.notify(message)
    frame.refresh_active_panel()
