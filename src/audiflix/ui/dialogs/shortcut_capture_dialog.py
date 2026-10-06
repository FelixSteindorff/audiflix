"""Capture a shortcut without triggering the application's menu actions."""

from __future__ import annotations

import wx

from audiflix import speech
from audiflix.i18n import _
from audiflix.ui import shortcuts


class ShortcutCaptureDialog(wx.Dialog):
    def __init__(self, parent, action_label: str, bindings: dict[str, str]):
        super().__init__(parent, title=_("Record shortcut for %s") % action_label)
        self.bindings = bindings
        self.shortcut = ""
        outer = wx.BoxSizer(wx.VERTICAL)
        hint = wx.StaticText(self, label=_(
            "Press the desired key combination. Enter confirms, Escape cancels. "
            "Tab moves to the buttons."
        ))
        hint.Wrap(self.FromDIP(440))
        outer.Add(hint, 0, wx.EXPAND | wx.ALL, 12)
        self.capture = wx.TextCtrl(self, style=wx.TE_READONLY)
        self.capture.SetName(_("Press the desired key combination"))
        outer.Add(self.capture, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        self.status = wx.StaticText(self, label="")
        outer.Add(self.status, 0, wx.EXPAND | wx.ALL, 12)
        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 12)
        self.ok = self.FindWindowById(wx.ID_OK, self)
        self.ok.Enable(False)
        self.SetSizerAndFit(outer)
        self.SetMinSize(self.GetSize())
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.capture.SetFocus()
        self.CentreOnParent()

    def _on_key(self, event: wx.KeyEvent) -> None:
        # Preserve dialog navigation; capture only while the recording field
        # has focus, so Space can still activate the OK/Cancel buttons.
        if wx.Window.FindFocus() is not self.capture:
            event.Skip()
            return
        if event.GetKeyCode() == wx.WXK_ESCAPE and event.GetModifiers() == wx.MOD_NONE:
            self.EndModal(wx.ID_CANCEL)
            return
        if event.GetKeyCode() in (wx.WXK_TAB, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not (
            event.ControlDown() or event.AltDown() or event.MetaDown()
        ):
            event.Skip()
            return
        value = shortcuts.from_key_event(event)
        if value is None:
            return
        self.shortcut = value
        self.capture.ChangeValue(value)
        conflicts = [label for label, binding in self.bindings.items()
                     if binding and shortcuts.parse(binding) == shortcuts.parse(value)]
        self.ok.Enable(not conflicts)
        message = (
            _("Already assigned to: %s") % ", ".join(conflicts)
            if conflicts else _("Shortcut detected: %s. Press Enter to confirm.") % value
        )
        self.status.SetLabel(message)
        self.status.Wrap(self.FromDIP(440))
        self.GetSizer().Fit(self)
        speech.announce(message, interrupt=True)
