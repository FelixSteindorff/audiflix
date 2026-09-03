"""Tab 4: Series.

* a choice control for sorting (newest / alphabetical),
* a search field for series names.

Enter opens the books of a series (in reading order); Backspace returns to the
series list. The books are already contained in the series response, so opening
a series needs no further server call.
"""

from __future__ import annotations

import wx

from audiflix.i18n import N_, _
from audiflix.ui.item_actions import context_actions
from audiflix.ui.panels.base_list_panel import BaseListPanel

SORT_OPTIONS = [N_("Newest"), N_("Alphabetical")]


class SeriesPanel(wx.Panel):
    def __init__(self, parent, frame):
        super().__init__(parent)
        self.frame = frame
        self.ctx = frame.ctx
        self._series = []  # loaded Series objects

        sizer = wx.BoxSizer(wx.VERTICAL)
        controls = wx.BoxSizer(wx.HORIZONTAL)
        controls.Add(
            wx.StaticText(self, label=_("&Sort:")), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4,
        )
        self.sort_choice = wx.Choice(self, choices=[_(option) for option in SORT_OPTIONS])
        self.sort_choice.SetName(_("Sort series"))
        self.sort_choice.SetSelection(1)
        controls.Add(self.sort_choice, 0, wx.RIGHT, 12)
        controls.Add(
            wx.StaticText(self, label=_("Sea&rch:")), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4,
        )
        self.search = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search.SetName(_("Search series"))
        self.search.SetHint(_("Press Enter to search"))
        controls.Add(self.search, 1)
        sizer.Add(controls, 0, wx.EXPAND | wx.ALL, 4)

        self.series_list = BaseListPanel(
            self, label=_("Series"), columns=[_("Series"), _("Books")],
            on_open=self._open_series,
        )
        self.books_list = BaseListPanel(
            self, label=_("Books in this series"),
            on_open=lambda item: self.ctx.play_item(item),
            on_back=self._back_to_series,
            context_builder=lambda item: context_actions(self.frame, item),
        )
        self.books_list.Hide()
        sizer.Add(self.series_list, 1, wx.EXPAND | wx.ALL, 2)
        sizer.Add(self.books_list, 1, wx.EXPAND | wx.ALL, 2)
        self.SetSizer(sizer)

        self.sort_choice.Bind(wx.EVT_CHOICE, lambda event: self._render_series())
        self.search.Bind(wx.EVT_TEXT_ENTER, lambda event: self._render_series())

    def focus_default(self):
        if self.books_list.IsShown():
            self.books_list.focus_list()
        else:
            self.series_list.focus_list()

    def focus_search(self):
        self.search.SetFocus()
        self.search.SelectAll()

    # --- Loading / rendering series -----------------------------------------
    def load(self):
        ctx = self.ctx
        lib_ids = ctx.active_library_ids
        if not lib_ids:
            return

        def show(series):
            self._series = series
            self._render_series()

        ctx.run_async(
            lambda: ctx.client.series_all(lib_ids), on_done=show, description="series"
        )

    def _render_series(self):
        term = self.search.GetValue().strip().lower()
        series = [s for s in self._series if term in s.name.lower()] if term else list(self._series)
        if self.sort_choice.GetSelection() == 0:  # newest
            series.sort(key=lambda entry: entry.added_at, reverse=True)
        else:
            series.sort(key=lambda entry: entry.name.lower())
        rows = [[entry.name, str(entry.num_books)] for entry in series]
        self.series_list.set_rows(rows, series)
        self.series_list.set_label(_("Series (%d)") % len(series))

    # --- Drill-down ---------------------------------------------------------
    def _open_series(self, series):
        ctx = self.ctx
        books = series.books
        self.books_list.set_items(books, ctx.is_downloaded, ctx.is_finished)
        self.books_list.set_label(
            _("Series %(name)s (%(count)d)") % {"name": series.name, "count": len(books)}
        )
        self.series_list.Hide()
        self.books_list.Show()
        self.Layout()
        self.books_list.focus_list()

    def _back_to_series(self):
        self.books_list.Hide()
        self.series_list.Show()
        self.Layout()
        self.series_list.focus_list()

    def refresh(self):
        self._back_to_series()
        self.load()
