"""Add an item to a collection, or create a new collection."""

from __future__ import annotations

import wx

from audiflix.api.models import Collection
from audiflix.i18n import _


class AddToCollectionDialog(wx.Dialog):
    def __init__(self, parent, collections: list[Collection]):
        super().__init__(parent, title=_("Add to collection"))
        self.collections = collections
        self.new_label_text = _("+ Create a new collection...")

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(panel, label=_("&Collection:"))
        choices = [collection.name for collection in collections] + [self.new_label_text]
        self.choice = wx.Choice(panel, choices=choices)
        self.choice.SetName(_("Collection"))
        self.choice.SetSelection(0)

        self.new_label = wx.StaticText(panel, label=_("&Name of the new collection:"))
        self.new_name = wx.TextCtrl(panel)
        self.new_name.SetName(_("Name of the new collection"))
        is_new = not collections
        self.new_label.Show(is_new)
        self.new_name.Show(is_new)

        sizer.Add(label, 0, wx.ALL, 8)
        sizer.Add(self.choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self.new_label, 0, wx.ALL, 8)
        sizer.Add(self.new_name, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(
            self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8
        )
        self.SetSizer(outer)
        self.SetSize((400, 260))
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.choice.SetFocus()
        self.choice.Bind(wx.EVT_CHOICE, self._on_choice)

    def _on_choice(self, event):
        is_new = self.choice.GetStringSelection() == self.new_label_text
        self.new_label.Show(is_new)
        self.new_name.Show(is_new)
        self.Layout()
        if is_new:
            self.new_name.SetFocus()

    def result(self):
        """Return ('existing', Collection), ('new', name) or None."""
        if self.choice.GetStringSelection() == self.new_label_text:
            name = self.new_name.GetValue().strip()
            return ("new", name) if name else None
        index = self.choice.GetSelection()
        if 0 <= index < len(self.collections):
            return ("existing", self.collections[index])
        return None
