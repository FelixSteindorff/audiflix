"""Tests for the chapter model and the player's chapter navigation logic."""

from audiflix.api.models import Chapter, LibraryItem
from audiflix.audio.player import VlcPlayer


def test_library_item_chapters():
    raw = {
        "id": "b1",
        "media": {
            "metadata": {"title": "Book"},
            "chapters": [
                {"id": 0, "start": 0.0, "end": 60.0, "title": "One"},
                {"id": 1, "start": 60.0, "end": 120.0, "title": "Two"},
            ],
        },
    }
    item = LibraryItem(raw)
    chapters = item.chapters
    assert len(chapters) == 2
    assert chapters[1].title == "Two"
    assert chapters[1].start == 60.0


def test_chapter_defaults():
    ch = Chapter({})
    assert ch.title == "(untitled)"
    assert ch.start == 0.0
    assert ch.end == 0.0


def _player_with_chapters():
    p = VlcPlayer()
    p._chapters = [
        {"start": 0.0, "end": 60.0, "title": "One"},
        {"start": 60.0, "end": 120.0, "title": "Two"},
        {"start": 120.0, "end": 180.0, "title": "Three"},
    ]
    return p


def test_has_chapters():
    assert _player_with_chapters().has_chapters is True
    assert VlcPlayer().has_chapters is False


def test_chapter_index_at():
    p = _player_with_chapters()
    assert p.chapter_index_at(0.0) == 0
    assert p.chapter_index_at(59.9) == 0
    assert p.chapter_index_at(60.0) == 1
    assert p.chapter_index_at(125.0) == 2
    assert p.chapter_index_at(999.0) == 2  # past the end -> last chapter


def test_chapter_index_when_empty():
    assert VlcPlayer().chapter_index_at(10.0) == -1


def test_normalize_chapters_sorts():
    result = VlcPlayer._normalize_chapters([
        {"start": 120.0, "title": "Three"},
        {"start": 0.0, "title": "One"},
        {"start": 60.0, "title": "Two"},
    ])
    assert [c["title"] for c in result] == ["One", "Two", "Three"]
