"""Accessible ListCtrl base used by every tab.

Provides the one keyboard behaviour the whole application shares:

* arrow up/down: native ListCtrl navigation (the screen reader reads the row),
* Enter: open (``on_open``),
* Backspace: back (``on_back``),
* applications key / Shift+F10 / right click: context menu.

One row corresponds to exactly one :class:`LibraryItem`. The displayed columns
come exclusively from :mod:`audiflix.helpers.formatting`, and the visible
heading is also set as the list's accessible name so a screen reader announces
which list has the focus.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from audiflix.api.models import LibraryItem
from audiflix.helpers.formatting import item_columns, item_row
from audiflix.i18n import _
from audiflix.logging_setup import get_logger

log = get_logger(__name__)


class BaseListPanel(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        label: str = "",
        columns: list[str] | None = None,
        on_open: Callable[[object], None] | None = None,
        on_back: Callable[[], None] | None = None,
        context_builder: Callable[[object], list[tuple[str, Callable[[], None]]]] | None = None,
    ):
        super().__init__(parent)
        self.on_open = on_open
        self.on_back = on_back
        self.context_builder = context_builder
        self._items: list = []
        self._columns = columns or item_columns()
        self._base_label = label

        sizer = wx.BoxSizer(wx.VERTICAL)
        if label:
            self.heading = wx.StaticText(self, label=label)
            sizer.Add(self.heading, 0, wx.ALL, 4)
        else:
            self.heading = None

        self.list_ctrl = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN
        )
        self.list_ctrl.SetName(label or _("List"))
        for index, column in enumerate(self._columns):
            self.list_ctrl.InsertColumn(index, column, width=wx.LIST_AUTOSIZE_USEHEADER)
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 2)
        self.SetSizer(sizer)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activate)
        self.list_ctrl.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.list_ctrl.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)

    # --- Data --------------------------------------------------------------
    def set_label(self, text: str) -> None:
        """Update the visible heading and the accessible name of the list."""
        self._base_label = text
        if self.heading is not None:
            self.heading.SetLabel(text)
        self.list_ctrl.SetName(text)

    @property
    def label(self) -> str:
        return self._base_label

    def set_items(
        self,
        items: list[LibraryItem],
        downloaded_fn: Callable[[LibraryItem], bool] | None = None,
        finished_fn: Callable[[LibraryItem], bool] | None = None,
    ) -> None:
        """Fill the list with items. The optional callables supply the
        download/finished state per item."""
        rows = []
        for item in items:
            downloaded = downloaded_fn(item) if downloaded_fn else False
            finished = finished_fn(item) if finished_fn else False
            rows.append(item_row(item, downloaded, finished))
        self.set_rows(rows, list(items))

    def set_rows(self, rows: list[list[str]], payloads: list) -> None:
        """Generic variant with arbitrary column values (authors, series, ...)."""
        self._items = payloads
        self.list_ctrl.Freeze()
        try:
            self.list_ctrl.DeleteAllItems()
            for row, values in enumerate(rows):
                self.list_ctrl.InsertItem(row, values[0] if values else "")
                for column in range(1, len(self._columns)):
                    self.list_ctrl.SetItem(
                        row, column, values[column] if column < len(values) else ""
                    )
        finally:
            self.list_ctrl.Thaw()
        if rows:
            self.list_ctrl.Select(0)
            self.list_ctrl.Focus(0)

    def is_empty(self) -> bool:
        return not self._items

    def selected(self):
        index = self.list_ctrl.GetFirstSelected()
        if index < 0 or index >= len(self._items):
            return None
        return self._items[index]

    def focus_list(self) -> None:
        self.list_ctrl.SetFocus()
        if self._items and self.list_ctrl.GetFirstSelected() < 0:
            self.list_ctrl.Select(0)
            self.list_ctrl.Focus(0)

    # --- Events ------------------------------------------------------------
    def _on_activate(self, event: wx.Event) -> None:
        item = self.selected()
        if item is not None and self.on_open:
            self.on_open(item)

    def _on_key(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key == wx.WXK_BACK:
            if self.on_back:
                self.on_back()
                return
            event.Skip()
            return
        if key == wx.WXK_WINDOWS_MENU or (key == wx.WXK_F10 and event.ShiftDown()):
            self._show_context()
            return
        event.Skip()

    def _on_context_menu(self, event: wx.Event) -> None:
        self._show_context()

    def _show_context(self) -> None:
        item = self.selected()
        if item is None or self.context_builder is None:
            return
        try:
            entries = self.context_builder(item)
        except Exception:
            log.exception("Could not build the context menu")
            return
        if not entries:
            return
        menu = wx.Menu()
        try:
            for label, callback in entries:
                menu_item = menu.Append(wx.ID_ANY, label)
                menu.Bind(wx.EVT_MENU, lambda event, cb=callback: cb(), menu_item)
            # Popping the menu up on the list control keeps it anchored to the
            # focused row, which is where a screen reader expects it.
            self.list_ctrl.PopupMenu(menu)
        finally:
            menu.Destroy()
