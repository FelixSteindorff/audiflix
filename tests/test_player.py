"""Tests for player behaviour that does not require a running VLC."""

from audiflix.audio.player import Track, VlcPlayer


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
    assert remaining is not None and 590 < remaining <= 600
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
        pass

    def get_length(self):
        return 1000

    def is_playing(self):
        return False

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
    monkeypatch.setattr(player, "_seek_when_ready", lambda offset: None)
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
