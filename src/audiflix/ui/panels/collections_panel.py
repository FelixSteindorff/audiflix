"""Tab 5: Collections.

A list of collections; Enter opens the books they contain (sub view) and
Backspace returns to the collection list.
"""

from __future__ import annotations

import wx

from audiflix.i18n import _
from audiflix.ui.item_actions import context_actions
from audiflix.ui.panels.base_list_panel import BaseListPanel


class CollectionsPanel(wx.Panel):
    def __init__(self, parent, frame):
        super().__init__(parent)
        self.frame = frame
        self.ctx = frame.ctx
        self._collections = []

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.collections_list = BaseListPanel(
            self, label=_("Collections"), columns=[_("Collection"), _("Books")],
            on_open=self._open_collection,
        )
        self.books_list = BaseListPanel(
            self, label=_("Books in this collection"),
            on_open=lambda item: self.ctx.play_item(item),
            on_back=self._back_to_collections,
            context_builder=lambda item: context_actions(self.frame, item),
        )
        self.books_list.Hide()
        sizer.Add(self.collections_list, 1, wx.EXPAND | wx.ALL, 2)
        sizer.Add(self.books_list, 1, wx.EXPAND | wx.ALL, 2)
        self.SetSizer(sizer)

    def focus_default(self):
        if self.books_list.IsShown():
            self.books_list.focus_list()
        else:
            self.collections_list.focus_list()

    def load(self):
        ctx = self.ctx
        lib_ids = ctx.active_library_ids
        if not lib_ids:
            return

        def show(collections):
            self._collections = collections
            rows = [
                [collection.name, str(collection.num_books)] for collection in collections
            ]
            self.collections_list.set_rows(rows, collections)
            self.collections_list.set_label(_("Collections (%d)") % len(collections))

        ctx.run_async(
            lambda: ctx.client.collections_all(lib_ids),
            on_done=show,
            description="collections",
        )

    def _open_collection(self, collection):
        ctx = self.ctx
        books = collection.books
        self.books_list.set_items(books, ctx.is_downloaded, ctx.is_finished)
        self.books_list.set_label(
            _("%(collection)s (%(count)d)")
            % {"collection": collection.name, "count": len(books)}
        )
        self.collections_list.Hide()
        self.books_list.Show()
        self.Layout()
        self.books_list.focus_list()

    def _back_to_collections(self):
        self.books_list.Hide()
        self.collections_list.Show()
        self.Layout()
        self.collections_list.focus_list()

    def refresh(self):
        self._back_to_collections()
        self.load()
