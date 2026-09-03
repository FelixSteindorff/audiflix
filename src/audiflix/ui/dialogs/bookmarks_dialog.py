"""Manage bookmarks: list, jump to, rename and delete.

Fully keyboard operable: arrow keys select, Enter jumps to the position, F2
renames, Delete removes. The same actions are available as buttons so they are
discoverable without knowing the keys. All changes go through the controller
asynchronously and refresh the list in place.
"""

from __future__ import annotations

import wx

from audiflix import speech
from audiflix.helpers import formatting
from audiflix.i18n import _


class BookmarksDialog(wx.Dialog):
    def __init__(self, parent, ctx, item, bookmarks):
        super().__init__(
            parent,
            title=_("Bookmarks - %s") % item.title,
            size=(520, 460),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.ctx = ctx
        self.item = item
        self._bookmarks = list(bookmarks)
        self.jump_time: int | None = None

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        hint = wx.StaticText(
            panel,
            label=_(
                "&Bookmarks (Enter jumps to the position, F2 renames, Delete removes):"
            ),
        )
        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list.SetName(_("Bookmarks"))
        self.list.InsertColumn(0, _("Title"), width=300)
        self.list.InsertColumn(1, _("Position"), width=110)

        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activate)
        self.list.Bind(wx.EVT_KEY_DOWN, self._on_key)

        self.jump_button = wx.Button(panel, label=_("&Go to"))
        self.rename_button = wx.Button(panel, label=_("Re&name"))
        self.delete_button = wx.Button(panel, label=_("&Delete"))
        self.jump_button.Bind(wx.EVT_BUTTON, lambda event: self._jump_selected())
        self.rename_button.Bind(wx.EVT_BUTTON, lambda event: self._rename_selected())
        self.delete_button.Bind(wx.EVT_BUTTON, lambda event: self._delete_selected())

        actions = wx.BoxSizer(wx.HORIZONTAL)
        actions.Add(self.jump_button, 0, wx.RIGHT, 6)
        actions.Add(self.rename_button, 0, wx.RIGHT, 6)
        actions.Add(self.delete_button, 0)

        sizer.Add(hint, 0, wx.ALL, 8)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(actions, 0, wx.ALL, 8)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(
            self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 10
        )
        self.SetSizer(outer)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

        self._populate(self._bookmarks)
        self.list.SetFocus()
        if not self._bookmarks:
            speech.announce(_("No bookmarks for this title yet."), interrupt=True)

    # --- Display ------------------------------------------------------------
    def _populate(self, bookmarks) -> None:
        self._bookmarks = list(bookmarks)
        self.list.DeleteAllItems()
        for index, bookmark in enumerate(self._bookmarks):
            self.list.InsertItem(index, bookmark.title or _("Bookmark %d") % (index + 1))
            self.list.SetItem(index, 1, formatting.format_clock(bookmark.time))
        if self._bookmarks:
            self.list.Select(0)
            self.list.Focus(0)
        self._update_buttons()

    def _update_buttons(self) -> None:
        enabled = bool(self._bookmarks)
        for button in (self.jump_button, self.rename_button, self.delete_button):
            button.Enable(enabled)

    def _reload(self) -> None:
        item_id = self.item.id
        self.ctx.run_async(
            lambda: self.ctx.client.bookmarks(item_id),
            on_done=self._populate,
            description="reload-bookmarks",
        )

    def _selected(self):
        index = self.list.GetFirstSelected()
        if 0 <= index < len(self._bookmarks):
            return self._bookmarks[index]
        return None

    # --- Actions ------------------------------------------------------------
    def _on_ok(self, event):
        self._jump_selected()

    def _on_activate(self, event):
        self._jump_selected()

    def _jump_selected(self):
        bookmark = self._selected()
        if bookmark is None:
            speech.announce(_("No bookmark selected."), interrupt=True)
            return
        self.jump_time = bookmark.time
        self.EndModal(wx.ID_OK)

    def _on_key(self, event):
        code = event.GetKeyCode()
        if code == wx.WXK_DELETE:
            self._delete_selected()
        elif code == wx.WXK_F2:
            self._rename_selected()
        else:
            event.Skip()

    def _delete_selected(self):
        bookmark = self._selected()
        if bookmark is None:
            return
        answer = wx.MessageBox(
            _('Delete the bookmark "%s"?') % (bookmark.title or formatting.format_clock(bookmark.time)),
            _("Audiflix"),
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        )
        if answer != wx.YES:
            return
        item_id, time = self.item.id, bookmark.time
        self.ctx.run_async(
            lambda: self.ctx.client.delete_bookmark(item_id, time),
            on_done=lambda _result: self._after_change(_("Bookmark deleted.")),
            description="delete-bookmark",
        )

    def _rename_selected(self):
        bookmark = self._selected()
        if bookmark is None:
            return
        new_title = wx.GetTextFromUser(
            _("New title:"), _("Rename bookmark"), bookmark.title, self
        )
        if not new_title or new_title == bookmark.title:
            return
        item_id, time = self.item.id, bookmark.time
        self.ctx.run_async(
            lambda: self.ctx.client.update_bookmark(item_id, time, new_title),
            on_done=lambda _result: self._after_change(_("Bookmark renamed.")),
            description="rename-bookmark",
        )

    def _after_change(self, message: str) -> None:
        speech.announce(message, interrupt=True)
        self._reload()
