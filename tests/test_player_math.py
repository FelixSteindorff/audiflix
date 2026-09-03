"""Tests for the position calculation across tracks (no VLC needed)."""

from audiflix.audio.player import Track, VlcPlayer


def _player_with_tracks():
    player = VlcPlayer()
    # set the tracks directly, without initialising VLC
    player._tracks = [
        Track(content_url="/a", start_offset=0.0, duration=100.0),
        Track(content_url="/b", start_offset=100.0, duration=150.0),
        Track(content_url="/c", start_offset=250.0, duration=50.0),
    ]
    player._total_duration = 300.0
    return player


def test_locate_within_first_track():
    p = _player_with_tracks()
    assert p._locate(30.0) == (0, 30.0)


def test_locate_within_second_track():
    p = _player_with_tracks()
    assert p._locate(180.0) == (1, 80.0)


def test_locate_boundary_goes_to_next_track():
    p = _player_with_tracks()
    # exactly on the boundary the next track starts
    assert p._locate(100.0) == (1, 0.0)


def test_locate_past_end_clamps_to_last_track():
    p = _player_with_tracks()
    index, offset = p._locate(999.0)
    assert index == 2
    assert offset >= 0.0
