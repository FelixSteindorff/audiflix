"""Application controller: bundles services and playback control.

The controller is the shared interface between the UI panels and the services
(API client, player, settings, status). It owns the threading rule of the whole
application - network calls run in the background, UI updates go through
``wx.CallAfter`` - and the playback actions triggered from the menu and the
keyboard shortcuts.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import wx

from audiflix import speech
from audiflix.api.client import ApiError, AudiobookshelfClient, AuthExpiredError
from audiflix.api.models import LibraryItem
from audiflix.audio.player import PlayerError, VlcPlayer
from audiflix.config import Settings
from audiflix.helpers import formatting
from audiflix.helpers.status import DownloadRegistry, ProgressIndex
from audiflix.i18n import _, ngettext
from audiflix.logging_setup import get_logger

log = get_logger(__name__)


class AppContext:
    def __init__(self, client: AudiobookshelfClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.registry = DownloadRegistry()
        self.progress = ProgressIndex(client.user)

        # active library selection: list of library ids plus a display name
        self.libraries: list[dict] = []
        self.active_library_ids: list[str] = []
        self.active_library_label: str = ""
        self.active_is_podcast: bool = False

        self.current_item: LibraryItem | None = None
        self.current_episode = None
        self.current_session_id: str | None = None
        self.status_cb: Callable[[str], None] | None = None
        self.auth_expired_cb: Callable[[], None] | None = None

        self.player = VlcPlayer(
            on_progress=self._on_player_progress,
            on_finished=self._on_player_finished,
            on_sleep=self._on_sleep,
            on_error=self._on_player_error,
            on_notice=self._on_player_notice,
            on_chapter_change=self._on_chapter_change,
            url_resolver=self.client.authed_url,
            default_rate=float(settings.get("default_speed", 1.0)),
            default_volume=int(settings.get("default_volume", 100)),
            sync_interval=float(settings.get("progress_sync_seconds", 15)),
            fade_seconds=float(settings.get("sleep_fade_seconds", 0)),
        )

    # --- Status message plus speech ---------------------------------------
    def notify(self, text: str, interrupt: bool = True, speak: bool = True) -> None:
        """Set the status bar and announce it (safe from any thread)."""
        if not text:
            return

        def do():
            if self.status_cb:
                self.status_cb(text)
            if speak:
                speech.announce(text, interrupt=interrupt)

        if wx.IsMainThread():
            do()
        else:
            wx.CallAfter(do)

    # --- Threading helper --------------------------------------------------
    def run_async(
        self,
        func: Callable,
        on_done: Callable | None = None,
        on_error: Callable[[Exception], None] | None = None,
        description: str = "",
    ) -> None:
        """Run ``func`` on a worker thread and deliver the result on the main thread."""

        def worker():
            try:
                result = func()
            except AuthExpiredError as exc:
                log.info("Session expired during %s", description or "a background call")
                wx.CallAfter(self._handle_auth_expired, exc)
                return
            except ApiError as exc:
                log.warning("API call failed (%s): %s", description or func, exc)
                wx.CallAfter(self._deliver_error, exc, on_error)
                return
            except Exception as exc:
                log.exception("Background call failed (%s)", description or func)
                wx.CallAfter(self._deliver_error, exc, on_error)
                return
            if on_done:
                wx.CallAfter(on_done, result)

        threading.Thread(
            target=worker, name=f"audiflix-{description or 'worker'}", daemon=True
        ).start()

    def _deliver_error(self, exc: Exception, on_error: Callable[[Exception], None] | None) -> None:
        if on_error:
            on_error(exc)
        else:
            self.notify(_("Error: %s") % exc)

    def _handle_auth_expired(self, exc: AuthExpiredError) -> None:
        self.notify(str(exc))
        if self.auth_expired_cb:
            self.auth_expired_cb()

    # --- Library selection -------------------------------------------------
    def set_libraries(self, libraries: list[dict]) -> None:
        self.libraries = libraries

    def select_all_books(self) -> None:
        books = [lib for lib in self.libraries if lib.get("mediaType") != "podcast"]
        self.active_library_ids = [lib["id"] for lib in books]
        self.active_library_label = _("All books")
        self.active_is_podcast = False
        self._remember_library("all")

    def select_library(self, library: dict) -> None:
        self.active_library_ids = [library["id"]]
        self.active_library_label = library.get("name", "")
        self.active_is_podcast = library.get("mediaType") == "podcast"
        self._remember_library(library["id"])

    def _remember_library(self, value: str) -> None:
        self.settings["last_library"] = value
        self.settings.save()

    def restore_last_library(self) -> bool:
        """Restore the previously selected library. True on success."""
        last = self.settings.get("last_library", "")
        if not last:
            return False
        if last == "all":
            if any(lib.get("mediaType") != "podcast" for lib in self.libraries):
                self.select_all_books()
                return True
            return False
        library = next((lib for lib in self.libraries if lib.get("id") == last), None)
        if library:
            self.select_library(library)
            return True
        return False

    # --- Status helpers for the panels -------------------------------------
    def is_downloaded(self, item: LibraryItem) -> bool:
        return self.registry.is_downloaded(item.id)

    def is_finished(self, item: LibraryItem) -> bool:
        return self.progress.is_finished(item.id)

    def episode_status(self, item_id: str, episode_id: str) -> str:
        """Listening state of a single podcast episode, for its list row."""
        return formatting.progress_label(
            self.progress.progress_for(item_id, episode_id),
            self.progress.is_finished(item_id, episode_id),
        )

    def item_progress(self, item: LibraryItem) -> str:
        """Progress column of a list row: how far in, how much is left."""
        return formatting.progress_column(
            self.progress.progress_for(item.id),
            self.progress.is_finished(item.id),
            item.duration,
            self.progress.current_time(item.id),
        )

    def item_status(self, item: LibraryItem) -> str:
        """Status column of a list row: whether the title is available offline."""
        return formatting.download_label(
            self.registry.is_downloaded(item.id),
            self.registry.is_playable_offline(item.id),
        )

    # --- Playback ----------------------------------------------------------
    def play_item(self, item: LibraryItem, episode=None) -> None:
        """Play a book or - when ``episode`` is given - a podcast episode.

        ``episode`` may be an Episode object (with ``.id``/``.title``) or an
        episode id (str).

        A downloaded title is played from disk. The server is still asked for a
        playback session, because that is where the resume position and the
        chapter marks come from; when it cannot be reached, the download is
        played offline from its manifest instead.
        """
        episode_id = getattr(episode, "id", episode) if episode else None
        display_title = getattr(episode, "title", None) or item.title
        # Podcast episodes are not downloaded as files, only whole books are.
        local_tracks = [] if episode_id else self.registry.local_tracks(item.id)

        self.notify(_("Loading %s...") % display_title)

        def load():
            try:
                return self.client.play_item(item.id, episode_id)
            except ApiError as exc:
                if not local_tracks or exc.is_auth_error:
                    # Without local files there is nothing to fall back to, and
                    # a sign-in problem has to be reported rather than hidden.
                    raise
                log.info("Server unreachable (%s) - playing %s offline", exc, item.id)
                return None

        def started(session: dict | None):
            if session is None:
                self._play_offline(item, local_tracks)
                return
            tracks = local_tracks or self._session_tracks(session)
            if not tracks:
                self.notify(_("No playable audio files were found."))
                return
            total = float(session.get("duration") or sum(t["duration"] for t in tracks))
            start_time = float(session.get("currentTime") or 0.0)
            chapters = session.get("chapters") or []
            self.current_session_id = session.get("id")
            self._start_playback(
                item, episode, tracks, total, start_time, chapters, display_title,
                offline=bool(local_tracks),
            )

        self.run_async(load, on_done=started, description="play-item")

    def _session_tracks(self, session: dict) -> list[dict]:
        return [
            {
                "content_url": track.get("contentUrl", ""),
                "url": self.client.authed_url(track.get("contentUrl", "")),
                "start_offset": float(track.get("startOffset", 0.0)),
                "duration": float(track.get("duration", 0.0)),
            }
            for track in (session.get("audioTracks") or [])
        ]

    def _play_offline(self, item: LibraryItem, tracks: list[dict]) -> None:
        """Play a downloaded title without the server.

        The position comes from the manifest, which is where playback wrote it
        the last time the server could not be reached.
        """
        manifest = self.registry.manifest(item.id) or {}
        duration = float(manifest.get("duration") or sum(t["duration"] for t in tracks))
        start_time = float(manifest.get("position") or 0.0)
        if not start_time:
            start_time = self.progress.current_time(item.id)
        self.current_session_id = None
        self._start_playback(
            item, None, tracks, duration, start_time,
            manifest.get("chapters") or [], item.title, offline=True, disconnected=True,
        )

    def _start_playback(
        self,
        item: LibraryItem,
        episode,
        tracks: list[dict],
        total: float,
        start_time: float,
        chapters: list,
        display_title: str,
        offline: bool = False,
        disconnected: bool = False,
    ) -> None:
        self.current_item = item
        self.current_episode = episode
        try:
            self.player.load(
                tracks, total, start_time=start_time,
                item_id=item.id, item_title=display_title,
                chapters=chapters,
            )
            self.player.set_rate(self.speed_for(item))
            self.player.play()
        except PlayerError as exc:
            log.error("Playback could not be started: %s", exc)
            self.notify(str(exc))
            return
        if disconnected:
            self.notify(_("Playing offline: %s") % display_title)
        elif offline:
            self.notify(_("Playing from the download: %s") % display_title)
        else:
            self.notify(_("Playing: %s") % display_title)

    def toggle_play(self) -> None:
        if not self.player.has_media:
            self.notify(_("No title loaded."))
            return
        playing = self.player.toggle()
        self.notify(_("Playing") if playing else _("Paused"))

    def skip_back(self) -> None:
        if not self._require_media():
            return
        self.player.skip(-float(self.settings.get("skip_back_seconds", 15)))
        self._announce_position()

    def skip_forward(self) -> None:
        if not self._require_media():
            return
        self.player.skip(float(self.settings.get("skip_forward_seconds", 30)))
        self._announce_position()

    # --- Chapters ----------------------------------------------------------
    def next_chapter(self) -> None:
        if not self._require_chapters():
            return
        self._announce_chapter(self.player.next_chapter())

    def prev_chapter(self) -> None:
        if not self._require_chapters():
            return
        self._announce_chapter(self.player.prev_chapter())

    def announce_chapter(self) -> None:
        if not self._require_chapters():
            return
        self._announce_chapter(self.player.current_chapter)

    def jump_to_chapter(self, index: int) -> None:
        self._announce_chapter(self.player.seek_chapter(index))

    def jump_to_time(self, seconds: float) -> None:
        """Jump to a global position (a bookmark, for example)."""
        if not self._require_media():
            return
        self.player.seek(float(seconds), autoplay=self.player.is_playing)
        self.announce_time()

    def _require_media(self) -> bool:
        if not self.player.has_media:
            self.notify(_("No title loaded."))
            return False
        return True

    def _require_chapters(self) -> bool:
        if not self._require_media():
            return False
        if not self.player.has_chapters:
            self.notify(_("This title has no chapters."))
            return False
        return True

    def _announce_chapter(self, chapter: dict | None) -> None:
        if not chapter:
            self.notify(_("No chapter."))
            return
        index = self.player.current_chapter_index + 1
        total = len(self.player.chapters)
        title = chapter.get("title") or _("Chapter %d") % index
        self.notify(
            _("Chapter %(index)d of %(total)d: %(title)s")
            % {"index": index, "total": total, "title": title}
        )

    # --- Speed -------------------------------------------------------------
    # The settings hold one default speed for everything plus an override per
    # title. Changing the speed while a title is playing saves it for that
    # title, so a fast reader and a slow one keep their own pace.
    @property
    def default_speed(self) -> float:
        return float(self.settings.get("default_speed", 1.0))

    def speed_for(self, item: LibraryItem | None) -> float:
        """Speed a title should start at: its own, or the general default."""
        if item is not None and self.settings.get("remember_speed_per_title", True):
            stored = (self.settings.get("book_speeds") or {}).get(item.id)
            if stored:
                try:
                    return float(stored)
                except (TypeError, ValueError):
                    log.warning("Ignoring an unusable stored speed for %s", item.id)
        return self.default_speed

    def has_own_speed(self, item: LibraryItem | None) -> bool:
        if item is None:
            return False
        return item.id in (self.settings.get("book_speeds") or {})

    def speed_up(self) -> None:
        self.set_speed(round(self.player.rate + 0.1, 2))

    def speed_down(self) -> None:
        self.set_speed(round(self.player.rate - 0.1, 2))

    def set_speed(self, rate: float, announce: bool = True) -> float:
        """Apply a speed and remember it for the title that is playing."""
        applied = self.player.set_rate(rate)
        saved = self._remember_speed(applied)
        if announce:
            if saved:
                self.notify(
                    _("Speed %(speed)s, saved for %(title)s")
                    % {
                        "speed": formatting.format_speed(applied),
                        "title": self.player.item_title or _("this title"),
                    }
                )
            else:
                self.notify(_("Speed %s") % formatting.format_speed(applied))
        return applied

    def speed_reset(self) -> None:
        """Back to the default speed, and forget this title's own setting."""
        self.forget_speed(self.current_item)
        applied = self.player.set_rate(self.default_speed)
        self.notify(
            _("Speed %s (default)") % formatting.format_speed(applied)
        )

    def _remember_speed(self, rate: float) -> bool:
        """Store ``rate`` for the current title. True when it was saved."""
        item = self.current_item
        if item is None or not self.settings.get("remember_speed_per_title", True):
            return False
        speeds = dict(self.settings.get("book_speeds") or {})
        if abs(rate - self.default_speed) < 0.001:
            # Same as the default - no need to carry an entry for it.
            speeds.pop(item.id, None)
        else:
            speeds[item.id] = round(rate, 2)
        self.settings["book_speeds"] = speeds
        self.settings.save()
        return item.id in speeds

    def forget_speed(self, item: LibraryItem | None) -> None:
        if item is None:
            return
        speeds = dict(self.settings.get("book_speeds") or {})
        if speeds.pop(item.id, None) is not None:
            self.settings["book_speeds"] = speeds
            self.settings.save()

    def announce_speed(self) -> None:
        rate = self.player.rate
        if self.has_own_speed(self.current_item):
            self.notify(
                _("Speed %(speed)s, saved for %(title)s")
                % {
                    "speed": formatting.format_speed(rate),
                    "title": self.player.item_title or _("this title"),
                }
            )
        else:
            self.notify(_("Speed %s") % formatting.format_speed(rate))

    # --- Volume ------------------------------------------------------------

    def volume_up(self) -> None:
        step = int(self.settings.get("volume_step", 5))
        self._announce_volume(self.player.change_volume(step))

    def volume_down(self) -> None:
        step = int(self.settings.get("volume_step", 5))
        self._announce_volume(self.player.change_volume(-step))

    def _announce_volume(self, volume: int) -> None:
        self.notify(_("Volume %d percent") % volume)

    def announce_time(self) -> None:
        if not self._require_media():
            return
        text = formatting.announce_position(self.player.position, self.player.duration)
        if self.status_cb:
            self.status_cb(formatting.format_position(self.player.position, self.player.duration))
        speech.announce(text, interrupt=True, force=True)

    def _announce_position(self) -> None:
        if self.settings.get("announce_on_seek", True):
            self.announce_time()

    # --- Bookmarks / sleep timer -------------------------------------------
    def add_bookmark(self) -> None:
        if not self.current_item:
            self.notify(_("No title loaded."))
            return
        time_s = self.player.position
        item = self.current_item

        def do():
            self.client.add_bookmark(item.id, time_s, formatting.format_clock(time_s))
            return time_s

        self.run_async(
            do,
            on_done=lambda t: self.notify(
                _("Bookmark set at %s.") % formatting.format_clock(t)
            ),
            description="add-bookmark",
        )

    def set_sleep_timer(self, minutes: float | None, until_chapter: bool = False) -> None:
        self.player.set_sleep_timer(minutes, until_chapter)
        if until_chapter:
            self.notify(_("Sleep timer: until the end of the chapter"))
        elif minutes:
            self.notify(_("Sleep timer: %d minutes") % int(minutes))
        else:
            self.notify(_("Sleep timer off"))

    def extend_sleep_timer(self, minutes: float) -> None:
        """Add time to the running timer - the "just one more chapter" case."""
        remaining = self.player.extend_sleep_timer(minutes)
        self.notify(
            _("Sleep timer extended, %s remaining")
            % formatting.format_duration(remaining or 0.0)
        )

    def announce_sleep_timer(self) -> None:
        remaining = self.player.sleep_remaining
        if remaining is None:
            self.notify(_("No sleep timer is running."))
            return
        self.notify(
            _("Sleep timer: %s remaining") % formatting.format_duration(remaining)
        )

    # --- Tracks ------------------------------------------------------------
    def next_track(self) -> None:
        if not self._require_media():
            return
        self._announce_track(self.player.next_track())

    def prev_track(self) -> None:
        if not self._require_media():
            return
        self._announce_track(self.player.prev_track())

    def _announce_track(self, position: tuple[int, int] | None) -> None:
        if position is None:
            self.notify(_("No further audio file."))
            return
        number, total = position
        if total <= 1:
            self.notify(_("This title is a single audio file."))
            return
        self.notify(
            _("File %(number)d of %(total)d") % {"number": number, "total": total}
        )

    def jump_to_percent(self, percent: float) -> None:
        """Jump to a share of the whole title (0-100)."""
        if not self._require_media():
            return
        duration = self.player.duration
        if duration <= 0:
            self.notify(_("The length of this title is unknown."))
            return
        self.jump_to_time(duration * max(0.0, min(percent, 100.0)) / 100.0)

    # --- Player callbacks (run on the player's sync thread) ----------------
    def _on_player_progress(
        self, position: float, duration: float, is_finished: bool, listened: float = 0.0
    ) -> None:
        item = self.current_item
        if not item:
            return
        episode_id = getattr(self.current_episode, "id", None)
        try:
            self.client.sync_progress(
                item.id, position, duration, is_finished, episode_id=episode_id
            )
        except AuthExpiredError:
            log.info("Progress sync skipped: session expired")
            self.registry.record_offline_position(item.id, position)
            wx.CallAfter(self._handle_auth_expired, AuthExpiredError())
            return
        except ApiError as exc:
            # Losing one sync is harmless while the server is reachable; for a
            # downloaded title it may not be, so the position is kept locally
            # and pushed as soon as the server answers again.
            log.warning("Progress sync failed: %s", exc)
            self.registry.record_offline_position(item.id, position)
            return
        self.registry.clear_offline_position(item.id, position)
        self._sync_session(position, duration, listened)

    def _sync_session(self, position: float, duration: float, listened: float) -> None:
        """Report the same progress to the open playback session.

        The progress endpoint alone keeps the resume position correct, but the
        server's listening statistics are built from sessions - without this
        the time spent listening in Audiflix would never show up there.
        """
        session_id = self.current_session_id
        if not session_id or listened <= 0:
            return
        try:
            self.client.sync_session(session_id, position, listened, duration)
        except ApiError as exc:
            if exc.status == 404:
                # The server has already closed the session (it does that after
                # a while); reporting to it again would fail every single time.
                log.info("Playback session %s no longer exists - stopping session sync", session_id)
                self.current_session_id = None
            else:
                log.warning("Session sync failed: %s", exc)

    def _on_player_finished(self) -> None:
        self.notify(_("Title finished."))
        if self.current_item:
            self.run_async(
                lambda: self.progress.update(self.client.fetch_me()),
                description="refresh-progress",
            )

    def _on_sleep(self) -> None:
        self.notify(_("Sleep timer elapsed - playback paused."))

    def _on_player_error(self, message: str) -> None:
        self.notify(message)

    def _on_player_notice(self, message: str) -> None:
        # Reconnect messages: say them, but do not cut off what is being read.
        self.notify(message, interrupt=False)

    def _on_chapter_change(self, index: int) -> None:
        """Announce a chapter the book moved into by itself."""
        if not self.settings.get("announce_chapter_change", True):
            return
        chapters = self.player.chapters
        if not 0 <= index < len(chapters):
            return
        title = chapters[index].get("title") or _("Chapter %d") % (index + 1)
        self.notify(_("Chapter: %s") % title, interrupt=False)

    # --- Offline progress --------------------------------------------------
    def flush_offline_progress(self) -> None:
        """Send positions that were played while the server was unreachable."""
        pending = self.registry.pending_positions()
        if not pending:
            return

        def push():
            sent = 0
            for item_id, position in pending.items():
                manifest = self.registry.manifest(item_id) or {}
                duration = float(manifest.get("duration") or 0.0)
                try:
                    self.client.sync_progress(item_id, position, duration)
                except ApiError as exc:
                    log.info("Offline progress for %s stays pending: %s", item_id, exc)
                    continue
                self.registry.clear_offline_position(item_id, position)
                sent += 1
            return sent

        def done(count: int):
            if count:
                log.info("Pushed offline progress for %d title(s)", count)
                self.notify(
                    ngettext(
                        "Offline progress for %d title sent to the server.",
                        "Offline progress for %d titles sent to the server.",
                        count,
                    ) % count,
                    speak=False,
                )
                self.run_async(
                    lambda: self.progress.update(self.client.fetch_me()),
                    description="refresh-progress",
                )

        self.run_async(push, on_done=done, description="flush-offline-progress")

    # --- Shutdown ----------------------------------------------------------
    def shutdown(self, network_timeout: float = 3.0) -> None:
        """Close the playback session and stop the player.

        The session is closed on a worker thread with a short join: the window
        is already closing, and a slow or unreachable server must not freeze
        the application for the full request timeout.
        """
        session_id = self.current_session_id
        self.current_session_id = None
        if session_id:
            position = self.player.position

            def close():
                try:
                    self.client.close_session(session_id, position)
                except ApiError as exc:
                    log.info("Could not close the playback session: %s", exc)
                except Exception:
                    log.exception("Unexpected error while closing the playback session")

            worker = threading.Thread(target=close, name="audiflix-close-session", daemon=True)
            worker.start()
            worker.join(timeout=network_timeout)
            if worker.is_alive():
                log.info("Playback session close is still running - leaving it to the daemon thread")
        self.player.shutdown()
