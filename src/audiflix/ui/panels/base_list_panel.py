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

The control is a **virtual** list: it keeps the row values in a Python list and
hands single cells to Windows on demand. Filling a library of several thousand
titles used to insert every row and every cell one by one, which took seconds
and froze the window; the virtual list only has to be told how many rows there
are. To the operating system - and therefore to a screen reader - it is the
same kind of list view as before.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from audiflix.api.models import LibraryItem
from audiflix.helpers.formatting import item_columns, item_row
from audiflix.i18n import _
from audiflix.logging_setup import get_logger

log = get_logger(__name__)


class VirtualListCtrl(wx.ListCtrl):
    """List control that reads its cells from ``rows`` instead of storing them."""

    def __init__(self, parent: wx.Window, columns: int):
        super().__init__(
            parent,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VIRTUAL | wx.BORDER_SUNKEN,
        )
        self._rows: list[list[str]] = []
        self._column_count = columns

    def set_rows(self, rows: list[list[str]]) -> None:
        self._rows = rows
        self.SetItemCount(len(rows))
        self.Refresh()

    def OnGetItemText(self, row: int, column: int) -> str:  # wx calls this name
        if not 0 <= row < len(self._rows):
            return ""
        values = self._rows[row]
        return values[column] if column < len(values) else ""


