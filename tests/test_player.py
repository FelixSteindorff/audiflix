"""Tests for player behaviour that does not require a running VLC."""

import threading
import time

import pytest

from audiflix.audio.player import ProgressReport, Track, VlcPlayer


def test_track_url_defaults_to_the_content_url():
    track = Track(content_url="/api/items/1/file/2", start_offset=0.0, duration=10.0)
    assert track.url == "/api/items/1/file/2"


def test_track_keeps_an_explicit_url():
    track = Track(content_url="/rel", start_offset=0.0, duration=1.0, url="https://h/rel?token=t")
    assert track.url == "https://h/rel?token=t"


def test_resolver_refreshes_the_url_before_playback():
    """Access tokens expire, so the URL is rebuilt right before a track plays."""
    player = VlcPlayer(url_resolver=lambda content_url: f"https://h{content_url}?token=fresh")
    track = Track(content_url="/api/items/1/file/2", start_offset=0.0, duration=10.0)
    assert player._resolve(track) == "https://h/api/items/1/file/2?token=fresh"
    assert track.url == "https://h/api/items/1/file/2?token=fresh"


def test_failing_resolver_keeps_the_previous_url():
    def broken(_content_url):
        raise RuntimeError("network down")

    player = VlcPlayer(url_resolver=broken)
    track = Track(content_url="/rel", start_offset=0.0, duration=1.0, url="https://h/old")
    assert player._resolve(track) == "https://h/old"


def test_resolver_returning_nothing_keeps_the_previous_url():
    player = VlcPlayer(url_resolver=lambda _content_url: "")
    track = Track(content_url="/rel", start_offset=0.0, duration=1.0, url="https://h/old")
    assert player._resolve(track) == "https://h/old"


def test_rate_is_clamped_to_a_sensible_range():
    player = VlcPlayer()
    assert player.set_rate(0.1) == 0.5
    assert player.set_rate(9.0) == 3.5
    assert player.set_rate(1.5) == 1.5


def test_change_rate_rounds():
    player = VlcPlayer(default_rate=1.0)
    assert player.change_rate(0.1) == 1.1


def test_sleep_timer_can_be_set_and_cancelled():
    player = VlcPlayer()
    assert player.sleep_remaining is None
    player.set_sleep_timer(10)
    remaining = player.sleep_remaining
    # A deadline of monotonic() + 600 can read back a hair above 600, so this
    # compares with a tolerance rather than an exact upper bound.
    assert remaining == pytest.approx(600, abs=10)
    player.cancel_sleep_timer()
    assert player.sleep_remaining is None


def test_until_chapter_timer_has_no_deadline():
    player = VlcPlayer()
    player.set_sleep_timer(None, until_chapter=True)
    assert player.sleep_remaining is None
    assert player._sleep_until_chapter is True


def test_normalize_chapters_ignores_non_dict_entries():
    result = VlcPlayer._normalize_chapters([{"start": 1.0, "title": "A"}, None, "nope"])
    assert [c["title"] for c in result] == ["A"]


def test_position_is_zero_without_media():
    player = VlcPlayer()
    assert player.position == 0.0
    assert player.has_media is False
    assert player.is_playing is False


class _FakeVlcPlayer:
    """Records what the player asks of libvlc, without needing libvlc."""

    def __init__(self):
        self.media = None
        self.played = False
        self.paused = False
        self.time_set = None
        self.time_ms = 0
        self.playing = False
        self.volume_set = None

    def set_media(self, media):
        self.media = media

    def get_media(self):
        return self.media

    def play(self):
        self.played = True

    def set_pause(self, flag):
        self.paused = bool(flag)

    def set_time(self, value):
        self.time_set = value

    def set_rate(self, rate):
        pass

    def audio_set_volume(self, volume):
        self.volume_set = volume

    def get_length(self):
        return 1000

    def get_time(self):
        return self.time_ms

    def is_playing(self):
        return self.playing

    def get_state(self):
        return None

    def stop(self):
        pass


class _FakeInstance:
    def __init__(self):
        self.created = []

    def media_new(self, url):
        self.created.append(url)
        return f"media:{url}"


