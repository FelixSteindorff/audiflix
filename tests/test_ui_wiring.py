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

pytestmark = pytest.mark.usefixtures("wx_app")


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
        frame.ctx.shutdown()
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


@pytest.mark.parametrize("has_selection, has_playback", [(True, True), (False, True), (False, False)])
def test_title_information_prefers_selection_then_playback(monkeypatch, has_selection, has_playback):
    from types import SimpleNamespace

    from audiflix.ui import item_actions
    from audiflix.ui.main_frame import MainFrame

    selected = object() if has_selection else None
    playing = object() if has_playback else None
    shown, notifications = [], []
    frame = SimpleNamespace(
        focused_item=lambda: selected,
        ctx=SimpleNamespace(current_item=playing, notify=notifications.append),
    )
    monkeypatch.setattr(item_actions, "show_info", lambda _frame, item: shown.append(item))
    MainFrame.show_media_info(frame)
    if has_selection or has_playback:
        assert shown == [selected or playing]
        assert notifications == []
    else:
        assert shown == []
        assert len(notifications) == 1


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


def _item(item_id):
    return LibraryItem({"id": item_id, "media": {"metadata": {"title": item_id}}})


def test_refresh_keeps_selected_id_after_reordering_and_replacing_objects():
    frame = wx.Frame(None)
    try:
        panel = BaseListPanel(frame, label="Books")
        panel.set_items([_item("a"), _item("b"), _item("c")])
        panel.list_ctrl.Select(0, False)
        panel.list_ctrl.Select(1)
        panel.set_items([_item("c"), _item("a"), _item("b")])
        assert panel.selected().id == "b"
        assert panel.list_ctrl.GetFocusedItem() == 2
        panel.set_items([_item("c"), _item("a")])
        assert panel.selected().id == "a"
    finally:
        frame.Destroy()


def test_episode_selection_uses_both_parent_and_episode_id():
    frame = wx.Frame(None)
    try:
        panel = BaseListPanel(frame)
        panel.set_rows([["a"], ["b"]], [(_item("podcast"), _item("a")), (_item("podcast"), _item("b"))])
        panel.list_ctrl.Select(0, False)
        panel.list_ctrl.Select(1)
        panel.set_rows([["b"], ["a"]], [(_item("podcast"), _item("b")), (_item("podcast"), _item("a"))])
        assert panel.selected()[1].id == "b"
    finally:
        frame.Destroy()


def test_column_widths_and_hidden_columns_survive_recreation():
    from types import SimpleNamespace

    frame = wx.Frame(None)
    frame.ctx = SimpleNamespace(settings=Settings())
    try:
        panel = BaseListPanel(frame, label="Books", settings_key="library")
        panel.list_ctrl.SetColumnWidth(0, panel.FromDIP(410))
        panel.save_layout()
        panel._hidden = {2}
        panel.list_ctrl.SetColumnWidth(2, 0)
        panel.save_layout()
        restored = BaseListPanel(frame, label="Bücher", settings_key="library")
        assert restored.ToDIP(restored.list_ctrl.GetColumnWidth(0)) == 410
        assert restored.list_ctrl.GetColumnWidth(2) == 0
        assert restored.list_ctrl.GetColumnWidth(1) > 0
    finally:
        frame.Destroy()


def test_settings_changes_on_all_pages_apply_together_and_cancel_is_safe(monkeypatch):
    from audiflix import speech
    from audiflix.ui.dialogs.settings_dialog import SettingsDialog

    settings = Settings({"book_speeds": {"a": 1.5}})
    monkeypatch.setattr(wx, "MessageBox", lambda *args, **kwargs: wx.YES)
    monkeypatch.setattr(speech, "announce", lambda *args, **kwargs: None)
    dialog = SettingsDialog(None, settings)
    try:
        assert dialog.notebook.GetPageCount() == 5
        assert all(isinstance(dialog.notebook.GetPage(i), wx.ScrolledWindow) for i in range(5))
        dialog._playback._on_forget_speeds(None)
        dialog._playback.skip_back.SetValue(23)
        dialog._general.sync.SetValue(30)
        dialog._accessibility.announce.SetValue(False)
        dialog._accessibility.time_format.SetSelection(1)
        assert settings.get("book_speeds") == {"a": 1.5}
        assert settings.get("skip_back_seconds") == 15
        for page in dialog._pages:
            page.apply()
        assert settings.get("book_speeds") == {}
        assert settings.get("skip_back_seconds") == 23
        assert settings.get("progress_sync_seconds") == 30
        assert settings.get("announce_on_seek") is False
        assert settings.get("time_format") == "words"
    finally:
        dialog.Destroy()


def test_small_window_has_one_overview_list_and_reachable_playback_controls(tmp_path, monkeypatch):
    from audiflix.ui.main_frame import MainFrame

    monkeypatch.setenv("AUDIFLIX_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(MainFrame, "_load_libraries", lambda self: None)
    frame = MainFrame(_StubClient(), Settings({"global_media_keys": False}))
    try:
        frame.SetSize((640, 480))
        frame.Layout()
        frame.content.Layout()
        frame.overview.Layout()
        assert [p.IsShown() for p in frame.overview._lists] == [True, False, False]
        frame.overview.section.SetSelection(1)
        frame.overview._on_section(None)
        assert [p.IsShown() for p in frame.overview._lists] == [False, True, False]
        for control in (frame.playback.title, frame.playback.position, frame.playback.play,
                        frame.playback.jump, frame.playback.speed, frame.playback.sleep):
            assert control.GetRect().bottom <= frame.playback.GetClientSize().height
        assert frame.overview.recent_list.GetSize().height > 70
    finally:
        frame.ctx.shutdown()
        frame.Destroy()


def test_settings_fit_available_screen_and_buttons_stay_below_pages():
    from audiflix.ui.dialogs.settings_dialog import SettingsDialog

    dialog = SettingsDialog(None, Settings())
    try:
        dialog.Layout()
        area = wx.GetClientDisplayRect()
        assert dialog.GetSize().height <= area.height
        assert dialog.GetSize().width <= area.width
        ok = dialog.FindWindowById(wx.ID_OK, dialog)
        assert ok.GetRect().bottom <= dialog.GetClientSize().height
        assert ok.GetRect().top >= dialog.notebook.GetRect().bottom
    finally:
        dialog.Destroy()


def test_window_size_and_column_layout_are_saved_on_close(tmp_path, monkeypatch):
    from audiflix import speech
    from audiflix.ui.main_frame import MainFrame

    monkeypatch.setenv("AUDIFLIX_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(MainFrame, "_load_libraries", lambda self: None)
    monkeypatch.setattr(speech, "announce", lambda *a, **k: None)
    settings = Settings({"global_media_keys": False})
    frame = MainFrame(_StubClient(), settings)
    try:
        frame.library.list.list_ctrl.SetColumnWidth(0, frame.FromDIP(390))
        frame._on_close(wx.CloseEvent())
        restored = Settings.load()
        assert restored.get("window_size") == list(frame.ToDIP(frame.GetSize()))
        assert restored.get("list_columns")["library"]["widths"][0] == 390
    finally:
        frame.Destroy()
