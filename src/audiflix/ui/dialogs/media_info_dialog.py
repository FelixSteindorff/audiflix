"""Media details dialog: a read-only text field with all information.

The text lives in a multi-line read-only text control that a screen reader can
read line by line. The control receives the focus when the dialog opens, which
already makes the screen reader read it - so the dialog deliberately does *not*
announce the text a second time.
"""

from __future__ import annotations

import wx

from audiflix.api.models import LibraryItem
from audiflix.helpers import formatting
from audiflix.i18n import _


class MediaInfoDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        item: LibraryItem,
        position: float | None = None,
        duration: float | None = None,
    ):
        super().__init__(
            parent,
            title=_("Media details - %s") % item.title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lines = [f"{label}: {value}" for label, value in item.to_info_lines()]
        if item.duration:
            lines.append(
                _("Total duration: %s") % formatting.format_duration(item.duration)
            )
        if position is not None and duration:
            lines.append(formatting.announce_position(position, duration))
        if item.description:
            lines.append("")
            lines.append(_("Description:"))
            lines.append(item.description)
        text = "\n".join(lines)

        label = wx.StaticText(panel, label=_("&Details:"))
        self.text = wx.TextCtrl(
            panel, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
        )
        self.text.SetName(_("Media details"))

        sizer.Add(label, 0, wx.ALL, 8)
        sizer.Add(self.text, 1, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(self.CreateStdDialogButtonSizer(wx.OK), 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(outer)
        self.SetSize((560, 500))
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_OK)

        self.text.SetInsertionPoint(0)
        self.text.SetFocus()
