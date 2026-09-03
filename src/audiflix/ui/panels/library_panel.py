"""Tab 2: Books / Podcasts.

* a choice control for sorting (newest / alphabetical),
* a choice control for filtering by listening state,
* a search field for titles,
* for podcast libraries an extra button to search for and add new podcasts.

Enter starts playback, Backspace clears an active search.
"""

from __future__ import annotations

import wx

from audiflix.api import client as api
from audiflix.helpers.formatting import episode_columns, episode_row
from audiflix.i18n import N_, _
from audiflix.ui.dialogs.add_podcast_dialog import AddPodcastDialog
from audiflix.ui.item_actions import context_actions
from audiflix.ui.panels.base_list_panel import BaseListPanel

SORT_OPTIONS: list[tuple[str, tuple[str, bool]]] = [
    (N_("Newest"), ("addedAt", True)),
    (N_("Alphabetical"), ("media.metadata.title", False)),
]

#: Label -> (server filter, local predicate name). The server filters the full
#: list; a search goes through a different endpoint that takes no filter, so
#: its results are filtered here instead.
FILTER_OPTIONS: list[tuple[str, tuple[str | None, str | None]]] = [
    (N_("All titles"), (None, None)),
    (N_("Not started"), (api.NOT_STARTED_FILTER, "not_started")),
    (N_("In progress"), (api.IN_PROGRESS_FILTER, "in_progress")),
    (N_("Finished"), (api.FINISHED_FILTER, "finished")),
    (N_("Downloaded"), (None, "downloaded")),
]


