"""Persistent playback controls, independent of transient status messages."""

from __future__ import annotations

import wx

from audiflix.helpers import formatting
from audiflix.i18n import _


class PlaybackPanel(wx.Panel):
    def __init__(self, parent: wx.Window, frame) -> None:
        super().__init__(parent)
        self.ctx = frame.ctx
        outer = wx.BoxSizer(wx.VERTICAL)
        title_row = wx.BoxSizer(wx.HORIZONTAL)
        title_label = wx.StaticText(self, label=_("Now &playing:"))
        self.title = wx.TextCtrl(self, style=wx.TE_READONLY)
        self.title.SetName(_("Now playing"))
        title_row.Add(title_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        title_row.Add(self.title, 1, wx.EXPAND)
        outer.Add(title_row, 0, wx.EXPAND | wx.ALL, 6)
        position_row = wx.BoxSizer(wx.HORIZONTAL)
        position_label = wx.StaticText(self, label=_("Position and &remaining time:"))
        self.position = wx.TextCtrl(self, style=wx.TE_READONLY)
        self.position.SetName(_("Playback position and remaining time"))
        position_row.Add(position_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        position_row.Add(self.position, 1, wx.EXPAND)
        outer.Add(position_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)
        buttons = wx.WrapSizer(wx.HORIZONTAL, flags=wx.REMOVE_LEADING_SPACES)
        self.back = self._button(buttons, _("Skip &back"), self.ctx.skip_back)
        self.play = self._button(buttons, _("&Play"), self.ctx.toggle_play)
        self.forward = self._button(buttons, _("Skip &forward"), self.ctx.skip_forward)
        self.jump = self._button(buttons, _("&Jump..."), frame.open_jump_to_time)
        self.speed = self._button(buttons, _("Speed"), frame.open_speed_dialog)
        self.sleep = self._button(buttons, _("Sleep timer"), frame.open_sleep_timer)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 4)
        self.SetSizer(outer)
        self.refresh()

    def _button(self, sizer: wx.Sizer, label: str, callback) -> wx.Button:
        button = wx.Button(self, label=label)
        button.SetName(label.replace("&", ""))
        button.Bind(wx.EVT_BUTTON, lambda event: callback())
        sizer.Add(button, 0, wx.ALL, 2)
        return button

    def refresh(self) -> None:
        player = self.ctx.player
        loaded = player.has_media
        chapter = player.current_chapter if loaded else None
        title = player.item_title if loaded else _("No title loaded.")
        if chapter:
            title += " — " + (chapter.get("title") or _("Chapter %d") % (player.current_chapter_index + 1))
        if self.title.GetValue() != title:
            self.title.ChangeValue(title)
        text = formatting.announce_position(
            player.position, player.duration,
            compact=self.ctx.settings.get("time_format", "clock") != "words",
        ) if loaded else ""
        if self.position.GetValue() != text:
            self.position.ChangeValue(text)
        labels = (
            (self.play, _("&Pause") if player.is_playing else _("&Play")),
            (self.speed, _("&Speed: %s...") % formatting.format_speed(player.rate)),
            (self.sleep, _("&Sleep: %s...") % self.ctx.format_time(player.sleep_remaining)
             if player.sleep_remaining is not None else _("&Sleep timer...")),
        )
        changed = False
        for button, label in labels:
            if button.GetLabel() != label:
                button.SetLabel(label)
                button.SetName(label.replace("&", ""))
                changed = True
        for button in (self.back, self.play, self.forward, self.jump):
            button.Enable(loaded)
        if changed:
            self.GetParent().Layout()
