"""Edit media details (title, subtitle, author, narrator, ...).

Produces a metadata dict in the ABS format expected by
``PATCH /api/items/<id>/media`` (keys ``title``, ``subtitle``, ``authorName``,
``narratorName``, ``publisher``, ``publishedYear``, ``description``).
"""

from __future__ import annotations

import wx

from audiflix.api.models import LibraryItem
from audiflix.i18n import N_, _

# (ABS key, label, item attribute, multiline)
FIELDS: list[tuple[str, str, str, bool]] = [
    ("title", N_("&Title:"), "title", False),
    ("subtitle", N_("&Subtitle:"), "subtitle", False),
    ("authorName", N_("&Author:"), "author", False),
    ("narratorName", N_("&Narrator:"), "narrator", False),
    ("publisher", N_("&Publisher:"), "publisher", False),
    ("publishedYear", N_("Published &year:"), "published_year", False),
    ("description", N_("&Description:"), "description", True),
]


class EditMetadataDialog(wx.Dialog):
    def __init__(self, parent, item: LibraryItem):
        super().__init__(
            parent,
            title=_("Edit media details - %s") % item.title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.item = item
        self._ctrls: dict[str, wx.TextCtrl] = {}

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(len(FIELDS), 2, 6, 8)
        grid.AddGrowableCol(1, 1)

        for key, label, attribute, multiline in FIELDS:
            text = _(label)
            static = wx.StaticText(panel, label=text)
            style = wx.TE_MULTILINE if multiline else 0
            ctrl = wx.TextCtrl(
                panel, value=str(getattr(item, attribute, "") or ""), style=style
            )
            ctrl.SetName(text.replace("&", "").rstrip(":"))
            grid.Add(static, 0, wx.ALIGN_TOP | wx.TOP, 4)
            grid.Add(ctrl, 1, wx.EXPAND)
            if multiline:
                ctrl.SetMinSize((-1, 100))
            self._ctrls[key] = ctrl

        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 12)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(
            self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8
        )
        self.SetSizer(outer)
        self.SetSize((560, 500))
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self._ctrls["title"].SetFocus()
        self._ctrls["title"].SelectAll()

    def get_metadata(self) -> dict:
        return {key: ctrl.GetValue().strip() for key, ctrl in self._ctrls.items()}
