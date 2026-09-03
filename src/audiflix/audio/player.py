"""VLC-based audiobook player with a position spanning chapters and tracks.

In Audiobookshelf an audiobook often consists of several audio files
(``audioTracks``). This class presents them as *one* continuous timeline:
``position`` and ``seek`` work with the global number of seconds across all
tracks.

A background thread takes care of:

* switching to the next track when one ends,
* periodic progress synchronisation (``on_progress`` callback),
* the sleep timer.

All callbacks run on the worker thread; the UI must marshal them onto the main
thread with ``wx.CallAfter``.

Track URLs are resolved lazily through ``url_resolver`` right before a track is
handed to VLC. Audiobookshelf access tokens are short-lived, so a URL built an
hour ago would no longer be accepted - resolving late means every newly opened
track gets a currently valid token.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from audiflix import vlc_runtime
from audiflix.i18n import _
from audiflix.logging_setup import get_logger
from audiflix.vlc_runtime import VlcRuntimeError

log = get_logger(__name__)

POLL_INTERVAL = 0.4  # seconds
#: Stop logging repeated identical tick failures after this many in a row.
MAX_CONSECUTIVE_TICK_ERRORS = 5


class PlayerError(RuntimeError):
    """Audio backend unavailable or playback failed."""


def _broken_engine_message() -> str:
    """Shown when libVLC is present but refuses to start."""
    if vlc_runtime.is_frozen():
        return _("The bundled audio engine could not be loaded. Please reinstall Audiflix.")
    return _("The audio engine could not be started. Please reinstall the VLC media player.")


@dataclass
class Track:
    """One audio file of an item.

    ``content_url`` is the URL as delivered by the server (usually relative);
    ``url`` is the ready-to-play URL and is refreshed on every load.
    """

    content_url: str
    start_offset: float
    duration: float
    url: str = field(default="")

    def __post_init__(self) -> None:
        if not self.url:
            self.url = self.content_url


class VlcPlayer:
    def __init__(
        self,
        on_progress: Callable[[float, float, bool], None] | None = None,
        on_track_change: Callable[[int], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        on_sleep: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        url_resolver: Callable[[str], str] | None = None,
        default_rate: float = 1.0,
        default_volume: int = 100,
        sync_interval: float = 15.0,
    ):
        self.on_progress = on_progress
        self.on_track_change = on_track_change
        self.on_finished = on_finished
        self.on_sleep = on_sleep
        self.on_error = on_error
        self.url_resolver = url_resolver
        self.sync_interval = sync_interval
        self.rate = default_rate
        self.volume = int(default_volume)

        self._vlc = None
        self._instance = None
        self._player = None

        self._tracks: list[Track] = []
        self._chapters: list[dict] = []  # each {start, end, title}, global seconds
        self._index = 0
        self._total_duration = 0.0
        self.item_id: str | None = None
        self.item_title: str = ""

        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._last_sync = 0.0
        self._sleep_deadline: float | None = None
        self._sleep_until_chapter = False
        self._tick_errors = 0

    # --- VLC initialisation ------------------------------------------------
    def _ensure_vlc(self):
        """Load the bundled libVLC and create the media player.

        The runtime is resolved by :mod:`audiflix.vlc_runtime`, which points
        python-vlc at the copy of VLC shipped with Audiflix before importing
        it. A packaged build never falls back to a system installation.
        """
        if self._player is not None:
            return
        try:
            vlc = vlc_runtime.load_vlc()
        except VlcRuntimeError as exc:  # pragma: no cover - depends on the install
            raise PlayerError(str(exc)) from exc

        runtime = vlc_runtime.configure()
        # libVLC 3 removed the --plugin-path option; the module directory is
        # controlled through VLC_PLUGIN_PATH, which vlc_runtime.configure() set.
        args = ["--no-video", "--quiet"]
        try:
            self._instance = vlc.Instance(*args)
            if self._instance is None:
                raise PlayerError(_broken_engine_message())
            self._player = self._instance.media_player_new()
            if self._player is None:
                raise PlayerError(_broken_engine_message())
        except PlayerError:
            raise
        except Exception as exc:  # pragma: no cover - libvlc runtime failures
            log.exception("Could not create a VLC instance")
            raise PlayerError(
                _("The audio engine could not be started: %s") % exc
            ) from exc
        self._vlc = vlc
        log.info("Audio engine ready (%s)", runtime.describe())

    # --- Loading / playback ------------------------------------------------
    def load(
        self,
        tracks: list[dict],
        total_duration: float,
        start_time: float = 0.0,
        item_id: str | None = None,
        item_title: str = "",
        chapters: list[dict] | None = None,
    ) -> None:
        """Load an item's tracks and jump to ``start_time`` (global seconds).

        ``chapters`` is an optional list of dicts with ``start``/``end``/
        ``title`` (global seconds) used for chapter navigation.
        """
        self._ensure_vlc()
        with self._lock:
            self.stop(sync=False)
            self._tracks = [
                Track(
                    content_url=t.get("content_url") or t.get("url", ""),
                    start_offset=float(t.get("start_offset", 0.0)),
                    duration=float(t.get("duration", 0.0)),
                    url=t.get("url", ""),
                )
                for t in tracks
            ]
            self._chapters = self._normalize_chapters(chapters)
            self._total_duration = total_duration or sum(t.duration for t in self._tracks)
            self.item_id = item_id
            self.item_title = item_title
            # -1 forces the following seek() to load a track: the media object
            # of the previous title is still attached to the VLC player, and
            # keeping index 0 would make seek() reuse it.
            self._index = -1
            self._stop_flag.clear()
            self._tick_errors = 0
            self._last_sync = time.monotonic()
        log.info(
            "Loaded '%s' with %d track(s), %.0f s total, starting at %.0f s",
            item_title, len(self._tracks), self._total_duration, start_time,
        )
        self.seek(start_time, autoplay=False)
        self._start_thread()

    def _resolve(self, track: Track) -> str:
        """Return a currently valid playback URL for ``track``."""
        if self.url_resolver and track.content_url:
            try:
                resolved = self.url_resolver(track.content_url)
                if resolved:
                    track.url = resolved
            except Exception:
                # A failing resolver must not kill playback - keep the old URL.
                log.exception("Could not refresh the playback URL, using the previous one")
        return track.url

    def _load_index(self, index: int, offset_in_track: float = 0.0, autoplay: bool = True) -> None:
        track = self._tracks[index]
        url = self._resolve(track)
        if not url:
            raise PlayerError(_("This title has no playable audio files."))
        media = self._instance.media_new(url)
        self._player.set_media(media)
        self._index = index
        self._player.play()
        # Apply rate, volume and position as soon as VLC is ready.
        self._apply_rate()
        self._apply_volume()
        if offset_in_track > 0:
            self._seek_when_ready(offset_in_track)
        if not autoplay:
            # Play briefly to establish the position, then pause.
            self._player.set_pause(1)
        if self.on_track_change:
            self.on_track_change(index)

    def _seek_when_ready(self, offset_in_track: float) -> None:
        def worker():
            for _attempt in range(50):  # wait up to ~5 s for the length
                if self._player is None:
                    return
                length = self._player.get_length()
                if length and length > 0:
                    break
                time.sleep(0.1)
            try:
                if self._player is not None:
                    self._player.set_time(int(offset_in_track * 1000))
            except Exception:
                log.exception("Could not seek to %.1f s inside the track", offset_in_track)

        threading.Thread(target=worker, name="audiflix-seek", daemon=True).start()

    def play(self) -> None:
        if not self._tracks:
            return
        self._ensure_vlc()
        if self._player.get_media() is None:
            self._load_index(self._index)
        else:
            self._player.play()
            self._apply_rate()
            self._apply_volume()
        self._start_thread()

    def pause(self) -> None:
        if self._player is not None:
            self._player.set_pause(1)
        self._sync_now()

    def toggle(self) -> bool:
        """Toggle play/pause. Returns True when playback is now running."""
        if self.is_playing:
            self.pause()
            return False
        self.play()
        return True

    def stop(self, sync: bool = True) -> None:
        if sync:
            self._sync_now()
        self._stop_flag.set()
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                log.exception("VLC refused to stop playback")

    # --- Navigation --------------------------------------------------------
    def skip(self, seconds: float) -> None:
        self.seek(self.position + seconds)

    def seek(self, global_time: float, autoplay: bool = True) -> None:
        if not self._tracks:
            return
        global_time = max(0.0, min(global_time, self._total_duration or global_time))
        index, offset = self._locate(global_time)
        with self._lock:
            if index != self._index or self._player.get_media() is None:
                self._load_index(index, offset, autoplay=autoplay)
            else:
                self._player.set_time(int(offset * 1000))
                if autoplay:
                    self._player.play()
                    self._apply_rate()

    def _locate(self, global_time: float) -> tuple[int, float]:
        for i, track in enumerate(self._tracks):
            end = track.start_offset + track.duration
            if global_time < end or i == len(self._tracks) - 1:
                return i, max(0.0, global_time - track.start_offset)
        return 0, 0.0

    def next_track(self) -> None:
        if self._index + 1 < len(self._tracks):
            self._load_index(self._index + 1, 0.0)

    # --- Chapters ----------------------------------------------------------
    @staticmethod
    def _normalize_chapters(chapters: list[dict] | None) -> list[dict]:
        """Normalise and sort chapters by start time."""
        return sorted(
            (
                {
                    "start": float(c.get("start") or 0.0),
                    "end": float(c.get("end") or 0.0),
                    "title": c.get("title") or "",
                }
                for c in (chapters or [])
                if isinstance(c, dict)
            ),
            key=lambda c: c["start"],
        )

    @property
    def has_chapters(self) -> bool:
        return len(self._chapters) > 1

    @property
    def chapters(self) -> list[dict]:
        return list(self._chapters)

    def chapter_index_at(self, global_time: float) -> int:
        """Index of the chapter containing ``global_time`` (-1 when there are none)."""
        if not self._chapters:
            return -1
        idx = -1
        for i, chapter in enumerate(self._chapters):
            if global_time >= chapter["start"]:
                idx = i
            else:
                break
        return idx if idx >= 0 else 0

    @property
    def current_chapter_index(self) -> int:
        return self.chapter_index_at(self.position)

    @property
    def current_chapter(self) -> dict | None:
        idx = self.current_chapter_index
        return self._chapters[idx] if idx >= 0 else None

    def seek_chapter(self, index: int) -> dict | None:
        """Jump to the start of chapter ``index`` and return it."""
        if not (0 <= index < len(self._chapters)):
            return None
        chapter = self._chapters[index]
        self.seek(chapter["start"], autoplay=self.is_playing)
        return chapter

    def next_chapter(self) -> dict | None:
        return self.seek_chapter(self.current_chapter_index + 1)

    def prev_chapter(self) -> dict | None:
        """Jump to the previous chapter - or to the start of the current one when
        more than three seconds have been played (the usual audiobook behaviour)."""
        idx = self.current_chapter_index
        if idx < 0:
            return None
        current = self._chapters[idx]
        if self.position - current["start"] > 3.0:
            return self.seek_chapter(idx)
        return self.seek_chapter(idx - 1) or self.seek_chapter(idx)

    # --- Speed -------------------------------------------------------------
    def set_rate(self, rate: float) -> float:
        self.rate = max(0.5, min(rate, 3.5))
        self._apply_rate()
        return self.rate

    def change_rate(self, delta: float) -> float:
        return self.set_rate(round(self.rate + delta, 2))

    def _apply_rate(self) -> None:
        if self._player is not None:
            try:
                self._player.set_rate(self.rate)
            except Exception:
                log.exception("Could not set the playback rate to %.2f", self.rate)

    # --- Volume ------------------------------------------------------------
    def set_volume(self, volume: int) -> int:
        self.volume = max(0, min(int(volume), 100))
        self._apply_volume()
        return self.volume

    def change_volume(self, delta: int) -> int:
        return self.set_volume(self.volume + delta)

    def _apply_volume(self) -> None:
        if self._player is not None:
            try:
                self._player.audio_set_volume(self.volume)
            except Exception:
                log.exception("Could not set the volume to %d", self.volume)

    # --- State -------------------------------------------------------------
    @property
    def is_playing(self) -> bool:
        return bool(self._player is not None and self._player.is_playing())

    @property
    def position(self) -> float:
        """Global position in seconds across all tracks."""
        if not self._tracks or self._player is None or not 0 <= self._index < len(self._tracks):
            return 0.0
        track = self._tracks[self._index]
        current = self._player.get_time()
        local = (current / 1000.0) if current and current > 0 else 0.0
        return track.start_offset + local

    @property
    def duration(self) -> float:
        return self._total_duration

    @property
    def has_media(self) -> bool:
        return bool(self._tracks)

    # --- Sleep timer -------------------------------------------------------
    def set_sleep_timer(self, minutes: float | None, until_chapter: bool = False) -> None:
        with self._lock:
            if minutes is None and not until_chapter:
                self._sleep_deadline = None
                self._sleep_until_chapter = False
            elif until_chapter:
                self._sleep_until_chapter = True
                self._sleep_deadline = None
            else:
                self._sleep_deadline = time.monotonic() + minutes * 60
                self._sleep_until_chapter = False

    def cancel_sleep_timer(self) -> None:
        self.set_sleep_timer(None)

    @property
    def sleep_remaining(self) -> float | None:
        if self._sleep_deadline is None:
            return None
        return max(0.0, self._sleep_deadline - time.monotonic())

    # --- Background thread -------------------------------------------------
    def _start_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run, name="audiflix-player", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_flag.wait(POLL_INTERVAL):
            try:
                self._tick()
                self._tick_errors = 0
            except Exception:
                self._tick_errors += 1
                if self._tick_errors <= MAX_CONSECUTIVE_TICK_ERRORS:
                    log.exception("Player background tick failed (%d)", self._tick_errors)
                if self._tick_errors == MAX_CONSECUTIVE_TICK_ERRORS:
                    log.error("Suppressing further identical player tick errors")
                    if self.on_error:
                        self.on_error(_("Playback reported repeated errors. See the log file."))

    def _tick(self) -> None:
        if self._player is None:
            return
        state = self._player.get_state()
        ended = self._vlc is not None and state == self._vlc.State.Ended
        failed = self._vlc is not None and state == self._vlc.State.Error

        if failed:
            log.error("VLC reported a playback error for track %d", self._index)
            self._stop_flag.set()
            if self.on_error:
                self.on_error(_("Playback failed. The stream may have expired - please try again."))
            return

        # End of track -> next track or end of book
        if ended:
            if self._index + 1 < len(self._tracks):
                if self._sleep_until_chapter:
                    self._sleep_until_chapter = False
                    self._fire_sleep()
                    return
                log.debug("Track %d ended, continuing with the next one", self._index)
                self._load_index(self._index + 1, 0.0)
            else:
                self._sync_now(is_finished=True)
                if self.on_finished:
                    self.on_finished()
                self._stop_flag.set()
            return

        # Sleep timer (time based)
        if self._sleep_deadline is not None and time.monotonic() >= self._sleep_deadline:
            self._sleep_deadline = None
            self._fire_sleep()
            return

        # Periodic progress synchronisation
        now = time.monotonic()
        if now - self._last_sync >= self.sync_interval:
            self._last_sync = now
            self._sync_now()

    def _fire_sleep(self) -> None:
        self.pause()
        if self.on_sleep:
            self.on_sleep()

    def _sync_now(self, is_finished: bool = False) -> None:
        if self.on_progress and self._tracks:
            try:
                self.on_progress(self.position, self.duration, is_finished)
            except Exception:
                log.exception("Progress callback failed")

    def shutdown(self) -> None:
        self.stop(sync=True)
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        if self._player is not None:
            try:
                self._player.release()
            except Exception:
                log.exception("Could not release the VLC player")
        self._player = None
        self._instance = None
