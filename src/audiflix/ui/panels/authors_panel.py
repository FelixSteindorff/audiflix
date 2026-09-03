"""Tab 3: Authors.

* a choice control for sorting (newest / alphabetical),
* a search field for author names.

Enter opens the author's books (sub view); Backspace returns to the author
list.
"""

from __future__ import annotations

import wx

from audiflix.i18n import N_, _
from audiflix.ui.item_actions import author_context_actions, context_actions
from audiflix.ui.panels.base_list_panel import BaseListPanel

SORT_OPTIONS = [N_("Newest"), N_("Alphabetical")]


class AuthorsPanel(wx.Panel):
    def __init__(self, parent, frame):
        super().__init__(parent)
        self.frame = frame
        self.ctx = frame.ctx
        self._authors = []  # loaded Author objects

        sizer = wx.BoxSizer(wx.VERTICAL)
        controls = wx.BoxSizer(wx.HORIZONTAL)
        controls.Add(
            wx.StaticText(self, label=_("&Sort:")), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4,
        )
        self.sort_choice = wx.Choice(self, choices=[_(option) for option in SORT_OPTIONS])
        self.sort_choice.SetName(_("Sort authors"))
        self.sort_choice.SetSelection(1)
        controls.Add(self.sort_choice, 0, wx.RIGHT, 12)
        controls.Add(
            wx.StaticText(self, label=_("Sea&rch:")), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4,
        )
        self.search = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search.SetName(_("Search authors"))
        self.search.SetHint(_("Press Enter to search"))
        controls.Add(self.search, 1)
        sizer.Add(controls, 0, wx.EXPAND | wx.ALL, 4)

        self.authors_list = BaseListPanel(
            self, label=_("Authors"), columns=[_("Author"), _("Books")],
            on_open=self._open_author,
            context_builder=lambda author: author_context_actions(self.frame, author),
        )
        self.books_list = BaseListPanel(
            self, label=_("Books by this author"),
            on_open=lambda item: self.ctx.play_item(item),
            on_back=self._back_to_authors,
            context_builder=lambda item: context_actions(self.frame, item),
        )
        self.books_list.Hide()
        sizer.Add(self.authors_list, 1, wx.EXPAND | wx.ALL, 2)
        sizer.Add(self.books_list, 1, wx.EXPAND | wx.ALL, 2)
        self.SetSizer(sizer)

        self.sort_choice.Bind(wx.EVT_CHOICE, lambda event: self._render_authors())
        self.search.Bind(wx.EVT_TEXT_ENTER, lambda event: self._render_authors())

    def focus_default(self):
        if self.books_list.IsShown():
            self.books_list.focus_list()
        else:
            self.authors_list.focus_list()

    def focus_search(self):
        self.search.SetFocus()
        self.search.SelectAll()

    # --- Loading / rendering authors ---------------------------------------
    def load(self):
        ctx = self.ctx
        lib_ids = ctx.active_library_ids
        if not lib_ids:
            return

        def show(authors):
            self._authors = authors
            self._render_authors()

        ctx.run_async(
            lambda: ctx.client.authors_all(lib_ids), on_done=show, description="authors"
        )

    def _render_authors(self):
        term = self.search.GetValue().strip().lower()
        authors = [a for a in self._authors if term in a.name.lower()] if term else list(self._authors)
        if self.sort_choice.GetSelection() == 0:  # newest
            authors.sort(key=lambda author: author.added_at, reverse=True)
        else:
            authors.sort(key=lambda author: author.name.lower())
        rows = [[author.name, str(author.num_books)] for author in authors]
        self.authors_list.set_rows(rows, authors)
        self.authors_list.set_label(_("Authors (%d)") % len(authors))

    # --- Drill-down ---------------------------------------------------------
    def _open_author(self, author):
        self.show_author(author.id, author.name)

    def show_author(self, author_id: str, author_name: str):
        ctx = self.ctx

        def show(items):
            self.books_list.set_items(items, ctx.item_progress, ctx.item_status)
            self.books_list.set_label(
                _("Books by %(author)s (%(count)d)")
                % {"author": author_name, "count": len(items)}
            )
            self.authors_list.Hide()
            self.books_list.Show()
            self.Layout()
            self.books_list.focus_list()

        ctx.run_async(
            lambda: ctx.client.author_items(author_id),
            on_done=show,
            description="author-items",
        )

    def _back_to_authors(self):
        self.books_list.Hide()
        self.authors_list.Show()
        self.Layout()
        self.authors_list.focus_list()

    def refresh(self):
        self._back_to_authors()
        self.load()