class BaseListPanel(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        label: str = "",
        columns: list[str] | None = None,
        on_open: Callable[[object], None] | None = None,
        on_back: Callable[[], None] | None = None,
        context_builder: Callable[[object], list[tuple[str, Callable[[], None]]]] | None = None,
        settings_key: str = "",
    ):
        super().__init__(parent)
        self.on_open = on_open
        self.on_back = on_back
        self.context_builder = context_builder
        self._items: list = []
        self._columns = columns or item_columns()
        self._base_label = label
        self._settings_key = settings_key
        self._settings = getattr(getattr(parent, "ctx", None), "settings", None)
        self._retry: Callable | None = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        heading_row = wx.BoxSizer(wx.HORIZONTAL)
        if label:
            self.heading = wx.StaticText(self, label=label, style=wx.ST_ELLIPSIZE_END)
            heading_row.Add(self.heading, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        else:
            self.heading = None
        self.columns_button = wx.Button(self, label=_("&Columns..."))
        self.columns_button.SetName(_("Columns: %s") % (label or _("List")))
        self.columns_button.Bind(wx.EVT_BUTTON, self._choose_columns)
        heading_row.Add(self.columns_button, 0, wx.ALL, 2)
        sizer.Add(heading_row, 0, wx.EXPAND)

        self.message = wx.StaticText(self, label="")
        self._message_text = ""
        self.message.Hide()
        sizer.Add(self.message, 0, wx.EXPAND | wx.ALL, 4)
        self.retry_button = wx.Button(self, label=_("&Retry"))
        self.retry_button.SetName(_("Retry loading this list"))
        self.retry_button.Bind(wx.EVT_BUTTON, self._on_retry)
        self.retry_button.Hide()
        sizer.Add(self.retry_button, 0, wx.ALL, 4)

        self.list_ctrl = VirtualListCtrl(self, len(self._columns))
        self.list_ctrl.SetName(label or _("List"))
        layouts = self._settings.get("list_columns", {}) if self._settings else {}
        saved = layouts.get(settings_key, {}) if isinstance(layouts, dict) else {}
        self._widths = saved.get("widths", []) if isinstance(saved, dict) else []
        self._hidden = set(saved.get("hidden", [])) - {0} if isinstance(saved, dict) else set()
        if not isinstance(self._widths, list) or len(self._widths) != len(self._columns) or not all(isinstance(w, int) for w in self._widths):
            self._widths = [320, *([160] * (len(self._columns) - 1))]
        for index, column in enumerate(self._columns):
            width = max(60, min(2000, int(self._widths[index])))
            self.list_ctrl.InsertColumn(index, column, width=0 if index in self._hidden else self.FromDIP(width))
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 2)
        self.SetSizer(sizer)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activate)
        self.list_ctrl.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.list_ctrl.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)
        self.list_ctrl.Bind(wx.EVT_LIST_COL_END_DRAG, self._on_column_resize)
        self.Bind(wx.EVT_SIZE, self._on_size)

    # --- Data --------------------------------------------------------------
    def set_label(self, text: str) -> None:
        """Update the visible heading and the accessible name of the list."""
        self._base_label = text
        if self.heading is not None:
            self.heading.SetLabel(text)
        self.list_ctrl.SetName(text)
        self.columns_button.SetName(_("Columns: %s") % text)

    @property
    def label(self) -> str:
        return self._base_label

    def set_items(
        self,
        items: list[LibraryItem],
        progress_fn: Callable[[LibraryItem], str] | None = None,
        status_fn: Callable[[LibraryItem], str] | None = None,
    ) -> None:
        """Fill the list with items.

        The optional callables supply the progress and status text of a row;
        they come from the controller, which is what knows about progress and
        downloads.
        """
        rows = [
            item_row(
                item,
                progress_fn(item) if progress_fn else "",
                status_fn(item) if status_fn else "",
            )
            for item in items
        ]
        self.set_rows(rows, list(items))

    def set_rows(self, rows: list[list[str]], payloads: list) -> None:
        """Generic variant with arbitrary column values (authors, series, ...)."""
        selected_index = self.list_ctrl.GetFirstSelected()
        selected_key = self._item_key(self.selected())
        top = max(0, self.list_ctrl.GetTopItem())
        top_key = self._item_key(self._items[top]) if top < len(self._items) else None
        if selected_index >= 0:
            self.list_ctrl.Select(selected_index, False)
        self._items = payloads
        self.list_ctrl.set_rows(rows)
        if rows:
            keys = [self._item_key(item) for item in payloads]
            index = keys.index(selected_key) if selected_key in keys else max(0, min(selected_index, len(rows) - 1))
            self.list_ctrl.Select(index)
            self.list_ctrl.Focus(index)
            target_top = keys.index(top_key) if top_key in keys else min(top, len(rows) - 1)
            if self.list_ctrl.IsShownOnScreen():
                current_top = max(0, min(self.list_ctrl.GetTopItem(), len(rows) - 1))
                height = self.list_ctrl.GetItemRect(current_top).height
                self.list_ctrl.ScrollList(0, (target_top - current_top) * height)
        self.set_message("" if rows else _("No items in this list."))

    @staticmethod
    def _item_key(item):
        if isinstance(item, tuple):
            return tuple(BaseListPanel._item_key(part) for part in item)
        return getattr(item, "id", item) if item is not None else None

    def set_message(self, message: str, retry: Callable | None = None) -> None:
        self._message_text = message
        self.message.SetLabel(message)
        self.message.Wrap(max(200, self.GetClientSize().width - self.FromDIP(8)))
        self.message.Show(bool(message))
        self._retry = retry
        self.retry_button.Show(retry is not None)
        self.Layout()

    def _on_size(self, event: wx.SizeEvent) -> None:
        self.message.SetLabel(self._message_text)
        self.message.Wrap(max(200, self.GetClientSize().width - self.FromDIP(8)))
        event.Skip()

    def _on_retry(self, event: wx.CommandEvent) -> None:
        if self._retry:
            self._retry()

    def load_async(self, ctx, fetch: Callable, show: Callable, key: str, retry: Callable) -> None:
        """Share loading/error states and protect each view from stale replies."""
        self.set_message(_("Loading..."))

        def done(result):
            if not self or self.IsBeingDeleted():
                return
            self.set_message("")
            show(result)

        def failed(exc):
            if not self or self.IsBeingDeleted():
                return
            self.set_message(_("Loading failed: %s") % exc, retry=retry)

        ctx.run_async(fetch, on_done=done, on_error=failed, description=key, request_key=f"view:{key}")

    def save_layout(self) -> None:
        if self._settings is None or not self._settings_key:
            return
        for index in range(len(self._columns)):
            if index not in self._hidden:
                self._widths[index] = self.ToDIP(self.list_ctrl.GetColumnWidth(index))
        layouts = dict(self._settings.get("list_columns", {}) or {})
        layouts[self._settings_key] = {"widths": self._widths[:], "hidden": sorted(self._hidden)}
        self._settings["list_columns"] = layouts

    def _on_column_resize(self, event: wx.ListEvent) -> None:
        event.Skip()
        # Native resizing finishes after this event has been processed.
        wx.CallAfter(self._save_if_alive)

    def _save_if_alive(self) -> None:
        if self and not self.IsBeingDeleted():
            self.save_layout()

    def _choose_columns(self, event: wx.CommandEvent) -> None:
        dlg = wx.MultiChoiceDialog(self, _("Choose additional columns. The first column stays visible."),
                                   _("Visible columns"), self._columns[1:])
        dlg.SetSelections([i - 1 for i in range(1, len(self._columns)) if i not in self._hidden])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            self.save_layout()
            visible = {i + 1 for i in dlg.GetSelections()}
            self._hidden = set(range(1, len(self._columns))) - visible
            for i in range(1, len(self._columns)):
                self.list_ctrl.SetColumnWidth(i, 0 if i in self._hidden else self.FromDIP(self._widths[i]))
            self.save_layout()
        finally:
            dlg.Destroy()

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
