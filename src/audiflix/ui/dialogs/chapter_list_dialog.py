"""Chapter list: shows every chapter of the current title, Enter jumps to it.

Fully keyboard operable: arrow keys select, Enter or OK jumps to the start of
the chapter. The chapter that is currently playing is preselected so the screen
reader reads it out as soon as the dialog opens.
"""

from __future__ import annotations

import wx

from audiflix.helpers import formatting
from audiflix.i18n import _


class ChapterListDialog(wx.Dialog):
    def __init__(self, parent, chapters: list[dict], current_index: int = 0):
        super().__init__(
            parent,
            title=_("Chapters"),
            size=(480, 440),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._chapters = chapters
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(panel, label=_("&Chapters (%d):") % len(chapters))
        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list.SetName(_("Chapter list"))
        self.list.InsertColumn(0, _("Chapter"), width=300)
        self.list.InsertColumn(1, _("Start"), width=110)
        for index, chapter in enumerate(chapters):
            title = chapter.get("title") or _("Chapter %d") % (index + 1)
            self.list.InsertItem(index, title)
            self.list.SetItem(index, 1, formatting.format_clock(chapter.get("start", 0.0)))
        if chapters:
            index = current_index if 0 <= current_index < len(chapters) else 0
            self.list.Select(index)
            self.list.Focus(index)
            self.list.EnsureVisible(index)

        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activate)

        sizer.Add(label, 0, wx.ALL, 8)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(
            self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 10
        )
        self.SetSizer(outer)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.list.SetFocus()

    def _on_activate(self, event):
        # Enter / double click on a row jumps straight away
        self.EndModal(wx.ID_OK)

    def selected_index(self) -> int:
        return self.list.GetFirstSelected()
