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
from audiflix.i18n import _
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
            url_resolver=self.client.authed_url,
            default_rate=float(settings.get("default_speed", 1.0)),
            default_volume=int(settings.get("default_volume", 100)),
            sync_interval=float(settings.get("progress_sync_seconds", 15)),
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

    # --- Playback ----------------------------------------------------------
    def play_item(self, item: LibraryItem, episode=None) -> None:
        """Play a book or - when ``episode`` is given - a podcast episode.

        ``episode`` may be an Episode object (with ``.id``/``.title``) or an
        episode id (str).
        """
        episode_id = getattr(episode, "id", episode) if episode else None
        display_title = getattr(episode, "title", None) or item.title

        self.notify(_("Loading %s...") % display_title)

        def load():
            return self.client.play_item(item.id, episode_id)

        def started(session: dict):
            tracks_raw = session.get("audioTracks") or []
            if not tracks_raw:
                self.notify(_("No playable audio files were found."))
                return
            tracks = [
                {
                    "content_url": track.get("contentUrl", ""),
                    "url": self.client.authed_url(track.get("contentUrl", "")),
                    "start_offset": float(track.get("startOffset", 0.0)),
                    "duration": float(track.get("duration", 0.0)),
                }
                for track in tracks_raw
            ]
            total = float(session.get("duration") or sum(t["duration"] for t in tracks))
            start_time = float(session.get("currentTime") or 0.0)
            chapters = session.get("chapters") or []
            self.current_item = item
            self.current_episode = episode
            self.current_session_id = session.get("id")
            try:
                self.player.load(
                    tracks, total, start_time=start_time,
                    item_id=item.id, item_title=display_title,
                    chapters=chapters,
                )
                self.player.play()
            except PlayerError as exc:
                log.error("Playback could not be started: %s", exc)
                self.notify(str(exc))
                return
            self.notify(_("Playing: %s") % display_title)

        self.run_async(load, on_done=started, description="play-item")

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

    # --- Speed and volume --------------------------------------------------
    def speed_up(self) -> None:
        self._announce_speed(self.player.change_rate(0.1))

    def speed_down(self) -> None:
        self._announce_speed(self.player.change_rate(-0.1))

    def speed_reset(self) -> None:
        self._announce_speed(self.player.set_rate(float(self.settings.get("default_speed", 1.0))))

    def _announce_speed(self, rate: float) -> None:
        self.notify(_("Speed %s") % formatting.format_speed(rate))

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

    # --- Player callbacks (run on the player thread) -----------------------
    def _on_player_progress(self, position: float, duration: float, is_finished: bool) -> None:
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
            wx.CallAfter(self._handle_auth_expired, AuthExpiredError())
        except ApiError as exc:
            # Losing one sync is harmless; the next one will catch up.
            log.warning("Progress sync failed: %s", exc)

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