class LibraryPanel(wx.Panel):
    def __init__(self, parent, frame):
        super().__init__(parent)
        self.frame = frame
        self.ctx = frame.ctx

        sizer = wx.BoxSizer(wx.VERTICAL)

        # Control row: sorting plus title search
        controls = wx.BoxSizer(wx.HORIZONTAL)
        controls.Add(
            wx.StaticText(self, label=_("&Sort:")), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4,
        )
        self.sort_choice = wx.Choice(self, choices=[_(option[0]) for option in SORT_OPTIONS])
        self.sort_choice.SetName(_("Sort order"))
        self.sort_choice.SetSelection(0)
        controls.Add(self.sort_choice, 0, wx.RIGHT, 12)
        controls.Add(
            wx.StaticText(self, label=_("&Filter:")), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4,
        )
        self.filter_choice = wx.Choice(self, choices=[_(option[0]) for option in FILTER_OPTIONS])
        self.filter_choice.SetName(_("Filter by listening state"))
        self.filter_choice.SetSelection(0)
        controls.Add(self.filter_choice, 0, wx.RIGHT, 12)
        controls.Add(
            wx.StaticText(self, label=_("Sea&rch:")), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4,
        )
        self.search = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search.SetName(_("Search titles"))
        self.search.SetHint(_("Press Enter to search"))
        controls.Add(self.search, 1)
        sizer.Add(controls, 0, wx.EXPAND | wx.ALL, 4)

        # Podcast row (only visible for podcast libraries)
        self.podcast_row = wx.BoxSizer(wx.HORIZONTAL)
        self.add_podcast_btn = wx.Button(self, label=_("Search and &add podcast..."))
        self.podcast_row.Add(self.add_podcast_btn, 0)
        sizer.Add(self.podcast_row, 0, wx.EXPAND | wx.ALL, 4)

        self.list = BaseListPanel(
            self,
            label=_("Books"),
            on_open=self._open,
            on_back=self._clear_search,
            context_builder=lambda item: context_actions(self.frame, item),
        )
        # Episode list (podcasts only; reached by drilling into a podcast)
        self.episodes_list = BaseListPanel(
            self,
            label=_("Episodes"),
            columns=episode_columns(),
            on_open=self._play_episode,
            on_back=self._back_from_episodes,
        )
        self.episodes_list.Hide()
        sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 2)
        sizer.Add(self.episodes_list, 1, wx.EXPAND | wx.ALL, 2)
        self.SetSizer(sizer)

        self.sort_choice.Bind(wx.EVT_CHOICE, lambda event: self.load())
        self.filter_choice.Bind(wx.EVT_CHOICE, lambda event: self.load())
        self.search.Bind(wx.EVT_TEXT_ENTER, lambda event: self.load())
        self.add_podcast_btn.Bind(wx.EVT_BUTTON, self._on_add_podcast)

    def focus_default(self):
        if self.episodes_list.IsShown():
            self.episodes_list.focus_list()
        else:
            self.list.focus_list()

    def focus_search(self):
        self.search.SetFocus()
        self.search.SelectAll()

    def _open(self, item):
        if item.is_podcast:
            self._show_episodes(item)
            return
        self.ctx.play_item(item)

    # --- Podcast episodes ---------------------------------------------------
    def _show_episodes(self, item):
        ctx = self.ctx
        ctx.notify(_("Loading episodes of %s...") % item.title)

        def fetch():
            full = ctx.client.item(item.id)
            # Episode progress lives on the user object, so it has to be current
            # for the status column to mean anything.
            ctx.progress.update(ctx.client.fetch_me())
            return full, full.episodes

        def show(result):
            full, episodes = result
            # newest episodes first
            episodes = sorted(episodes, key=lambda episode: episode.published_at, reverse=True)
            rows = [
                episode_row(episode, ctx.episode_status(full.id, episode.id))
                for episode in episodes
            ]
            payloads = [(full, episode) for episode in episodes]
            self.episodes_list.set_rows(rows, payloads)
            self.episodes_list.set_label(
                _("Episodes: %(title)s (%(count)d)")
                % {"title": full.title, "count": len(episodes)}
            )
            self.list.Hide()
            self.episodes_list.Show()
            self.Layout()
            self.episodes_list.focus_list()

        ctx.run_async(fetch, on_done=show, description="podcast-episodes")

    def _play_episode(self, payload):
        parent_item, episode = payload
        self.ctx.play_item(parent_item, episode)

    def _back_from_episodes(self):
        self.episodes_list.Hide()
        self.list.Show()
        self.Layout()
        self.list.focus_list()

    def _clear_search(self):
        if self.search.GetValue():
            self.search.SetValue("")
            self.load()

    def _on_add_podcast(self, event):
        lib_ids = self.ctx.active_library_ids
        if not lib_ids:
            return
        dlg = AddPodcastDialog(self.frame, self.ctx.client, lib_ids[0])
        try:
            added = dlg.ShowModal() == wx.ID_OK
        finally:
            dlg.Destroy()
        if added:
            self.load()

    def update_mode(self):
        """Adapt the podcast row and the labels to the active library."""
        is_podcast = self.ctx.active_is_podcast
        self.podcast_row.ShowItems(is_podcast)
        # always return to the main list when the library changes
        self.episodes_list.Hide()
        self.list.Show()
        self.list.set_label(_("Podcasts") if is_podcast else _("Books"))
        self.search.SetName(_("Search podcasts") if is_podcast else _("Search titles"))
        self.Layout()

    # --- Loading ------------------------------------------------------------
    def load(self):
        ctx = self.ctx
        lib_ids = ctx.active_library_ids
        if not lib_ids:
            return
        term = self.search.GetValue().strip()
        sort_key, desc = SORT_OPTIONS[max(0, self.sort_choice.GetSelection())][1]
        filter_index = max(0, self.filter_choice.GetSelection())
        filter_label, (server_filter, local_filter) = FILTER_OPTIONS[filter_index]

        def fetch():
            if term:
                merged = []
                for lib_id in lib_ids:
                    merged.extend(ctx.client.search_library(lib_id, term, limit=50))
                return self._apply_filter(merged, local_filter)
            items = ctx.client.all_items(
                lib_ids, sort=sort_key, desc=desc, filter_=server_filter
            )
            # "Downloaded" has no equivalent on the server - it is about this
            # machine, not the library.
            return self._apply_filter(items, local_filter) if server_filter is None else items

        def show(items):
            self.list.set_items(items, ctx.item_progress, ctx.item_status)
            base = _("Podcasts") if ctx.active_is_podcast else _("Books")
            if filter_index:
                base = f"{base} - {_(filter_label)}"
            if term:
                self.list.set_label(
                    _("%(kind)s (%(count)d) - search '%(term)s'")
                    % {"kind": base, "count": len(items), "term": term}
                )
            else:
                self.list.set_label(f"{base} ({len(items)})")

        ctx.run_async(fetch, on_done=show, description="library-items")

    def _apply_filter(self, items: list, local_filter: str | None) -> list:
        """Filter a list of items here, for the cases the server cannot cover."""
        if not local_filter:
            return items
        ctx = self.ctx
        if local_filter == "downloaded":
            return [item for item in items if ctx.registry.is_downloaded(item.id)]
        if local_filter == "finished":
            return [item for item in items if ctx.progress.is_finished(item.id)]
        if local_filter == "in_progress":
            return [
                item for item in items
                if not ctx.progress.is_finished(item.id)
                and ctx.progress.progress_for(item.id) > 0
            ]
        if local_filter == "not_started":
            return [item for item in items if ctx.progress.progress_for(item.id) <= 0]
        return items

    def refresh(self):
        self.update_mode()
        self.load()
