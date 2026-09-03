"""Jump to a position in the title that is playing.

One text field takes both forms a listener thinks in: a time (``1:23:45``,
``23:45``, ``90m``) and a share of the book (``45%``). Parsing lives in
:mod:`audiflix.helpers.formatting` so it can be tested without a window.
"""

from __future__ import annotations

import wx

from audiflix.helpers import formatting
from audiflix.i18n import _


class JumpToTimeDialog(wx.Dialog):
    def __init__(self, parent, position: float = 0.0, duration: float = 0.0):
        super().__init__(parent, title=_("Jump to position"))
        self.duration = duration
        self._target: float | None = None

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        current = wx.StaticText(
            panel,
            label=_("Current position: %s") % formatting.format_position(position, duration),
        )
        label = wx.StaticText(panel, label=_("Jump &to:"))
        self.field = wx.TextCtrl(panel, value="", style=wx.TE_PROCESS_ENTER)
        self.field.SetName(_("Position to jump to"))
        self.field.SetHint(_("for example 1:23:45 or 45%"))
        hint = wx.StaticText(
            panel,
            label=_(
                "Enter a time as hours:minutes:seconds or minutes:seconds, or a "
                "percentage of the whole title."
            ),
        )

        sizer.Add(current, 0, wx.ALL, 10)
        sizer.Add(label, 0, wx.LEFT | wx.RIGHT, 10)
        sizer.Add(self.field, 0, wx.EXPAND | wx.ALL, 10)
        sizer.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(outer)
        outer.Fit(self)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.field.Bind(wx.EVT_TEXT_ENTER, self._on_ok)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self.field.SetFocus()

    def _on_ok(self, event) -> None:
        target = formatting.parse_position(self.field.GetValue(), self.duration)
        if target is None:
            wx.MessageBox(
                _(
                    "'%s' is not a position Audiflix understands.\n\n"
                    "Use 1:23:45, 23:45, 90m or 45%%."
                ) % self.field.GetValue(),
                _("Audiflix"), wx.OK | wx.ICON_WARNING, self,
            )
            self.field.SetFocus()
            self.field.SelectAll()
            return
        self._target = target
        self.EndModal(wx.ID_OK)

    @property
    def target(self) -> float | None:
        """The position to jump to, in seconds."""
        return self._target