def _prepared_player(monkeypatch):
    player = VlcPlayer(url_resolver=lambda content_url: f"https://h{content_url}?token=t")
    instance = _FakeInstance()
    player._instance = instance
    player._player = _FakeVlcPlayer()
    monkeypatch.setattr(player, "_ensure_vlc", lambda: None)
    monkeypatch.setattr(player, "_start_thread", lambda: None)
    monkeypatch.setattr(player, "_seek_when_ready", lambda offset, generation: None)
    return player, instance


def test_loading_a_second_title_replaces_the_media(monkeypatch):
    """Regression: track 0 of a new book must not reuse the old book's media."""
    player, instance = _prepared_player(monkeypatch)

    player.load([{"content_url": "/first"}], total_duration=100.0, item_title="First")
    assert instance.created == ["https://h/first?token=t"]

    player.load([{"content_url": "/second"}], total_duration=100.0, item_title="Second")
    assert instance.created == ["https://h/first?token=t", "https://h/second?token=t"]
    assert player._player.get_media() == "media:https://h/second?token=t"


def test_load_starts_at_the_requested_position(monkeypatch):
    player, instance = _prepared_player(monkeypatch)
    player.load(
        [
            {"content_url": "/a", "start_offset": 0.0, "duration": 100.0},
            {"content_url": "/b", "start_offset": 100.0, "duration": 100.0},
        ],
        total_duration=200.0,
        start_time=150.0,
    )
    assert instance.created == ["https://h/b?token=t"]
    assert player._index == 1


def _player_with_chapters(monkeypatch):
    """A player positioned inside a single file with two chapters."""
    player, _instance = _prepared_player(monkeypatch)
    player._tracks = [Track(content_url="/a", start_offset=0.0, duration=180.0)]
    player._total_duration = 180.0
    player._index = 0
    player._chapters = VlcPlayer._normalize_chapters(
        [
            {"start": 0.0, "end": 60.0, "title": "One"},
            {"start": 60.0, "end": 120.0, "title": "Two"},
        ]
    )
    return player


def test_sleep_until_chapter_remembers_the_chapter_end(monkeypatch):
    player = _player_with_chapters(monkeypatch)
    player._player.time_ms = 10_000  # 10 s in, so inside chapter one
    player.set_sleep_timer(None, until_chapter=True)
    assert player._sleep_chapter_end == 60.0


def test_sleep_until_chapter_stops_at_the_chapter_end(monkeypatch):
    """Regression: a book in a single file ends exactly once, so waiting for
    the end of a *track* would never stop at a chapter mark."""
    player = _player_with_chapters(monkeypatch)
    slept = []
    player.on_sleep = lambda: slept.append(True)

    player._player.time_ms = 10_000
    player.set_sleep_timer(None, until_chapter=True)

    player._tick()
    assert slept == []  # still in the middle of the chapter

    player._player.time_ms = 59_500  # close enough to the chapter end
    player._tick()
    assert slept == [True]
    assert player._player.paused is True
    assert player._sleep_until_chapter is False
    assert player._sleep_chapter_end is None


def test_sleep_until_chapter_without_chapters_waits_for_the_track(monkeypatch):
    """Without chapter marks there is nothing to watch, so the end of the
    track remains the trigger."""
    player, _instance = _prepared_player(monkeypatch)
    player._tracks = [Track(content_url="/a", start_offset=0.0, duration=180.0)]
    player._total_duration = 180.0
    player.set_sleep_timer(None, until_chapter=True)
    assert player._sleep_until_chapter is True
    assert player._sleep_chapter_end is None


def test_chapter_end_falls_back_to_the_next_chapter_start(monkeypatch):
    """Some servers send chapters without an "end"."""
    player, _instance = _prepared_player(monkeypatch)
    player._tracks = [Track(content_url="/a", start_offset=0.0, duration=180.0)]
    player._total_duration = 180.0
    player._chapters = VlcPlayer._normalize_chapters(
        [{"start": 0.0, "title": "One"}, {"start": 90.0, "title": "Two"}]
    )
    assert player._current_chapter_end() == 90.0


def test_a_stale_seek_is_dropped(monkeypatch):
    """A seek that waited for the length must not be applied to the track that
    is playing by then."""
    player, _instance = _prepared_player(monkeypatch)
    monkeypatch.undo()  # _seek_when_ready is the function under test here
    player._player = _FakeVlcPlayer()
    player._load_generation = 5

    player._seek_when_ready(12.0, generation=4).join(timeout=2.0)
    assert player._player.time_set is None

    player._seek_when_ready(12.0, generation=5).join(timeout=2.0)
    assert player._player.time_set == 12_000


