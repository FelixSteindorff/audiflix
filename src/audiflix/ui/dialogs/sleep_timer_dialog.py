"""Sleep timer dialog with a choice control for the length."""

from __future__ import annotations

import wx

from audiflix.i18n import N_, _

SLEEP_OPTIONS: list[tuple[str, object]] = [
    (N_("Off"), None),
    (N_("5 minutes"), 5),
    (N_("10 minutes"), 10),
    (N_("15 minutes"), 15),
    (N_("30 minutes"), 30),
    (N_("45 minutes"), 45),
    (N_("60 minutes"), 60),
    (N_("Until the end of the chapter"), "chapter"),
]


class SleepTimerDialog(wx.Dialog):
    def __init__(self, parent, default_minutes: int = 15):
        super().__init__(parent, title=_("Sleep timer"))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(panel, label=_("Sleep timer &length:"))
        self.choice = wx.Choice(panel, choices=[_(option[0]) for option in SLEEP_OPTIONS])
        self.choice.SetName(_("Sleep timer length"))
        default_index = next(
            (i for i, option in enumerate(SLEEP_OPTIONS) if option[1] == default_minutes), 3
        )
        self.choice.SetSelection(default_index)

        sizer.Add(label, 0, wx.ALL, 10)
        sizer.Add(self.choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(
            self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 10
        )
        self.SetSizer(outer)
        outer.Fit(self)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.choice.SetFocus()

    def get_selection(self) -> tuple[float | None, bool]:
        """Return ``(minutes, until_chapter)``."""
        index = max(0, self.choice.GetSelection())
        value = SLEEP_OPTIONS[index][1]
        if value == "chapter":
            return None, True
        return (float(value) if value else None), False
