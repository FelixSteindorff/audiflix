"""Tests for shortcut parsing, validation and conflict detection.

These need wxPython for the key-code parsing, so they are skipped where wx is
not installed (a headless CI runner, for example).
"""

import pytest

wx = pytest.importorskip("wx")

from audiflix.ui import shortcuts


@pytest.fixture(scope="module", autouse=True)
def wx_app():
    app = wx.App()
    yield app


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

    invalid = [key for key, value in DEFAULT_SHORTCUTS.items() if not shortcuts.is_valid(value)]
    assert invalid == []
