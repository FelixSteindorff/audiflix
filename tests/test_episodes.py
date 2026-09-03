"""Tests for the podcast episode models and their formatting."""

from audiflix.api.models import Episode, LibraryItem
from audiflix.audio.player import VlcPlayer
from audiflix.helpers import formatting


def test_library_item_episodes_and_recent():
    raw = {
        "id": "pod1",
        "mediaType": "podcast",
        "media": {"metadata": {"title": "My Podcast"}, "episodes": [
            {"id": "e1", "title": "Episode 1", "publishedAt": 1000, "duration": 60},
            {"id": "e2", "title": "Episode 2", "publishedAt": 2000, "duration": 120},
        ]},
        "recentEpisode": {"id": "e2", "title": "Episode 2", "publishedAt": 2000},
    }
    item = LibraryItem(raw)
    assert item.is_podcast
    assert item.num_episodes == 2
    eps = item.episodes
    assert [e.id for e in eps] == ["e1", "e2"]
    assert eps[0].parent_item_id == "pod1"
    recent = item.recent_episode
    assert recent is not None
    assert recent.id == "e2"


def test_recent_episode_none_when_absent():
    item = LibraryItem({"id": "x", "media": {"metadata": {"title": "Book"}}})
    assert item.recent_episode is None


def test_episode_row_columns():
    ep = Episode({"id": "e", "title": "Test", "publishedAt": 0, "pubDate": "2024", "duration": 95})
    row = formatting.episode_row(ep, downloaded=False)
    assert row[0] == "Test"
    assert row[2] == formatting.format_clock(95)
    assert row[3] == formatting.not_downloaded_label()


def test_format_date_fallback():
    assert formatting.format_date(0, "2024") == "2024"
    assert formatting.format_date(0, "") == ""


def test_player_volume_without_vlc():
    p = VlcPlayer(default_volume=80)
    assert p.volume == 80
    assert p.set_volume(150) == 100  # capped
    assert p.set_volume(-5) == 0
    assert p.change_volume(30) == 30
