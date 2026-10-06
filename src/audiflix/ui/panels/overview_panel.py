"""Tab 1: Overview - continue listening, recently added, finished.

Three switchable lists keep the overview usable in small windows. Each row
shows title, author, narrator, series and download status.
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
        controls = wx.BoxSizer(wx.HORIZONTAL)
        controls.Add(wx.StaticText(self, label=_("&Show:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.section = wx.Choice(self, choices=[_("Continue listening"), _("Recently added"), _("Finished")])
        self.section.SetName(_("Overview list"))
        self.section.SetSelection(0)
        controls.Add(self.section, 1)
        sizer.Add(controls, 0, wx.EXPAND | wx.ALL, 6)
        self.continue_list = self._make_list(sizer, _("Continue listening"), "continue")
        self.recent_list = self._make_list(sizer, _("Recently added"), "recent")
        self.finished_list = self._make_list(sizer, _("Finished"), "finished")
        self._lists = [self.continue_list, self.recent_list, self.finished_list]
        self.recent_list.Hide()
        self.finished_list.Hide()
        self.section.Bind(wx.EVT_CHOICE, self._on_section)
        self.SetSizer(sizer)

    def _on_section(self, event: wx.CommandEvent) -> None:
        for index, panel in enumerate(self._lists):
            panel.Show(index == self.section.GetSelection())
        self.Layout()

    def _make_list(self, sizer, label, key) -> BaseListPanel:
        panel = BaseListPanel(
            self,
            label=label,
            settings_key=key,
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
        self._lists[max(0, self.section.GetSelection())].focus_list()

    # --- Loading ------------------------------------------------------------
    def load(self):
        ctx = self.ctx
        lib_ids = ctx.active_library_ids
        if not lib_ids:
            return

        for panel, label, key, fetch in (
            (self.continue_list, _("Continue listening"), "continue", lambda: ctx.client.items_in_progress(limit=25)),
            (self.recent_list, _("Recently added"), "recent", lambda: ctx.client.recently_added_all(lib_ids, limit=50)),
            (self.finished_list, _("Finished"), "finished", lambda: ctx.client.finished_items_all(lib_ids, limit=100)),
        ):
            def show(items, panel=panel, label=label):
                panel.set_items(items, ctx.item_progress, ctx.item_status)
                panel.set_label(f"{label} ({len(items)})")
            panel.load_async(ctx, fetch, show, f"overview-{key}", self.load)

    def refresh(self):
        self.load()
