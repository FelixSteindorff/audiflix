"""Tests for the display formatting (runs without a server or GUI)."""

from audiflix.api.models import LibraryItem
from audiflix.helpers import formatting


def test_format_clock_minutes_and_hours():
    assert formatting.format_clock(0) == "00:00"
    assert formatting.format_clock(65) == "01:05"
    assert formatting.format_clock(3661) == "1:01:01"


def test_format_clock_never_goes_negative():
    assert formatting.format_clock(-30) == "00:00"


def test_format_duration_uses_singular_and_plural():
    assert formatting.format_duration(3600) == "1 hour"
    assert formatting.format_duration(7320) == "2 hours 2 minutes"
    assert formatting.format_duration(45) == "45 seconds"
    assert formatting.format_duration(1) == "1 second"
    assert formatting.format_duration(60) == "1 minute"


def test_announce_position_reports_remaining():
    text = formatting.announce_position(60, 3660)
    assert "Position" in text
    assert "remaining" in text
    assert "1 hour" in text


def test_item_row_columns_and_status():
    item = LibraryItem({
        "id": "x",
        "media": {"metadata": {
            "title": "The Hobbit",
            "authorName": "J.R.R. Tolkien",
            "narratorName": "Rob Inglis",
            "seriesName": "Middle-earth 1",
        }},
    })
    row = formatting.item_row(item, downloaded=True)
    assert row[0] == "The Hobbit"
    assert row[1] == "J.R.R. Tolkien"
    assert row[2] == "Rob Inglis"
    assert row[3] == "Middle-earth 1"
    assert row[4] == formatting.downloaded_label()


def test_item_row_not_downloaded():
    item = LibraryItem({"id": "y", "media": {"metadata": {"title": "T"}}})
    row = formatting.item_row(item, downloaded=False)
    assert row[4] == formatting.not_downloaded_label()
    assert row[1] == "-"


def test_finished_status_label():
    item = LibraryItem({"id": "z", "media": {"metadata": {"title": "T"}}})
    row = formatting.item_row(item, downloaded=False, finished=True)
    assert "Finished" in row[4]


def test_item_row_matches_the_column_count():
    item = LibraryItem({"id": "z", "media": {"metadata": {"title": "T"}}})
    assert len(formatting.item_row(item, downloaded=False)) == len(formatting.item_columns())


def test_item_announce_mentions_all_the_metadata():
    item = LibraryItem({
        "id": "x",
        "media": {"metadata": {
            "title": "The Hobbit",
            "authorName": "Tolkien",
            "narratorName": "Inglis",
            "seriesName": "Middle-earth 1",
        }},
    })
    text = formatting.item_announce(item, downloaded=True)
    assert "The Hobbit" in text
    assert "by Tolkien" in text
    assert "narrated by Inglis" in text
    assert "series Middle-earth 1" in text


def test_format_speed():
    assert formatting.format_speed(1.0) == "1x"
    assert formatting.format_speed(1.5) == "1.5x"
    assert formatting.format_speed(1.25) == "1.25x"


def test_format_position():
    assert formatting.format_position(65, 3661) == "01:05 / 1:01:01"