def test_progress_sync_does_not_block_the_caller():
    """Pause and stop report progress from the UI thread; a slow server must
    not freeze the window."""
    started = threading.Event()
    release = threading.Event()
    reports = []

    def slow_progress(position, duration, is_finished, listened):
        reports.append((position, duration, is_finished))
        started.set()
        release.wait(5)

    player = VlcPlayer(on_progress=slow_progress)
    player._tracks = [Track(content_url="/a", start_offset=0.0, duration=10.0)]
    player._total_duration = 10.0

    player._sync_now()  # returns while the callback is still running
    assert started.wait(2) is True
    release.set()
    player.flush_sync(timeout=2.0)
    assert reports == [(0.0, 10.0, False)]


def test_a_newer_report_keeps_what_the_queued_one_carried(monkeypatch):
    """Progress is absolute, but the finished flag and the listening time are
    not - superseding a queued report must not drop them."""
    player = VlcPlayer(on_progress=lambda *args: None)
    player._tracks = [Track(content_url="/a", start_offset=0.0, duration=10.0)]
    player._total_duration = 10.0
    monkeypatch.setattr(player, "_ensure_sync_thread", lambda: None)

    player._listened = 4.0
    player._sync_now(is_finished=True)
    player._listened = 2.0
    player._sync_now()

    pending = player._pending_sync
    assert isinstance(pending, ProgressReport)
    assert pending.is_finished is True
    assert pending.listened == pytest.approx(6.0)


def test_listening_time_counts_only_what_was_played(monkeypatch):
    player, _instance = _prepared_player(monkeypatch)

    player._player.playing = True
    player._last_tick = time.monotonic() - 0.5
    player._count_listening_time()
    assert player._take_listened() == pytest.approx(0.5, abs=0.2)

    # Paused: the clock runs, the listening time does not.
    player._player.playing = False
    player._last_tick = time.monotonic() - 0.5
    player._count_listening_time()
    assert player._take_listened() == 0.0

    # A long gap means the machine slept, not that anyone was listening.
    player._player.playing = True
    player._last_tick = time.monotonic() - 3600
    player._count_listening_time()
    assert player._take_listened() == 0.0


def test_a_downloaded_track_is_never_run_through_the_resolver():
    """A local path handed to the URL resolver would come back as a URL."""
    player = VlcPlayer(url_resolver=lambda url: "https://server" + url)
    track = Track(
        content_url="C:/Audiflix/Book/001.m4b", start_offset=0.0, duration=10.0, local=True
    )
    assert player._resolve(track) == "C:/Audiflix/Book/001.m4b"


def test_local_flag_survives_loading(monkeypatch):
    player, _instance = _prepared_player(monkeypatch)
    player.load(
        [{"content_url": "C:/Book/001.m4b", "duration": 10.0, "local": True}],
        total_duration=10.0,
    )
    assert player._tracks[0].local is True


def test_next_and_previous_track(monkeypatch):
    player, _instance = _prepared_player(monkeypatch)
    player.load(
        [
            {"content_url": "/a", "start_offset": 0.0, "duration": 100.0},
            {"content_url": "/b", "start_offset": 100.0, "duration": 100.0},
        ],
        total_duration=200.0,
    )
    assert player.track_number == 1
    assert player.next_track() == (2, 2)
    assert player.track_number == 2
    assert player.next_track() is None  # already the last file

    player._player.time_ms = 30_000  # 30 s into the second file
    assert player.prev_track() == (2, 2)  # back to the start of this file
    player._player.time_ms = 0
    assert player.prev_track() == (1, 2)


def test_a_broken_stream_is_reopened(monkeypatch):
    """A dropped connection must not cost the listener their place."""
    player, _instance = _prepared_player(monkeypatch)
    notices = []
    errors = []
    player.on_notice = notices.append
    player.on_error = errors.append
    player.load(
        [{"content_url": "/a", "start_offset": 0.0, "duration": 600.0}],
        total_duration=600.0,
    )
    player._player.playing = True
    player._player.time_ms = 120_000
    player._remember_position()
    assert player._last_position == pytest.approx(120.0)

    player._begin_reconnect()
    assert player._retry_at is not None
    assert notices and "again" in notices[0]
    assert errors == []

    # A second failure while an attempt is pending changes nothing.
    player._begin_reconnect()
    assert player._reconnect_attempts == 1

    player._retry_at = time.monotonic() - 1
    player._reconnect_now()
    assert player._retry_at is None
    assert player._index == 0
    assert notices[-1] == "Playback resumed."


