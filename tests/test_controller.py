"""Tests for the controller logic that does not need a window.

:class:`AppContext` owns the rules the UI only triggers: which speed a title
starts at, what a list row says, and what happens when the server cannot be
reached. Those are tested here with a stub client and settings that are never
written to disk.
"""

from pathlib import Path

import pytest

wx = pytest.importorskip("wx")

import audiflix.helpers.status as status_module
from audiflix.api.client import ApiError
from audiflix.api.models import LibraryItem
from audiflix.config import Settings
from audiflix.helpers import downloads
from audiflix.ui.controller import AppContext


class _StubClient:
    server_version = ""

    def __init__(self, session=None, error=None):
        self.user: dict = {}
        self._session = session
        self._error = error
        self.play_calls: list[tuple] = []
        self.progress_calls: list[tuple] = []

    def authed_url(self, url):
        return f"https://server{url}"

    def play_item(self, item_id, episode_id=None):
        self.play_calls.append((item_id, episode_id))
        if self._error is not None:
            raise self._error
        return self._session

    def sync_progress(self, item_id, position, duration, is_finished=False, episode_id=None):
        self.progress_calls.append((item_id, position, duration, is_finished))


class _StubPlayer:
    """Stands in for VlcPlayer so nothing tries to load libVLC."""

    def __init__(self):
        self.rate = 1.0
        self.item_title = ""
        self.loaded = None
        self.played = False

    def load(self, tracks, total, start_time=0.0, item_id=None, item_title="", chapters=None):
        self.loaded = {
            "tracks": tracks, "total": total, "start_time": start_time,
            "item_id": item_id, "chapters": chapters,
        }
        self.item_title = item_title

    def play(self):
        self.played = True

    def set_rate(self, rate):
        self.rate = rate
        return rate

    def change_rate(self, delta):
        return self.set_rate(round(self.rate + delta, 2))


def _settings(tmp_path, **overrides):
    settings = Settings(dict(overrides))
    # Never touch the real config directory in a test.
    settings.save = lambda: True
    return settings


def _book(item_id="li_1", title="A Book", duration=7200.0):
    return LibraryItem({
        "id": item_id,
        "media": {"metadata": {"title": title}, "duration": duration},
    })


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(status_module, "config_dir", lambda: tmp_path)
    context = AppContext(_StubClient(), _settings(tmp_path))
    context.player = _StubPlayer()
    context.notify = lambda text, interrupt=True, speak=True: context.messages.append(text)
    context.messages = []
    return context


# --- speed ------------------------------------------------------------------

def test_a_title_without_its_own_speed_uses_the_default(ctx):
    ctx.settings["default_speed"] = 1.2
    assert ctx.speed_for(_book()) == 1.2
    assert ctx.speed_for(None) == 1.2


def test_changing_the_speed_saves_it_for_the_title(ctx):
    item = _book()
    ctx.current_item = item
    ctx.speed_up()
    assert ctx.player.rate == pytest.approx(1.1)
    assert ctx.settings["book_speeds"] == {"li_1": 1.1}
    assert ctx.speed_for(item) == 1.1
    assert ctx.has_own_speed(item) is True


def test_a_speed_equal_to_the_default_is_not_stored(ctx):
    """Otherwise every title would collect an entry that says nothing."""
    item = _book()
    ctx.current_item = item
    ctx.speed_up()
    ctx.speed_down()
    assert ctx.player.rate == pytest.approx(1.0)
    assert ctx.settings["book_speeds"] == {}


def test_resetting_the_speed_forgets_the_title(ctx):
    item = _book()
    ctx.current_item = item
    ctx.set_speed(1.5)
    assert ctx.has_own_speed(item) is True
    ctx.speed_reset()
    assert ctx.player.rate == 1.0
    assert ctx.has_own_speed(item) is False


def test_speeds_are_kept_apart_per_title(ctx):
    fast, slow = _book("li_fast"), _book("li_slow")
    ctx.current_item = fast
    ctx.set_speed(1.8)
    ctx.current_item = slow
    ctx.set_speed(0.9)
    assert ctx.speed_for(fast) == 1.8
    assert ctx.speed_for(slow) == 0.9


def test_the_per_title_speed_can_be_turned_off(ctx):
    ctx.settings["remember_speed_per_title"] = False
    ctx.current_item = _book()
    ctx.set_speed(1.5)
    assert ctx.settings["book_speeds"] == {}
    assert ctx.speed_for(ctx.current_item) == 1.0


def test_an_unusable_stored_speed_is_ignored(ctx):
    ctx.settings["book_speeds"] = {"li_1": "fast"}
    assert ctx.speed_for(_book()) == 1.0


def test_playback_starts_at_the_speed_saved_for_the_title(ctx):
    item = _book()
    ctx.settings["book_speeds"] = {"li_1": 1.4}
    ctx._start_playback(item, None, [{"duration": 10.0}], 10.0, 0.0, [], "A Book")
    assert ctx.player.rate == 1.4
    assert ctx.player.played is True


# --- list columns -----------------------------------------------------------

