"""Tests for shortcut parsing, validation and conflict detection.

These need wxPython for the key-code parsing, so they are skipped where wx is
not installed (a headless CI runner, for example).
"""

import pytest

wx = pytest.importorskip("wx")

from audiflix.ui import shortcuts

pytestmark = pytest.mark.usefixtures("wx_app")


@pytest.mark.parametrize(
    "text",
    ["Ctrl+Space", "Ctrl+Shift+C", "F5", "Ctrl+Left", "Ctrl+,", "Ctrl++", "Ctrl+-", "Q",
     "Alt+Right", "ctrl+shift+b"],
)
def test_valid_shortcuts(text):
    assert shortcuts.is_valid(text)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "Ctrl+", "Blah+X", "Strg+A", "xyz", "Ctrl+Shift+", "Meta+A"],
)
def test_invalid_shortcuts(text):
    """wx.AcceleratorEntry.FromString accepts 'Blah+X' - we must not."""
    assert not shortcuts.is_valid(text)


def test_split_handles_a_plus_key():
    assert shortcuts.split_shortcut("Ctrl++") == (["Ctrl"], "+")
    assert shortcuts.split_shortcut("+") == ([], "+")
    assert shortcuts.split_shortcut("Ctrl+Shift+C") == (["Ctrl", "Shift"], "C")


def test_parse_collects_the_modifier_flags():
    flags, keycode = shortcuts.parse("Ctrl+Shift+C")
    assert flags == wx.ACCEL_CTRL | wx.ACCEL_SHIFT
    assert keycode == ord("C")


def test_case_is_irrelevant():
    assert shortcuts.parse("ctrl+a") == shortcuts.parse("Ctrl+A")


def _key_event(key, *, ctrl=False, alt=False, shift=False, meta=False):
    event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    event.SetKeyCode(key)
    event.SetControlDown(ctrl)
    event.SetAltDown(alt)
    event.SetShiftDown(shift)
    event.SetMetaDown(meta)
    return event


@pytest.mark.parametrize("key, modifiers, expected", [
    (ord("B"), {"ctrl": True, "shift": True}, "Ctrl+Shift+B"),
    (wx.WXK_LEFT, {"alt": True}, "Alt+Left"),
    (wx.WXK_F5, {}, "F5"),
    (wx.WXK_SPACE, {"ctrl": True}, "Ctrl+Space"),
    (ord("+"), {"ctrl": True}, "Ctrl++"),
    (ord(","), {"ctrl": True}, "Ctrl+,"),
    (wx.WXK_TAB, {"ctrl": True}, "Ctrl+Tab"),
])
def test_captured_keys_roundtrip_into_menu_accelerators(key, modifiers, expected):
    result = shortcuts.from_key_event(_key_event(key, **modifiers))
    assert result is not None
    assert shortcuts.parse(result) == shortcuts.parse(expected)


@pytest.mark.parametrize("key, modifiers", [
    (wx.WXK_CONTROL, {"ctrl": True}),
    (wx.WXK_SHIFT, {"shift": True}),
    (wx.WXK_ALT, {"alt": True}),
    (ord("B"), {"meta": True}),
])
def test_modifiers_alone_and_unsupported_system_keys_are_not_recorded(key, modifiers):
    assert shortcuts.from_key_event(_key_event(key, **modifiers)) is None


def test_capture_blocks_conflicts_and_preserves_navigation(monkeypatch):
    from unittest.mock import Mock

    from audiflix import speech
    from audiflix.ui.dialogs.shortcut_capture_dialog import ShortcutCaptureDialog

    announce = Mock()
    monkeypatch.setattr(speech, "announce", announce)
    dialog = ShortcutCaptureDialog(None, "Download", {"Refresh": "F5"})
    monkeypatch.setattr(wx.Window, "FindFocus", lambda: dialog.capture)
    monkeypatch.setattr(dialog, "EndModal", Mock())
    try:
        assert not dialog.ok.IsEnabled()
        dialog._on_key(_key_event(wx.WXK_F5))
        assert not dialog.ok.IsEnabled()
        assert "Refresh" in dialog.status.GetLabel()
        event = _key_event(ord("D"), ctrl=True)
        dialog._on_key(event)
        assert not event.GetSkipped()  # Prevent the parent menu from handling it.
        assert dialog.ok.IsEnabled()
        assert dialog.shortcut == "Ctrl+D"
        assert "Ctrl+D" in announce.call_args.args[0]
        for key in (wx.WXK_TAB, wx.WXK_RETURN):
            event = _key_event(key)
            dialog._on_key(event)
            assert event.GetSkipped()
            assert dialog.shortcut == "Ctrl+D"
        dialog._on_key(_key_event(wx.WXK_ESCAPE))
        dialog.EndModal.assert_called_once_with(wx.ID_CANCEL)
    finally:
        dialog.Destroy()


