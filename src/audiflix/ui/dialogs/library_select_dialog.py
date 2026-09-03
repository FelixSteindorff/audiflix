"""Library selection.

"All books" combines every book library. Podcast libraries can only be selected
one at a time. The list is navigated with the arrow keys; Enter or OK applies
the selection.
"""

from __future__ import annotations

import wx

from audiflix.i18n import _


class LibrarySelectDialog(wx.Dialog):
    def __init__(self, parent, libraries: list[dict], current_label: str = ""):
        super().__init__(parent, title=_("Select library"))
        self.libraries = libraries
        self._entries: list[tuple[str, object]] = []  # (label, value) value: "all" | dict

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(panel, label=_("&Library:"))

        self.listbox = wx.ListBox(panel, style=wx.LB_SINGLE)
        self.listbox.SetName(_("Library selection"))

        book_libraries = [lib for lib in libraries if lib.get("mediaType") != "podcast"]
        if book_libraries:
            self._entries.append((_("All books"), "all"))
        for library in libraries:
            suffix = _(" (podcast)") if library.get("mediaType") == "podcast" else ""
            self._entries.append((f"{library.get('name', '?')}{suffix}", library))

        self.listbox.Set([entry[0] for entry in self._entries])
        # preselect the current library
        for index, (entry_label, _value) in enumerate(self._entries):
            if entry_label == current_label:
                self.listbox.SetSelection(index)
                break
        else:
            if self._entries:
                self.listbox.SetSelection(0)

        sizer.Add(label, 0, wx.ALL, 8)
        sizer.Add(self.listbox, 1, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(
            self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8
        )
        self.SetSizer(outer)
        self.SetSize((380, 340))
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.listbox.SetFocus()
        self.listbox.Bind(wx.EVT_LISTBOX_DCLICK, lambda event: self.EndModal(wx.ID_OK))

    def get_selection(self):
        """Return "all", a library dict, or None."""
        index = self.listbox.GetSelection()
        if index < 0:
            return None
        return self._entries[index][1]
