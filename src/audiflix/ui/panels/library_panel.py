"""Tab 2: Books / Podcasts.

* a choice control for sorting (newest / alphabetical),
* a search field for titles,
* for podcast libraries an extra button to search for and add new podcasts.

Enter starts playback, Backspace clears an active search.
"""

from __future__ import annotations

import wx

from audiflix.helpers.formatting import episode_columns, episode_row
from audiflix.i18n import N_, _
from audiflix.ui.dialogs.add_podcast_dialog import AddPodcastDialog
from audiflix.ui.item_actions import context_actions
from audiflix.ui.panels.base_list_panel import BaseListPanel

SORT_OPTIONS: list[tuple[str, tuple[str, bool]]] = [
    (N_("Newest"), ("addedAt", True)),
    (N_("Alphabetical"), ("media.metadata.title", False)),
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
            return full, full.episodes

        def show(result):
            full, episodes = result
            # newest episodes first
            episodes = sorted(episodes, key=lambda episode: episode.published_at, reverse=True)
            rows = [episode_row(episode) for episode in episodes]
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

        def fetch():
            if term:
                merged = []
                for lib_id in lib_ids:
                    merged.extend(ctx.client.search_library(lib_id, term, limit=50))
                return merged
            return ctx.client.all_items(lib_ids, sort=sort_key, desc=desc)

        def show(items):
            self.list.set_items(items, ctx.is_downloaded, ctx.is_finished)
            base = _("Podcasts") if ctx.active_is_podcast else _("Books")
            if term:
                self.list.set_label(
                    _("%(kind)s (%(count)d) - search '%(term)s'")
                    % {"kind": base, "count": len(items), "term": term}
                )
            else:
                self.list.set_label(f"{base} ({len(items)})")

        ctx.run_async(fetch, on_done=show, description="library-items")

    def refresh(self):
        self.update_mode()
        self.load()