@pytest.mark.parametrize("result", [wx.ID_OK, wx.ID_CANCEL])
def test_recorded_shortcut_is_staged_only_after_confirmation(monkeypatch, result):
    from audiflix.config import Settings
    from audiflix.ui.dialogs import settings_dialog

    class FakeCapture:
        shortcut = "Ctrl+D"

        def __init__(self, parent, label, bindings):
            assert "Ctrl+D" not in bindings.values()

        def ShowModal(self):
            return result

        def Destroy(self):
            pass

    monkeypatch.setattr(settings_dialog, "ShortcutCaptureDialog", FakeCapture)
    settings = Settings()
    frame = wx.Frame(None)
    try:
        page = settings_dialog._ShortcutPage(frame, settings)
        page._focused_key = "ctx_download"
        page._on_record(None)
        expected = "Ctrl+D" if result == wx.ID_OK else ""
        assert page.values()["ctx_download"] == expected
        assert settings.shortcut("ctx_download") == ""
        page.apply()
        assert settings.shortcut("ctx_download") == expected
    finally:
        frame.Destroy()


def test_normalize_produces_a_canonical_spelling():
    assert shortcuts.normalize("ctrl+a") == shortcuts.normalize("Ctrl+A")
    assert shortcuts.normalize("nonsense") is None


def test_to_entry_binds_the_command_id():
    entry = shortcuts.to_entry("Ctrl+Q", 4242)
    assert entry is not None
    assert entry.GetCommand() == 4242


def test_to_entry_rejects_invalid_input():
    assert shortcuts.to_entry("Blah+X", 1) is None
    assert shortcuts.to_entry("", 1) is None


def test_find_conflicts_reports_duplicates_across_spellings():
    conflicts = shortcuts.find_conflicts(
        {"play_pause": "Ctrl+A", "search": "ctrl+a", "quit": "Ctrl+Q"}
    )
    assert len(conflicts) == 1
    actions = next(iter(conflicts.values()))
    assert sorted(actions) == ["play_pause", "search"]


def test_find_conflicts_ignores_empty_and_invalid_entries():
    conflicts = shortcuts.find_conflicts(
        {"a": "", "b": "", "c": "Blah+X", "d": "nope", "e": "Ctrl+Q"}
    )
    assert conflicts == {}


def test_defaults_have_no_conflicts():
    from audiflix.config import DEFAULT_SHORTCUTS

    assert shortcuts.find_conflicts(DEFAULT_SHORTCUTS) == {}


def test_defaults_are_all_valid():
    from audiflix.config import DEFAULT_SHORTCUTS

    invalid = [key for key, value in DEFAULT_SHORTCUTS.items() if value and not shortcuts.is_valid(value)]
    assert invalid == []


def test_every_menu_command_is_configurable_and_listed_once():
    from audiflix.config import DEFAULT_SHORTCUTS
    from audiflix.ui.dialogs.settings_dialog import SHORTCUT_LABELS
    from audiflix.ui.menus import MENUS

    entries = [entry for _label, group in MENUS for entry in group if entry is not None]
    keys = [key for key, _label in SHORTCUT_LABELS]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(DEFAULT_SHORTCUTS) == {entry[0] for entry in entries}
    assert all(entry[2] == entry[0] and entry[3] is None for entry in entries)
    assert "media_info" in keys
    assert "ctx_info" not in keys


def test_shortcut_editing_detects_conflicts_and_updates_saved_menu(tmp_path, monkeypatch):
    from audiflix.config import Settings
    from audiflix.ui.dialogs.settings_dialog import _ShortcutPage
    from audiflix.ui.menus import build_menubar

    monkeypatch.setenv("AUDIFLIX_CONFIG_DIR", str(tmp_path))
    settings = Settings({"shortcuts": {"play_pause": "Ctrl+P", "search": ""}})
    frame = wx.Frame(None)
    menubar = None
    try:
        page = _ShortcutPage(frame, settings)
        page._ctrls["ctx_download"].SetValue("F5")
        assert page.validate() is not None  # Conflicts with refresh.
        page._ctrls["refresh"].SetValue("")
        page._ctrls["shortcuts"].SetValue("")
        page._ctrls["tab_overview"].SetValue("Ctrl+9")
        assert page.validate() is None
        page.apply()
        assert settings.save()
        restored = Settings.load()
        assert restored.shortcut("play_pause") == "Ctrl+P"
        assert restored.shortcut("search") == ""
        menubar, ids = build_menubar(restored, {})
        for action, expected in {"ctx_download": "F5", "tab_overview": "Ctrl+9"}.items():
            accel = menubar.FindItemById(ids[action]).GetAccel()
            assert (accel.GetFlags(), accel.GetKeyCode()) == shortcuts.parse(expected)
        for action in ("refresh", "shortcuts", "search"):
            assert menubar.FindItemById(ids[action]).GetAccel() is None
    finally:
        if menubar is not None:
            menubar.Destroy()
        frame.Destroy()


def test_shortcut_help_reports_custom_and_disabled_bindings():
    from types import SimpleNamespace

    from audiflix.config import Settings
    from audiflix.ui.main_frame import MainFrame

    shown = []
    frame = SimpleNamespace(
        settings=Settings({"shortcuts": {
            "refresh": "Ctrl+R", "tab_overview": "Ctrl+9", "shortcuts": "",
        }}),
        _show_text_dialog=lambda title, text: shown.append(text),
    )
    MainFrame.show_shortcuts(frame)
    assert "Ctrl+R" in shown[0]
    assert "Ctrl+9" in shown[0]
    assert "F5" not in shown[0]
    assert "Ctrl+1" not in shown[0]