def test_reconnecting_gives_up_after_a_few_attempts(monkeypatch):
    player, _instance = _prepared_player(monkeypatch)
    errors = []
    player.on_notice = lambda text: None
    player.on_error = errors.append
    player.load(
        [{"content_url": "/a", "start_offset": 0.0, "duration": 600.0}],
        total_duration=600.0,
    )
    player._last_position = 120.0
    from audiflix.audio.player import MAX_RECONNECT_ATTEMPTS

    for _attempt in range(MAX_RECONNECT_ATTEMPTS):
        player._begin_reconnect()
        player._retry_at = None
    player._begin_reconnect()
    assert errors, "the listener has to be told eventually"
    assert "02:00" in errors[0], "and where playback stopped"


def test_a_downloaded_file_is_not_retried(monkeypatch):
    """Reopening a local file that failed would fail again just as fast."""
    player, _instance = _prepared_player(monkeypatch)
    errors = []
    player.on_error = errors.append
    player.load(
        [{"content_url": "C:/Book/001.m4b", "duration": 10.0, "local": True}],
        total_duration=10.0,
    )
    player._begin_reconnect()
    assert player._retry_at is None
    assert errors


def test_extending_the_sleep_timer_adds_to_what_is_left():
    player = VlcPlayer()
    player.set_sleep_timer(10)
    player.extend_sleep_timer(5)
    assert player.sleep_remaining == pytest.approx(900, abs=10)


def test_extending_without_a_timer_starts_one():
    player = VlcPlayer()
    assert player.sleep_remaining is None
    player.extend_sleep_timer(10)
    assert player.sleep_remaining == pytest.approx(600, abs=10)


def test_chapter_timer_reports_its_remaining_time(monkeypatch):
    player = _player_with_chapters(monkeypatch)
    player._player.time_ms = 30_000
    player.set_sleep_timer(None, until_chapter=True)
    # 30 s of audio to the end of the chapter, at double speed that is 15 s.
    assert player.sleep_remaining == pytest.approx(30.0, abs=1)
    player.set_rate(2.0)
    assert player.sleep_remaining == pytest.approx(15.0, abs=1)


def test_the_sleep_timer_fades_the_volume_out(monkeypatch):
    player, _instance = _prepared_player(monkeypatch)
    player.fade_seconds = 20.0
    player.set_volume(100)
    player.set_sleep_timer(10)

    player._update_fade()  # far from the end: nothing to do
    assert player._volume_before_fade is None

    player._sleep_deadline = time.monotonic() + 5  # 5 s left of 20
    player._update_fade()
    assert player._volume_before_fade == 100
    assert player._player.volume_set == 25

    # Firing the timer restores the level the user chose.
    player._fire_sleep()
    assert player.volume == 100
    assert player._player.volume_set == 100


def test_turning_the_volume_up_during_the_fade_is_respected(monkeypatch):
    player, _instance = _prepared_player(monkeypatch)
    player.fade_seconds = 20.0
    player.set_volume(50)
    player.set_sleep_timer(10)
    player._sleep_deadline = time.monotonic() + 10
    player._update_fade()
    assert player._volume_before_fade == 50

    player.set_volume(80)
    assert player._volume_before_fade == 80
    player._end_fade()
    assert player.volume == 80


def test_a_new_chapter_is_reported_once(monkeypatch):
    player = _player_with_chapters(monkeypatch)
    seen = []
    player.on_chapter_change = seen.append
    player._player.time_ms = 10_000
    player._last_chapter_index = player.chapter_index_at(10.0)

    player._announce_new_chapter()
    assert seen == []

    player._player.time_ms = 70_000  # now in chapter two
    player._announce_new_chapter()
    player._announce_new_chapter()
    assert seen == [1], "the chapter is announced when it starts, not every tick"


def test_seeking_does_not_trigger_the_chapter_announcement(monkeypatch):
    """The action that jumped there announces the chapter itself."""
    player = _player_with_chapters(monkeypatch)
    seen = []
    player.on_chapter_change = seen.append
    player.seek(70.0)
    player._player.time_ms = 70_000
    player._announce_new_chapter()
    assert seen == []
