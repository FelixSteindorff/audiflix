"""Sleep timer dialog with a choice control for the length.

When a timer is already running the dialog opens on "extend": that is what
someone reaching for the sleep timer a second time almost always wants, and the
remaining time is stated in a label the screen reader reads on the way in.
"""

from __future__ import annotations

import wx

from audiflix.helpers import formatting
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

#: Values offered for extending a running timer, in minutes.
EXTEND_OPTIONS: list[tuple[str, int]] = [
    (N_("5 minutes"), 5),
    (N_("10 minutes"), 10),
    (N_("15 minutes"), 15),
    (N_("30 minutes"), 30),
]


class SleepTimerDialog(wx.Dialog):
    def __init__(self, parent, default_minutes: int = 15, remaining: float | None = None):
        super().__init__(parent, title=_("Sleep timer"))
        self.remaining = remaining
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        if remaining is not None:
            sizer.Add(
                wx.StaticText(
                    panel,
                    label=_("Sleep timer running, %s remaining.")
                    % formatting.format_duration(remaining),
                ),
                0, wx.ALL, 10,
            )
            self.extend = wx.CheckBox(panel, label=_("E&xtend the running timer by:"))
            self.extend.SetValue(True)
            self.extend_choice = wx.Choice(
                panel, choices=[_(option[0]) for option in EXTEND_OPTIONS]
            )
            self.extend_choice.SetName(_("Extend the sleep timer by"))
            self.extend_choice.SetSelection(1)
            sizer.Add(self.extend, 0, wx.LEFT | wx.RIGHT, 10)
            sizer.Add(self.extend_choice, 0, wx.EXPAND | wx.ALL, 10)
            self.extend.Bind(wx.EVT_CHECKBOX, self._on_extend_toggled)
        else:
            self.extend = None
            self.extend_choice = None

        label = wx.StaticText(
            panel,
            label=_("Set a new sleep timer &length:") if remaining is not None
            else _("Sleep timer &length:"),
        )
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
        self._on_extend_toggled(None)
        (self.extend_choice or self.choice).SetFocus()

    def _on_extend_toggled(self, event) -> None:
        """Only one of the two ways of setting the timer is active at a time."""
        if self.extend is None:
            return
        extending = self.extend.GetValue()
        self.extend_choice.Enable(extending)
        self.choice.Enable(not extending)

    def get_extension(self) -> float | None:
        """Minutes to add to the running timer, or ``None`` for a new timer."""
        if self.extend is None or not self.extend.GetValue():
            return None
        index = max(0, self.extend_choice.GetSelection())
        return float(EXTEND_OPTIONS[index][1])

    def get_selection(self) -> tuple[float | None, bool]:
        """Return ``(minutes, until_chapter)``."""
        index = max(0, self.choice.GetSelection())
        value = SLEEP_OPTIONS[index][1]
        if value == "chapter":
            return None, True
        return (float(value) if value else None), False
