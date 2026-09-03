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
    row = formatting.item_row(item, "42% played", formatting.downloaded_label())
    assert row[0] == "The Hobbit"
    assert row[1] == "J.R.R. Tolkien"
    assert row[2] == "Rob Inglis"
    assert row[3] == "Middle-earth 1"
    assert row[4] == "42% played"
    assert row[5] == formatting.downloaded_label()


def test_item_row_without_progress_or_status():
    item = LibraryItem({"id": "y", "media": {"metadata": {"title": "T"}}})
    row = formatting.item_row(item)
    assert row[1] == "-"
    assert row[4] == formatting.progress_label(0.0)
    assert row[5] == formatting.not_downloaded_label()


def test_download_label_distinguishes_playable_downloads():
    assert formatting.download_label(False) == formatting.not_downloaded_label()
    assert formatting.download_label(True, True) == "Available offline"
    # A zip archive from an older version is on disk but cannot be played.
    assert formatting.download_label(True, False) == "Downloaded (archive)"


def test_progress_column_states_the_remaining_time():
    text = formatting.progress_column(0.5, False, duration=7200, current_time=3600)
    assert "50% played" in text
    assert "1 hour" in text


def test_progress_column_without_a_known_length():
    assert formatting.progress_column(0.5, False) == formatting.progress_label(0.5)
    assert formatting.progress_column(1.0, True, duration=7200) == "Finished"


def test_item_row_matches_the_column_count():
    item = LibraryItem({"id": "z", "media": {"metadata": {"title": "T"}}})
    assert len(formatting.item_row(item)) == len(formatting.item_columns())


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
    text = formatting.item_announce(item, "42% played", formatting.downloaded_label())
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


def test_parse_position_reads_clock_times():
    assert formatting.parse_position("1:23:45") == 5025
    assert formatting.parse_position("23:45") == 1425
    assert formatting.parse_position("90") == 90


def test_parse_position_reads_units_and_percentages():
    assert formatting.parse_position("90m") == 5400
    assert formatting.parse_position("1.5h") == 5400
    assert formatting.parse_position("1,5h") == 5400  # German keyboard
    assert formatting.parse_position("50%", duration=7200) == 3600
    assert formatting.parse_position("150%", duration=7200) == 7200


def test_parse_position_rejects_nonsense():
    assert formatting.parse_position("") is None
    assert formatting.parse_position("later") is None
    assert formatting.parse_position("1:2:3:4") is None
    assert formatting.parse_position("-5") is None
    # A percentage needs a length to be a share of.
    assert formatting.parse_position("50%") is None
