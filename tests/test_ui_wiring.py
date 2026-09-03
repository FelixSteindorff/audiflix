"""Tests that build real windows: the menu wiring and the virtual list.

Every function of Audiflix has to be reachable from the menu bar, so a menu
entry without a handler is a broken feature rather than a cosmetic slip. And
because the lists are virtual, the row values no longer live in the control -
these tests check that the cells a screen reader asks for are the right ones.

Skipped where wxPython is not installed.
"""

import pytest

wx = pytest.importorskip("wx")

from audiflix.api.models import LibraryItem
from audiflix.config import Settings
from audiflix.helpers import formatting
from audiflix.ui import menus
from audiflix.ui.panels.base_list_panel import BaseListPanel


@pytest.fixture(scope="module", autouse=True)
def wx_app():
    app = wx.App()
    yield app


def _menu_actions() -> set[str]:
    return {
        entry[0]
        for _label, entries in menus.MENUS
        for entry in entries
        if entry is not None
    }


class _StubClient:
    server_version = ""

    def __init__(self):
        self.user: dict = {}

    def authed_url(self, url):
        return url

    def libraries(self):
        return []


def test_every_menu_entry_has_a_handler(tmp_path, monkeypatch):
    """A menu entry without a handler is a function nobody can reach."""
    monkeypatch.setenv("AUDIFLIX_CONFIG_DIR", str(tmp_path))
    from audiflix.ui.main_frame import MainFrame

    settings = Settings({"global_media_keys": False})
    settings.save = lambda: True
    frame = MainFrame(_StubClient(), settings)
    try:
        missing = sorted(_menu_actions() - set(frame._handlers()))
        assert missing == []
    finally:
        frame.ctx.player.shutdown()
        frame.Destroy()


def test_menu_shortcuts_all_have_a_default():
    from audiflix.config import DEFAULT_SETTINGS

    keys = {
        entry[2]
        for _label, entries in menus.MENUS
        for entry in entries
        if entry is not None and entry[2]
    }
    assert keys <= set(DEFAULT_SETTINGS["shortcuts"])


def test_the_virtual_list_serves_the_right_cells():
    frame = wx.Frame(None)
    try:
        panel = BaseListPanel(frame, label="Books")
        items = [
            LibraryItem({"id": "1", "media": {"metadata": {
                "title": "First", "authorName": "A", "seriesName": "S 1",
            }}}),
            LibraryItem({"id": "2", "media": {"metadata": {"title": "Second"}}}),
        ]
        panel.set_items(items, lambda item: "50% played", lambda item: "Available offline")

        control = panel.list_ctrl
        assert control.GetItemCount() == 2
        assert control.OnGetItemText(0, 0) == "First"
        assert control.OnGetItemText(0, 1) == "A"
        assert control.OnGetItemText(0, 4) == "50% played"
        assert control.OnGetItemText(0, 5) == "Available offline"
        assert control.OnGetItemText(1, 0) == "Second"
        assert control.OnGetItemText(1, 1) == "-"
        # Out of range must not raise: wx asks for rows while it repaints.
        assert control.OnGetItemText(99, 0) == ""
        assert panel.selected() is items[0]
    finally:
        frame.Destroy()


def test_the_list_column_count_matches_the_rows():
    frame = wx.Frame(None)
    try:
        panel = BaseListPanel(frame, label="Books")
        assert panel.list_ctrl.GetColumnCount() == len(formatting.item_columns())
    finally:
        frame.Destroy()


def test_replacing_the_rows_drops_the_old_ones():
    frame = wx.Frame(None)
    try:
        panel = BaseListPanel(frame, label="Books")
        panel.set_rows([["a"], ["b"], ["c"]], [1, 2, 3])
        assert panel.list_ctrl.GetItemCount() == 3
        panel.set_rows([], [])
        assert panel.list_ctrl.GetItemCount() == 0
        assert panel.is_empty() is True
        assert panel.selected() is None
    finally:
        frame.Destroy()