def test_item_progress_states_what_is_left(ctx):
    ctx.progress.update({"mediaProgress": [
        {"libraryItemId": "li_1", "progress": 0.5, "currentTime": 3600.0},
    ]})
    text = ctx.item_progress(_book())
    assert "50% played" in text
    assert "1 hour" in text


def test_item_status_tells_offline_titles_apart(ctx, tmp_path):
    item = _book()
    assert ctx.item_status(item) == "Not downloaded"

    folder = tmp_path / "book"
    folder.mkdir()
    (folder / "001.mp3").write_bytes(b"a")
    downloads.write_manifest(
        folder, item_id="li_1", title="A Book", duration=10.0,
        tracks=[{"file": "001.mp3", "ino": "1", "start_offset": 0.0, "duration": 10.0}],
    )
    ctx.registry.mark_folder("li_1", str(folder))
    assert ctx.item_status(item) == "Available offline"


# --- offline playback -------------------------------------------------------

def _downloaded(ctx, tmp_path, item_id="li_1"):
    folder = tmp_path / "download"
    folder.mkdir()
    (folder / "001.mp3").write_bytes(b"audio")
    downloads.write_manifest(
        folder, item_id=item_id, title="A Book", duration=600.0,
        tracks=[{"file": "001.mp3", "ino": "1", "start_offset": 0.0, "duration": 600.0}],
        chapters=[{"start": 0.0, "end": 600.0, "title": "One"}],
    )
    ctx.registry.mark_folder(item_id, str(folder))
    return folder


def test_an_unreachable_server_plays_the_download(ctx, tmp_path):
    folder = _downloaded(ctx, tmp_path)
    downloads.update_position(folder, 150.0, synced=False)
    ctx.client = _StubClient(error=ApiError("no network"))
    ctx.player.url_resolver = None

    item = _book()
    tracks = ctx.registry.local_tracks(item.id)
    ctx._play_offline(item, tracks)

    loaded = ctx.player.loaded
    assert Path(loaded["tracks"][0]["url"]).exists()
    assert loaded["start_time"] == 150.0
    assert loaded["chapters"][0]["title"] == "One"
    assert ctx.current_session_id is None
    assert any("offline" in message.lower() for message in ctx.messages)


def test_a_failed_sync_keeps_the_position_for_later(ctx, tmp_path):
    folder = _downloaded(ctx, tmp_path)
    ctx.current_item = _book()

    class _Failing(_StubClient):
        def sync_progress(self, *args, **kwargs):
            raise ApiError("no network")

    ctx.client = _Failing()
    ctx._on_player_progress(300.0, 600.0, False, 15.0)
    assert downloads.pending_position(folder) == 300.0

    # Once the server answers again the position is no longer owed.
    ctx.client = _StubClient()
    ctx._on_player_progress(360.0, 600.0, False, 15.0)
    assert downloads.pending_position(folder) is None


def test_pending_offline_progress_is_pushed(ctx, tmp_path):
    _downloaded(ctx, tmp_path)
    ctx.registry.record_offline_position("li_1", 420.0)
    client = _StubClient()
    ctx.client = client

    pending = ctx.registry.pending_positions()
    assert pending == {"li_1": 420.0}
    for item_id, position in pending.items():
        manifest = ctx.registry.manifest(item_id)
        client.sync_progress(item_id, position, manifest["duration"])
        ctx.registry.clear_offline_position(item_id, position)

    assert client.progress_calls == [("li_1", 420.0, 600.0, False)]
    assert ctx.registry.pending_positions() == {}


def test_a_downloaded_title_is_played_from_disk_while_online(ctx, tmp_path):
    """The server still supplies the resume position; the audio comes from disk."""
    _downloaded(ctx, tmp_path)
    ctx.client = _StubClient(session={
        "id": "sess_1",
        "duration": 600.0,
        "currentTime": 90.0,
        "chapters": [{"start": 0.0, "end": 600.0, "title": "One"}],
        "audioTracks": [
            {"contentUrl": "/stream/1", "startOffset": 0.0, "duration": 600.0}
        ],
    })
    calls = []
    ctx.run_async = lambda func, on_done=None, on_error=None, description="": (
        calls.append(description), on_done(func()) if on_done else None
    )

    ctx.play_item(_book())
    loaded = ctx.player.loaded
    assert loaded["tracks"][0]["local"] is True
    assert "stream" not in loaded["tracks"][0]["url"]
    assert loaded["start_time"] == 90.0  # the server knows better than the file
    assert ctx.current_session_id == "sess_1"


def test_a_sign_in_problem_is_not_hidden_behind_the_download(ctx, tmp_path):
    """Offline playback covers an unreachable server, not a rejected login."""
    _downloaded(ctx, tmp_path)
    ctx.client = _StubClient(error=ApiError("no", status=401))
    raised: list[ApiError] = []

    def run_async(func, on_done=None, on_error=None, description=""):
        try:
            result = func()
        except ApiError as exc:
            raised.append(exc)  # this is what run_async reports to the user
            return
        if on_done:
            on_done(result)

    ctx.run_async = run_async
    ctx.play_item(_book())
    assert [exc.status for exc in raised] == [401]
    assert ctx.player.loaded is None
