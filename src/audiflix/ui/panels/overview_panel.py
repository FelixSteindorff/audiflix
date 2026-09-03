"""Tab 1: Overview - continue listening, recently added, finished.

Three lists stacked vertically. Each row shows title, author, narrator, series
and the download status. Enter starts playback, the applications key opens the
context menu.
"""

from __future__ import annotations

import wx

from audiflix.i18n import _
from audiflix.ui.item_actions import context_actions
from audiflix.ui.panels.base_list_panel import BaseListPanel


class OverviewPanel(wx.Panel):
    def __init__(self, parent, frame):
        super().__init__(parent)
        self.frame = frame
        self.ctx = frame.ctx

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.continue_list = self._make_list(sizer, _("Continue listening"))
        self.recent_list = self._make_list(sizer, _("Recently added"))
        self.finished_list = self._make_list(sizer, _("Finished"))
        self.SetSizer(sizer)

    def _make_list(self, sizer, label) -> BaseListPanel:
        panel = BaseListPanel(
            self,
            label=label,
            on_open=self._open,
            context_builder=lambda item: context_actions(self.frame, item),
        )
        sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 2)
        return panel

    def _open(self, item):
        # Podcast from "continue listening": start the most recent episode.
        episode = item.recent_episode if item.is_podcast else None
        self.ctx.play_item(item, episode)

    def focus_default(self):
        self.continue_list.focus_list()

    # --- Loading ------------------------------------------------------------
    def load(self):
        ctx = self.ctx
        lib_ids = ctx.active_library_ids
        if not lib_ids:
            return

        def fetch():
            return {
                "continue": ctx.client.items_in_progress(limit=25),
                "recent": ctx.client.recently_added_all(lib_ids, limit=50),
                "finished": ctx.client.finished_items_all(lib_ids, limit=100),
            }

        def show(data):
            self.continue_list.set_items(data["continue"], ctx.is_downloaded, ctx.is_finished)
            self.recent_list.set_items(data["recent"], ctx.is_downloaded, ctx.is_finished)
            self.finished_list.set_items(data["finished"], ctx.is_downloaded, ctx.is_finished)
            self.continue_list.set_label(
                _("Continue listening (%d)") % len(data["continue"])
            )
            self.recent_list.set_label(_("Recently added (%d)") % len(data["recent"]))
            self.finished_list.set_label(_("Finished (%d)") % len(data["finished"]))

        ctx.run_async(fetch, on_done=show, description="overview")

    def refresh(self):
        self.load()
