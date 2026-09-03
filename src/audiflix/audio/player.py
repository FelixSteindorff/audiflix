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

``on_progress`` talks to the server and can therefore block for as long as the
request timeout. It runs on its own thread (see :meth:`VlcPlayer._sync_now`) so
that neither the UI thread - which reports progress on pause and on stop - nor
the tick loop, which has a sleep timer and track changes to attend to, ever
waits for the network.

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
from audiflix.helpers.formatting import format_clock
from audiflix.i18n import _
from audiflix.logging_setup import get_logger
from audiflix.vlc_runtime import VlcRuntimeError

log = get_logger(__name__)

POLL_INTERVAL = 0.4  # seconds
#: Stop logging repeated identical tick failures after this many in a row.
MAX_CONSECUTIVE_TICK_ERRORS = 5
#: How long to wait for the queued progress report when shutting down.
SYNC_FLUSH_TIMEOUT = 3.0
#: Ignore gaps longer than this when counting listening time (suspend, freeze).
MAX_LISTENED_STEP = POLL_INTERVAL * 5
#: How often a broken stream is reopened before giving up.
MAX_RECONNECT_ATTEMPTS = 3
#: Seconds to wait before each attempt; the last value is reused afterwards.
RECONNECT_DELAYS = (2.0, 5.0, 10.0)


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
    ``local`` marks a downloaded file: it is played from disk and its path must
    never be run through the URL resolver.
    """

    content_url: str
    start_offset: float
    duration: float
    url: str = field(default="")
    local: bool = False

    def __post_init__(self) -> None:
        if not self.url:
            self.url = self.content_url


@dataclass
class ProgressReport:
    """One queued progress report for the ``on_progress`` callback.

    ``listened`` is the wall-clock time actually played since the previous
    report - not the difference in position, which grows faster than real time
    at a playback rate above 1.0.
    """

    position: float
    duration: float
    is_finished: bool = False
    listened: float = 0.0


class VlcPlayer:
    def __init__(
        self,
        on_progress: Callable[[float, float, bool, float], None] | None = None,
        on_track_change: Callable[[int], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        on_sleep: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_notice: Callable[[str], None] | None = None,
        on_chapter_change: Callable[[int], None] | None = None,
        url_resolver: Callable[[str], str] | None = None,
        default_rate: float = 1.0,
        default_volume: int = 100,
        sync_interval: float = 15.0,
        fade_seconds: float = 0.0,
    ):
        self.on_progress = on_progress
        self.on_track_change = on_track_change
        self.on_finished = on_finished
        self.on_sleep = on_sleep
        self.on_error = on_error
        #: Non-fatal messages ("reconnecting..."), which the UI only announces.
        self.on_notice = on_notice
        self.on_chapter_change = on_chapter_change
        self.url_resolver = url_resolver
        self.sync_interval = sync_interval
        self.fade_seconds = float(fade_seconds)
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
        #: Global second at which the "until the end of the chapter" timer fires.
        self._sleep_chapter_end: float | None = None
        self._tick_errors = 0
        #: Bumped on every track load so a pending seek can tell whether the
        #: track it was started for is still the one that is playing.
        self._load_generation = 0
        self._last_tick = 0.0
        self._listened = 0.0
        #: Last position VLC reported while it was still playing. A broken
        #: stream reports nothing, so this is where a reconnect resumes.
        self._last_position = 0.0
        self._reconnect_attempts = 0
        self._retry_at: float | None = None
        self._last_chapter_index = -1
        #: Volume before the sleep timer started fading it out.
        self._volume_before_fade: int | None = None

        # Progress reports are sent from their own thread, see _sync_now().
        self._sync_lock = threading.Lock()
        self._pending_sync: ProgressReport | None = None
        self._sync_event = threading.Event()
        self._sync_stop = threading.Event()
        self._sync_thread: threading.Thread | None = None

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
                    local=bool(t.get("local")),
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
            self._reconnect_attempts = 0
            self._retry_at = None
            self._last_position = start_time
            self._last_chapter_index = self.chapter_index_at(start_time)
            self._last_sync = time.monotonic()
        log.info(
            "Loaded '%s' with %d track(s), %.0f s total, starting at %.0f s",
            item_title, len(self._tracks), self._total_duration, start_time,
        )
        self.seek(start_time, autoplay=False)
        self._start_thread()

    def _resolve(self, track: Track) -> str:
        """Return a currently valid playback URL for ``track``.

        A downloaded track is a path on disk, so there is nothing to resolve -
        and running it through the resolver would turn it into a URL.
        """
        if track.local:
            return track.url
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
        self._load_generation += 1
        generation = self._load_generation
        self._player.play()
        # Apply rate, volume and position as soon as VLC is ready.
        self._apply_rate()
        self._apply_volume()
        if offset_in_track > 0:
            self._seek_when_ready(offset_in_track, generation)
        if not autoplay:
            # Play briefly to establish the position, then pause.
            self._player.set_pause(1)
        if self.on_track_change:
            self.on_track_change(index)

    def _seek_when_ready(self, offset_in_track: float, generation: int) -> threading.Thread:
        """Seek inside a track once VLC knows its length.

        VLC reports a length only after it has opened the stream, so the seek
        has to wait. ``generation`` is the load it belongs to: while we wait the
        user can skip on or a track can end, and applying the old offset to the
        track that is playing now would jump to the wrong place.

        Returns the thread doing the waiting, which the tests join.
        """

        def worker():
            for _attempt in range(50):  # wait up to ~5 s for the length
                if self._player is None or self._load_generation != generation:
                    return
                length = self._player.get_length()
                if length and length > 0:
                    break
                time.sleep(0.1)
            try:
                with self._lock:
                    if self._player is None or self._load_generation != generation:
                        log.debug("Dropping a stale seek to %.1f s", offset_in_track)
                        return
                    self._player.set_time(int(offset_in_track * 1000))
            except Exception:
                log.exception("Could not seek to %.1f s inside the track", offset_in_track)

        thread = threading.Thread(target=worker, name="audiflix-seek", daemon=True)
        thread.start()
        return thread

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
            self._last_position = global_time
            # A deliberate jump is announced by the action that caused it, so
            # the automatic "new chapter" announcement must not fire as well.
            self._last_chapter_index = self.chapter_index_at(global_time)
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

    def next_track(self) -> tuple[int, int] | None:
        """Jump to the next audio file. Returns ``(number, total)`` or ``None``.

        Books without chapter marks are navigated by file, which is all the
        structure they have.
        """
        return self._goto_track(self._index + 1)

    def prev_track(self) -> tuple[int, int] | None:
        """Jump to the previous file - or to the start of the current one when
        more than three seconds of it have been played."""
        if self._index < 0 or not self._tracks:
            return None
        track = self._tracks[self._index]
        if self.position - track.start_offset > 3.0:
            return self._goto_track(self._index)
        return self._goto_track(self._index - 1) or self._goto_track(self._index)

    def _goto_track(self, index: int) -> tuple[int, int] | None:
        if not (0 <= index < len(self._tracks)):
            return None
        with self._lock:
            playing = self.is_playing
            self._load_index(index, 0.0, autoplay=playing)
            self._last_position = self._tracks[index].start_offset
            self._last_chapter_index = self.chapter_index_at(self._last_position)
        return index + 1, len(self._tracks)

    @property
    def track_count(self) -> int:
        return len(self._tracks)

    @property
    def track_number(self) -> int:
        """Number of the file that is playing, counting from 1 (0 = none)."""
        return self._index + 1 if 0 <= self._index < len(self._tracks) else 0

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
        if self._volume_before_fade is not None:
            # Turning the volume up during the fade means "this loud, from
            # here" - the fade continues from the new level.
            self._volume_before_fade = self.volume
        self._apply_volume()
        return self.volume

    def change_volume(self, delta: int) -> int:
        return self.set_volume(self.volume + delta)

    def _apply_volume(self) -> None:
        self._set_engine_volume(self.volume)

    def _set_engine_volume(self, volume: int) -> None:
        """Set the engine volume without changing the level the user chose.

        The sleep timer fades the sound out with this; the volume the user set
        is what playback returns to afterwards.
        """
        if self._player is not None:
            try:
                self._player.audio_set_volume(max(0, min(int(volume), 100)))
            except Exception:
                log.exception("Could not set the volume to %d", volume)

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
            self._end_fade()
            if minutes is None and not until_chapter:
                self._sleep_deadline = None
                self._sleep_until_chapter = False
                self._sleep_chapter_end = None
            elif until_chapter:
                self._sleep_until_chapter = True
                self._sleep_deadline = None
                self._sleep_chapter_end = self._current_chapter_end()
            else:
                self._sleep_deadline = time.monotonic() + minutes * 60
                self._sleep_until_chapter = False
                self._sleep_chapter_end = None

    def _current_chapter_end(self) -> float | None:
        """End of the chapter that is playing, in global seconds.

        ``None`` when there are no chapters - a book split into files without
        chapter marks, for example. The sleep timer then falls back to the end
        of the current track, which for such a book is the same thing.
        """
        index = self.current_chapter_index
        if index < 0:
            return None
        chapter = self._chapters[index]
        end = float(chapter.get("end") or 0.0)
        if end > chapter["start"]:
            return end
        # Not every server fills in "end"; the next chapter starts where this
        # one stops, and the last chapter ends with the book.
        if index + 1 < len(self._chapters):
            return self._chapters[index + 1]["start"]
        return self._total_duration or None

    def cancel_sleep_timer(self) -> None:
        self.set_sleep_timer(None)

    def extend_sleep_timer(self, minutes: float) -> float | None:
        """Add ``minutes`` to the running timer and return the new remaining time.

        With no timer running this simply starts one. A chapter timer becomes a
        timed one, because "the end of the chapter plus ten minutes" is a point
        in time, not a chapter mark.
        """
        with self._lock:
            remaining = self.sleep_remaining or 0.0
            self._end_fade()
            self._sleep_until_chapter = False
            self._sleep_chapter_end = None
            self._sleep_deadline = time.monotonic() + remaining + minutes * 60
        return self.sleep_remaining

    @property
    def sleep_remaining(self) -> float | None:
        """Seconds of real time left on the sleep timer, whichever kind it is."""
        if self._sleep_deadline is not None:
            return max(0.0, self._sleep_deadline - time.monotonic())
        if self._sleep_until_chapter and self._sleep_chapter_end is not None:
            # The position advances by "rate" seconds per second of real time.
            audio_left = max(0.0, self._sleep_chapter_end - self.position)
            return audio_left / (self.rate or 1.0)
        return None

    @property
    def sleep_active(self) -> bool:
        return self._sleep_deadline is not None or self._sleep_until_chapter

    # --- Fading out at the end of the sleep timer ---------------------------
    def _update_fade(self) -> None:
        """Lower the volume over the last seconds before the timer fires."""
        if self.fade_seconds <= 0:
            return
        remaining = self.sleep_remaining
        if remaining is None or remaining > self.fade_seconds:
            self._end_fade()
            return
        if self._volume_before_fade is None:
            self._volume_before_fade = self.volume
        factor = max(0.0, remaining / self.fade_seconds)
        self._set_engine_volume(round(self._volume_before_fade * factor))

    def _end_fade(self) -> None:
        """Restore the volume the user set before the fade started."""
        if self._volume_before_fade is None:
            return
        self.volume = self._volume_before_fade
        self._volume_before_fade = None
        self._apply_volume()

    # --- Background thread -------------------------------------------------
    def _start_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._last_tick = 0.0
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
        self._count_listening_time()
        state = self._player.get_state()
        ended = self._vlc is not None and state == self._vlc.State.Ended
        failed = self._vlc is not None and state == self._vlc.State.Error

        if failed:
            self._begin_reconnect()
            return

        # A scheduled reconnect is due.
        if self._retry_at is not None and time.monotonic() >= self._retry_at:
            self._reconnect_now()
            return

        self._remember_position()
        self._announce_new_chapter()
        self._update_fade()

        # Sleep timer (until the end of the chapter). A book in a single file
        # ends exactly once, so waiting for the end of a *track* would never
        # stop at a chapter mark - the position has to be watched instead.
        if self._sleep_until_chapter and self._sleep_chapter_end is not None:
            # One tick advances the position by POLL_INTERVAL * rate seconds;
            # stopping a moment early beats overshooting into the next chapter.
            tolerance = max(1.0, POLL_INTERVAL * self.rate)
            if self.position >= self._sleep_chapter_end - tolerance:
                log.info("Sleep timer: chapter finished at %.0f s", self.position)
                self._clear_chapter_timer()
                self._fire_sleep()
                return

        # End of track -> next track or end of book
        if ended:
            if self._index + 1 < len(self._tracks):
                if self._sleep_until_chapter:
                    self._clear_chapter_timer()
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
        self._end_fade()
        if self.on_sleep:
            self.on_sleep()

    # --- Reconnecting after a broken stream --------------------------------
    def _remember_position(self) -> None:
        """Keep the last position VLC reported while it was still playing.

        A stream that has died reports no position at all, so without this a
        reconnect would resume at the start of the track.
        """
        if self._player is None or not 0 <= self._index < len(self._tracks):
            return
        current = self._player.get_time()
        if current and current > 0:
            self._last_position = self._tracks[self._index].start_offset + current / 1000.0
            self._reconnect_attempts = 0

    def _begin_reconnect(self) -> None:
        """Schedule another attempt at the stream that just failed.

        A dropped connection is the normal case here - a phone leaving the
        flat's Wi-Fi, a server restarting - and a book should survive it
        instead of stopping and losing its place.
        """
        if self._retry_at is not None:
            return  # an attempt is already scheduled
        local = bool(
            self._tracks and 0 <= self._index < len(self._tracks)
            and self._tracks[self._index].local
        )
        self._reconnect_attempts += 1
        if local or not self._tracks or self._reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
            log.error(
                "Playback failed for track %d, giving up after %d attempt(s)",
                self._index, self._reconnect_attempts - 1,
            )
            self._stop_flag.set()
            self._reconnect_attempts = 0
            if self.on_error:
                self.on_error(
                    _("Playback failed. Press play again to continue from %s.")
                    % format_clock(self._last_position)
                )
            return
        delay = RECONNECT_DELAYS[min(self._reconnect_attempts - 1, len(RECONNECT_DELAYS) - 1)]
        self._retry_at = time.monotonic() + delay
        log.warning(
            "Playback failed for track %d - reconnecting in %.0f s (attempt %d of %d)",
            self._index, delay, self._reconnect_attempts, MAX_RECONNECT_ATTEMPTS,
        )
        if self.on_notice:
            self.on_notice(
                _("Connection lost - trying again (%(attempt)d of %(total)d)...")
                % {"attempt": self._reconnect_attempts, "total": MAX_RECONNECT_ATTEMPTS}
            )

    def _reconnect_now(self) -> None:
        """Reopen the current track at the last known position."""
        self._retry_at = None
        if not self._tracks:
            return
        index, offset = self._locate(self._last_position)
        log.info("Reconnecting at %.0f s (track %d)", self._last_position, index)
        try:
            with self._lock:
                self._load_index(index, offset, autoplay=True)
        except Exception:
            log.exception("Reconnect failed")
            self._begin_reconnect()
            return
        if self.on_notice:
            self.on_notice(_("Playback resumed."))

    def _announce_new_chapter(self) -> None:
        """Report a chapter the book moved into on its own."""
        if not self._chapters or self.on_chapter_change is None:
            return
        index = self.chapter_index_at(self.position)
        if index >= 0 and index != self._last_chapter_index:
            self._last_chapter_index = index
            self.on_chapter_change(index)

    def _clear_chapter_timer(self) -> None:
        self._sleep_until_chapter = False
        self._sleep_chapter_end = None

    def _count_listening_time(self) -> None:
        """Add the time played since the previous tick to the listening total."""
        now = time.monotonic()
        previous, self._last_tick = self._last_tick, now
        if not previous:
            return
        elapsed = now - previous
        # A long gap means the machine slept or the process was frozen - that
        # is not listening time, however long the wall clock says it was.
        if 0 < elapsed <= MAX_LISTENED_STEP and self.is_playing:
            with self._lock:
                self._listened += elapsed

    def _take_listened(self) -> float:
        with self._lock:
            listened, self._listened = self._listened, 0.0
        return listened

    # --- Progress synchronisation ------------------------------------------
    def _sync_now(self, is_finished: bool = False) -> None:
        """Queue a progress report for the server. Never blocks the caller.

        ``on_progress`` performs an HTTP request, and both callers must stay
        responsive: pause/stop run on the UI thread, and the tick loop still has
        the sleep timer and the next track to look after. The report is handed
        to :meth:`_sync_loop` instead, which always sends the most recent state -
        progress is absolute, so a newer report supersedes an older one.
        """
        if not self.on_progress or not self._tracks:
            return
        report = ProgressReport(
            position=self.position,
            duration=self.duration,
            is_finished=is_finished,
            listened=self._take_listened(),
        )
        with self._sync_lock:
            pending = self._pending_sync
            if pending is not None:
                # Superseding a queued report must not drop what it carried:
                # "finished" is a one-off event and listening time accumulates.
                report.is_finished = report.is_finished or pending.is_finished
                report.listened += pending.listened
            self._pending_sync = report
            self._ensure_sync_thread()
        self._sync_event.set()

    def _ensure_sync_thread(self) -> None:
        """Start the sync thread on first use. Called with ``_sync_lock`` held."""
        if self._sync_thread is not None and self._sync_thread.is_alive():
            return
        self._sync_stop.clear()
        self._sync_thread = threading.Thread(
            target=self._sync_loop, name="audiflix-sync", daemon=True
        )
        self._sync_thread.start()

    def _sync_loop(self) -> None:
        while True:
            self._sync_event.wait()
            self._sync_event.clear()
            # Read the stop flag before draining, so a report queued just before
            # the shutdown is still sent.
            stopping = self._sync_stop.is_set()
            self._drain_sync()
            if stopping:
                return

    def _drain_sync(self) -> None:
        while True:
            with self._sync_lock:
                report, self._pending_sync = self._pending_sync, None
            if report is None:
                return
            try:
                self.on_progress(
                    report.position, report.duration, report.is_finished, report.listened
                )
            except Exception:
                log.exception("Progress callback failed")

    def flush_sync(self, timeout: float = SYNC_FLUSH_TIMEOUT) -> None:
        """Send the queued progress report and stop the sync thread.

        Waits at most ``timeout`` seconds: the last position is worth a short
        wait when closing, an unreachable server is not worth a frozen window.
        """
        with self._sync_lock:
            thread = self._sync_thread
            self._sync_thread = None
        self._sync_stop.set()
        self._sync_event.set()
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
            if thread.is_alive():
                log.info("The last progress report is still on its way to the server")

    def shutdown(self) -> None:
        self.stop(sync=True)
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self.flush_sync()
        if self._player is not None:
            try:
                self._player.release()
            except Exception:
                log.exception("Could not release the VLC player")
        self._player = None
        self._instance = None
