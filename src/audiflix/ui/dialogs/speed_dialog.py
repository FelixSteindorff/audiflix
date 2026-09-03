"""Set the playback speed of the title that is playing.

The speed can also be nudged with the keyboard while listening; this dialog is
for setting an exact value and for deciding whether it stays with this title or
becomes the default for everything.
"""

from __future__ import annotations

import wx

from audiflix.helpers import formatting
from audiflix.i18n import _


class SpeedDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        current: float,
        default: float,
        title: str = "",
        has_own_speed: bool = False,
    ):
        super().__init__(parent, title=_("Playback speed"))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        if title:
            sizer.Add(wx.StaticText(panel, label=title), 0, wx.ALL, 10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(
            wx.StaticText(panel, label=_("&Speed:")), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6,
        )
        self.speed = wx.SpinCtrlDouble(panel, min=0.5, max=3.5, initial=current, inc=0.05)
        self.speed.SetDigits(2)
        self.speed.SetName(_("Playback speed"))
        row.Add(self.speed, 1)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 10)

        self.remember = wx.CheckBox(panel, label=_("&Remember this speed for this title"))
        self.remember.SetValue(True)
        sizer.Add(self.remember, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.as_default = wx.CheckBox(
            panel, label=_("Use as the &default speed for all titles")
        )
        sizer.Add(self.as_default, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        note = _("The default speed is %s.") % formatting.format_speed(default)
        if has_own_speed:
            note = _("This title has its own speed. The default is %s.") % (
                formatting.format_speed(default)
            )
        sizer.Add(wx.StaticText(panel, label=note), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(outer)
        outer.Fit(self)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.speed.SetFocus()

    def result(self) -> tuple[float, bool, bool]:
        """``(speed, remember for this title, use as the new default)``."""
        return (
            round(self.speed.GetValue(), 2),
            bool(self.remember.GetValue()),
            bool(self.as_default.GetValue()),
        )
