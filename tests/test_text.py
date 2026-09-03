"""Tests for the UI-independent text helpers.

These used to live inside a wx dialog module, which made them impossible to
test without a GUI toolkit installed.
"""

from audiflix.helpers.text import (
    MAX_NAME_LENGTH,
    safe_file_name,
    safe_folder_name,
    truncate,
)


def test_safe_folder_name_removes_illegal_characters():
    assert safe_folder_name("Serial: Killers") == "Serial Killers"
    assert safe_folder_name("Show/Name") == "ShowName"
    assert safe_folder_name("Bad*?<>|") == "Bad"


def test_safe_folder_name_falls_back_when_empty():
    assert safe_folder_name("   ") == "Podcast"
    assert safe_folder_name("") == "Podcast"
    assert safe_folder_name("***", fallback="Feed") == "Feed"


def test_safe_folder_name_keeps_normal_names():
    assert safe_folder_name("Normal Name") == "Normal Name"


def test_safe_folder_name_strips_trailing_dots_and_spaces():
    # Windows silently drops these, which would break path comparisons.
    assert safe_folder_name("Podcast. ") == "Podcast"


def test_safe_folder_name_escapes_reserved_device_names():
    assert safe_folder_name("CON") == "_CON"
    assert safe_folder_name("com1.stuff") == "_com1.stuff"


def test_safe_folder_name_is_length_limited():
    assert len(safe_folder_name("x" * 500)) == MAX_NAME_LENGTH


def test_safe_file_name_replaces_instead_of_removing():
    assert safe_file_name("A/B:C") == "A_B_C"
    assert safe_file_name("   ", fallback="item") == "item"


def test_truncate():
    assert truncate("short", 10) == "short"
    assert truncate("x" * 20, 10) == "xxxxxxx..."
    assert truncate("  padded  ", 10) == "padded"
