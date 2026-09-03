"""HTTP client for the Audiobookshelf REST API.

The client wraps authentication, every endpoint Audiflix needs, and the
aggregation across several book libraries (the "All books" view). It is
deliberately synchronous; the UI calls it from worker threads.

Authentication
--------------
Audiobookshelf 2.26 introduced JWT authentication: ``POST /login`` returns a
short-lived ``accessToken`` (about one hour) plus a long-lived refresh token,
while the legacy long-lived ``user.token`` is still present for backwards
compatibility but is being removed. Audiflix therefore:

* sends ``x-return-tokens: true`` on login so the refresh token comes back in
  the response body (Audiflix is not a browser and does not use cookies),
* prefers ``accessToken`` and falls back to ``token`` on older servers,
* refreshes proactively shortly before the access token expires and reactively
  once on any ``401``, then retries the failed request,
* attaches ``?token=`` **only** to URLs on the configured server host, so a
  media URL pointing at a third-party CDN can never receive the user's token.
"""

from __future__ import annotations

import base64
import binascii
import json as jsonlib
import os
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlencode

import requests

from audiflix import __version__
from audiflix.api.models import Author, Bookmark, Collection, LibraryItem, Series
from audiflix.helpers import urls as urlhelp
from audiflix.helpers.text import truncate
from audiflix.i18n import _
from audiflix.logging_setup import get_logger

log = get_logger(__name__)

# Filter value for "finished" titles: ABS expects progress.<base64>
FINISHED_FILTER = "progress." + base64.b64encode(b"finished").decode("ascii")
IN_PROGRESS_FILTER = "progress." + base64.b64encode(b"in-progress").decode("ascii")
NOT_STARTED_FILTER = "progress." + base64.b64encode(b"not-started").decode("ascii")

DEFAULT_TIMEOUT = 30
#: Refresh the access token this many seconds before it actually expires.
REFRESH_MARGIN_SECONDS = 120

CLIENT_NAME = "Audiflix"
DEVICE_ID = "audiflix-desktop"


class ApiError(RuntimeError):
    """An API call failed (network problem or HTTP status)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status

    @property
    def is_auth_error(self) -> bool:
        return self.status in (401, 403)


class AuthExpiredError(ApiError):
    """The session is no longer valid and could not be refreshed."""

    def __init__(self, message: str | None = None):
        super().__init__(message or _("Your session has expired. Please sign in again."), 401)


def decode_jwt_expiry(token: str) -> float | None:
    """Return the ``exp`` claim of a JWT as a unix timestamp, or ``None``.

    The signature is *not* verified - only the server can do that. We just want
    to know when to ask for a new token instead of waiting for a 401.
    """
    try:
        payload_b64 = token.split(".")[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload = jsonlib.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except (IndexError, ValueError, binascii.Error, UnicodeDecodeError):
        return None
    exp = payload.get("exp")
    try:
        return float(exp) if exp is not None else None
    except (TypeError, ValueError):
        return None


def _remove_quietly(path: str) -> None:
    """Delete a leftover partial download; failing to do so is not an error."""
    try:
        os.unlink(path)
    except OSError:
        pass


class AudiobookshelfClient:
    def __init__(
        self,
        server_url: str,
        token: str | None = None,
        refresh_token: str | None = None,
        on_tokens_changed: Callable[[str | None, str | None], None] | None = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.token: str | None = None
        self.refresh_token = refresh_token
        self.user: dict[str, Any] = {}
        self.server_version: str = ""
        self.on_tokens_changed = on_tokens_changed
        self._token_expires_at: float | None = None
        self._auth_lock = threading.RLock()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = f"{CLIENT_NAME}/{__version__}"
        if token:
            self._apply_token(token, notify=False)

    # --- Authentication ---------------------------------------------------
    def _apply_token(self, token: str, notify: bool = True) -> None:
        self.token = token
        self._token_expires_at = decode_jwt_expiry(token)
        self._session.headers["Authorization"] = f"Bearer {token}"
        if notify and self.on_tokens_changed:
            self.on_tokens_changed(self.token, self.refresh_token)

    def _clear_token(self) -> None:
        self.token = None
        self._token_expires_at = None
        self._session.headers.pop("Authorization", None)

    def _store_auth_response(self, data: dict[str, Any]) -> str:
        """Read tokens out of a ``/login`` or ``/auth/refresh`` response."""
        user = data.get("user") or {}
        # ABS >= 2.26 returns accessToken; older versions only have token.
        token = user.get("accessToken") or data.get("accessToken") or user.get("token")
        if not token:
            raise ApiError(_("Sign-in failed: the server did not return a token."))
        refresh = (
            data.get("refreshToken")
            or user.get("refreshToken")
            or self.refresh_token
        )
        self.refresh_token = refresh
        if user:
            self.user = user
        self.server_version = str(data.get("serverVersion") or self.server_version or "")
        self._apply_token(token)
        return token

    def login(self, username: str, password: str) -> str:
        """Sign in, store the tokens in the session and return the access token."""
        data = self._request(
            "POST",
            "/login",
            json={"username": username, "password": password},
            auth_required=False,
            headers={"x-return-tokens": "true"},
            allow_refresh=False,
        )
        token = self._store_auth_response(data)
        log.info(
            "Signed in as %s (server version %s, refresh token %s)",
            username,
            self.server_version or "unknown",
            "available" if self.refresh_token else "not provided",
        )
        return token

    def refresh_access_token(self) -> bool:
        """Exchange the refresh token for a new access token. True on success."""
        with self._auth_lock:
            if not self.refresh_token:
                return False
            try:
                data = self._request(
                    "POST",
                    "/auth/refresh",
                    auth_required=False,
                    headers={"x-refresh-token": self.refresh_token},
                    allow_refresh=False,
                )
            except ApiError as exc:
                log.warning("Token refresh failed: %s", exc)
                if exc.status in (401, 403, 404):
                    # 404 = server too old for /auth/refresh; stop trying.
                    self.refresh_token = None
                return False
            try:
                self._store_auth_response(data)
            except ApiError:
                return False
            log.info("Access token refreshed")
            return True

    def _token_expires_soon(self) -> bool:
        if self._token_expires_at is None:
            return False
        return time.time() >= self._token_expires_at - REFRESH_MARGIN_SECONDS

    def ensure_fresh_token(self) -> None:
        """Refresh proactively when the access token is about to expire."""
        if self.refresh_token and self._token_expires_soon():
            self.refresh_access_token()

    def logout(self) -> None:
        headers = {"x-refresh-token": self.refresh_token} if self.refresh_token else None
        try:
            self._request("POST", "/logout", headers=headers, allow_refresh=False)
        except ApiError as exc:
            log.info("Logout request failed (ignored): %s", exc)
        finally:
            self.refresh_token = None
            self._clear_token()

    def fetch_me(self) -> dict[str, Any]:
        """Current user object including mediaProgress/bookmarks."""
        self.user = self._request("GET", "/api/me")
        return self.user

    def server_status(self) -> dict[str, Any]:
        """Unauthenticated ``/status`` - used to check a URL before signing in."""
        return self._request("GET", "/status", auth_required=False, allow_refresh=False)

    # --- Libraries --------------------------------------------------------
    def libraries(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/api/libraries")
        return data.get("libraries", [])

    def book_libraries(self) -> list[dict[str, Any]]:
        return [lib for lib in self.libraries() if lib.get("mediaType") != "podcast"]

    # --- Items / lists ----------------------------------------------------
    def library_items(
        self,
        library_id: str,
        sort: str | None = None,
        desc: bool = False,
        filter_: str | None = None,
        limit: int = 0,
        page: int = 0,
    ) -> list[LibraryItem]:
        params: dict[str, Any] = {"minified": 1}
        if sort:
            params["sort"] = sort
        if desc:
            params["desc"] = 1
        if filter_:
            params["filter"] = filter_
        if limit:
            params["limit"] = limit
            params["page"] = page
        data = self._request("GET", f"/api/libraries/{library_id}/items", params=params)
        return [LibraryItem(r) for r in data.get("results", [])]

    def items_in_progress(self, limit: int = 25) -> list[LibraryItem]:
        """Continue listening: recently played, not yet finished titles."""
        data = self._request("GET", "/api/me/items-in-progress", params={"limit": limit})
        return [LibraryItem(r) for r in data.get("libraryItems", [])]

    def recently_added(self, library_id: str, limit: int = 50) -> list[LibraryItem]:
        return self.library_items(library_id, sort="addedAt", desc=True, limit=limit)

    def finished_items(self, library_id: str, limit: int = 100) -> list[LibraryItem]:
        return self.library_items(
            library_id, sort="media.metadata.title", filter_=FINISHED_FILTER, limit=limit
        )

    def recently_added_all(self, library_ids: Iterable[str], limit: int = 50) -> list[LibraryItem]:
        """Aggregate across several book libraries and sort by date."""
        merged: list[LibraryItem] = []
        for lib_id in library_ids:
            merged.extend(self.recently_added(lib_id, limit=limit))
        merged.sort(key=lambda it: it.added_at, reverse=True)
        return merged[:limit] if limit else merged

    def finished_items_all(self, library_ids: Iterable[str], limit: int = 100) -> list[LibraryItem]:
        merged: list[LibraryItem] = []
        for lib_id in library_ids:
            merged.extend(self.finished_items(lib_id, limit=limit))
        merged.sort(key=lambda it: it.title.lower())
        return merged

    def all_items(
        self,
        library_ids: Iterable[str],
        sort: str = "addedAt",
        desc: bool = True,
        limit: int = 0,
        filter_: str | None = None,
    ) -> list[LibraryItem]:
        """Merge items of several libraries and sort them consistently."""
        merged: list[LibraryItem] = []
        for lib_id in library_ids:
            merged.extend(
                self.library_items(lib_id, sort=sort, desc=desc, limit=limit, filter_=filter_)
            )
        if sort == "addedAt":
            merged.sort(key=lambda it: it.added_at, reverse=desc)
        else:
            merged.sort(key=lambda it: it.title.lower(), reverse=desc)
        return merged

    def item(self, item_id: str, expanded: bool = True) -> LibraryItem:
        params = {"expanded": 1} if expanded else None
        data = self._request("GET", f"/api/items/{item_id}", params=params)
        return LibraryItem(data)

    # --- Search -----------------------------------------------------------
    def search_library(self, library_id: str, query: str, limit: int = 25) -> list[LibraryItem]:
        data = self._request(
            "GET",
            f"/api/libraries/{library_id}/search",
            params={"q": query, "limit": limit},
        )
        results: list[LibraryItem] = []
        for key in ("book", "podcast"):
            for entry in data.get(key, []) or []:
                library_item = entry.get("libraryItem") if isinstance(entry, dict) else None
                if library_item:
                    results.append(LibraryItem(library_item))
        return results

    # --- Authors ----------------------------------------------------------
    def authors(self, library_id: str) -> list[Author]:
        data = self._request("GET", f"/api/libraries/{library_id}/authors")
        return [Author(a) for a in data.get("authors", [])]

    def authors_all(self, library_ids: Iterable[str]) -> list[Author]:
        merged: dict[str, Author] = {}
        for lib_id in library_ids:
            for author in self.authors(lib_id):
                merged.setdefault(author.id, author)
        return list(merged.values())

    def author(self, author_id: str) -> dict[str, Any]:
        return self._request(
            "GET", f"/api/authors/{author_id}", params={"include": "items,series"}
        )

    def author_items(self, author_id: str) -> list[LibraryItem]:
        data = self.author(author_id)
        return [LibraryItem(r) for r in data.get("libraryItems", [])]

    # --- Series -----------------------------------------------------------
    def series(self, library_id: str, page_size: int = 200) -> list[Series]:
        """All series of a library including their books (in reading order).

        Unlike ``/authors`` the series endpoint requires a ``limit`` (> 0);
        without it ABS returns nothing. We therefore page through the results.
        """
        results: list[Series] = []
        page = 0
        while True:
            data = self._request(
                "GET",
                f"/api/libraries/{library_id}/series",
                params={"limit": page_size, "page": page},
            )
            if isinstance(data, dict):
                batch = data.get("results", []) or []
                total = int(data.get("total") or 0)
            else:  # tolerant fallback for ABS versions returning a bare list
                batch = data or []
                total = len(batch)
            results.extend(Series(s) for s in batch)
            if len(batch) < page_size or (total and len(results) >= total):
                break
            page += 1
        return results

    def series_all(self, library_ids: Iterable[str]) -> list[Series]:
        merged: dict[str, Series] = {}
        for lib_id in library_ids:
            for item in self.series(lib_id):
                merged.setdefault(item.id, item)
        return list(merged.values())

    # --- Collections ------------------------------------------------------
    def collections(self, library_id: str) -> list[Collection]:
        data = self._request("GET", f"/api/libraries/{library_id}/collections")
        if isinstance(data, dict):
            raw = data.get("collections") or data.get("results") or []
        else:
            raw = data or []
        return [Collection(c) for c in raw]

    def collections_all(self, library_ids: Iterable[str]) -> list[Collection]:
        merged: list[Collection] = []
        for lib_id in library_ids:
            merged.extend(self.collections(lib_id))
        return merged

    def create_collection(
        self, library_id: str, name: str, book_ids: list[str] | None = None
    ) -> dict[str, Any]:
        payload = {"libraryId": library_id, "name": name, "books": book_ids or []}
        return self._request("POST", "/api/collections", json=payload)

    def add_to_collection(self, collection_id: str, item_id: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/api/collections/{collection_id}/book", json={"id": item_id}
        )

    # --- Podcasts ---------------------------------------------------------
    def search_podcasts(self, term: str) -> list[dict[str, Any]]:
        # The ABS endpoint is "/search/podcast" (singular).
        data = self._request("GET", "/api/search/podcast", params={"term": term})
        if isinstance(data, list):
            return data
        return data.get("podcasts", []) if isinstance(data, dict) else []

    def add_podcast(
        self,
        library_id: str,
        folder_id: str,
        path: str,
        metadata: dict[str, Any],
        auto_download: bool = False,
    ) -> dict[str, Any]:
        """Create a new podcast. ``path`` must be a non-empty path inside the
        chosen library folder (required by ABS)."""
        payload = {
            "libraryId": library_id,
            "folderId": folder_id,
            "path": path,
            "media": {"metadata": metadata},
            "autoDownloadEpisodes": auto_download,
        }
        return self._request("POST", "/api/podcasts", json=payload)

    def check_new_episodes(self, podcast_id: str, limit: int = 3) -> list[dict[str, Any]]:
        """Check the RSS feed for new episodes and let ABS download up to
        ``limit`` of them. Returns the newly found episodes."""
        data = self._request(
            "GET", f"/api/podcasts/{podcast_id}/checknew", params={"limit": limit}
        )
        if isinstance(data, dict):
            return data.get("episodes") or []
        return []

    def set_auto_download(self, item_id: str, enabled: bool) -> dict[str, Any]:
        """Toggle automatic episode downloads for a podcast."""
        return self._request(
            "PATCH",
            f"/api/items/{item_id}/media",
            json={"autoDownloadEpisodes": bool(enabled)},
        )

    def library_folders(self, library_id: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/api/libraries/{library_id}")
        library = data.get("library", data)
        return library.get("folders", []) if isinstance(library, dict) else []

    # --- Playback / progress ---------------------------------------------
    def play_item(self, item_id: str, episode_id: str | None = None) -> dict[str, Any]:
        """Start a playback session; returns audioTracks + session id."""
        payload = {
            "deviceInfo": {
                "clientName": CLIENT_NAME,
                "clientVersion": __version__,
                "deviceId": DEVICE_ID,
            },
            "supportedMimeTypes": [
                "audio/flac", "audio/mpeg", "audio/mp4", "audio/aac",
                "audio/ogg", "audio/opus", "audio/x-m4a", "audio/x-m4b",
            ],
            "mediaPlayer": "vlc",
            "forceDirectPlay": True,
        }
        path = f"/api/items/{item_id}/play"
        if episode_id:
            path += f"/{episode_id}"
        return self._request("POST", path, json=payload)

    def sync_progress(
        self,
        item_id: str,
        current_time: float,
        duration: float,
        is_finished: bool = False,
        episode_id: str | None = None,
    ) -> None:
        progress = 1.0 if is_finished else (current_time / duration if duration else 0.0)
        payload = {
            "currentTime": current_time,
            "duration": duration,
            "progress": min(max(progress, 0.0), 1.0),
            "isFinished": is_finished,
        }
        self._request("PATCH", self._progress_path(item_id, episode_id), json=payload)

    def sync_session(
        self,
        session_id: str,
        current_time: float,
        time_listened: float = 0.0,
        duration: float = 0.0,
    ) -> None:
        """Report progress for an open playback session.

        This is what feeds the listening statistics on the server;
        ``time_listened`` is the wall-clock time played since the last report.
        """
        self._request(
            "POST",
            f"/api/session/{session_id}/sync",
            json={
                "currentTime": current_time,
                "timeListened": time_listened,
                "duration": duration,
            },
        )

    def mark_finished(
        self, item_id: str, finished: bool = True, episode_id: str | None = None
    ) -> None:
        self._request(
            "PATCH", self._progress_path(item_id, episode_id), json={"isFinished": finished}
        )

    @staticmethod
    def _progress_path(item_id: str, episode_id: str | None = None) -> str:
        if episode_id:
            return f"/api/me/progress/{item_id}/{episode_id}"
        return f"/api/me/progress/{item_id}"

    def close_session(self, session_id: str, current_time: float | None = None) -> None:
        payload = {"currentTime": current_time} if current_time is not None else None
        try:
            self._request("POST", f"/api/session/{session_id}/close", json=payload)
        except ApiError as exc:
            log.info("Could not close playback session %s: %s", session_id, exc)

    # --- Bookmarks --------------------------------------------------------
    def add_bookmark(self, item_id: str, time: float, title: str = "") -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/me/item/{item_id}/bookmark",
            json={"time": int(time), "title": title},
        )

    def update_bookmark(self, item_id: str, time: float, title: str) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/api/me/item/{item_id}/bookmark",
            json={"time": int(time), "title": title},
        )

    def delete_bookmark(self, item_id: str, time: float) -> None:
        self._request("DELETE", f"/api/me/item/{item_id}/bookmark/{int(time)}")

    def bookmarks(self, item_id: str) -> list[Bookmark]:
        """Bookmarks of an item (taken from the user object), sorted by time."""
        user = self.fetch_me()
        marks = [
            Bookmark(b)
            for b in (user.get("bookmarks") or [])
            if isinstance(b, dict) and b.get("libraryItemId") == item_id
        ]
        marks.sort(key=lambda b: b.time)
        return marks

    # --- Editing / refreshing metadata ------------------------------------
    def update_media(self, item_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PATCH", f"/api/items/{item_id}/media", json={"metadata": metadata}
        )

    def scan_library(self, library_id: str) -> Any:
        """Trigger a full library scan so ABS re-reads all files (including
        embedded tags). Requires admin rights.

        The server answers immediately with 200 and keeps scanning in the
        background. (The single-item scan ``/api/items/<id>/scan`` only exists in
        ABS development mode, which is why the library scan is used here.)
        """
        return self._request("POST", f"/api/libraries/{library_id}/scan")

    # --- URLs (for VLC / downloads) ---------------------------------------
    def authed_url(self, relative_url: str) -> str:
        """Build a playable URL for a ``contentUrl`` returned by the server.

        A token is appended **only** when the resulting URL points at the
        configured Audiobookshelf host. Absolute URLs to other hosts (a CDN, a
        proxy, an attacker-controlled value in the API response) are returned
        untouched so the auth token never leaves our own server.
        """
        if not relative_url:
            return ""
        if urlhelp.is_same_origin(self.server_url, relative_url):
            url = (
                relative_url
                if relative_url.lower().startswith(("http://", "https://"))
                else urlhelp.join_base(self.server_url, relative_url)
            )
            if not self.token:
                return url
            return urlhelp.with_token(url, self.token)
        log.warning(
            "Not attaching auth token to foreign URL host %s",
            urlhelp.origin(relative_url)[1] or "?",
        )
        return relative_url

    def download_url(self, item_id: str) -> str:
        return self.authed_url(f"/api/items/{item_id}/download")

    def download_item(self, item_id: str, dest_path: str, progress_cb=None) -> str:
        """Download an item (file/zip). Returns the destination path.

        Uses the session's Authorization header rather than a token in the URL,
        so the token never ends up in a proxy or server access log.
        """
        return self._download(f"/api/items/{item_id}/download", dest_path, progress_cb)

    def download_audio_file(
        self, item_id: str, ino: str, dest_path: str, progress_cb=None
    ) -> str:
        """Download one audio file of an item, addressed by its inode.

        This is what offline playback is built on: the single files can be
        handed to the player as they are, while the ``/download`` endpoint
        returns a zip archive that nothing can play.
        """
        return self._download(
            f"/api/items/{item_id}/file/{ino}/download", dest_path, progress_cb
        )

    def _download(self, path: str, dest_path: str, progress_cb=None) -> str:
        """Stream a download to ``dest_path``.

        The data goes to a ``.part`` file that is renamed only once the
        download is complete, so an interrupted download can never be mistaken
        for a usable file.
        """
        self.ensure_fresh_token()
        url = urlhelp.join_base(self.server_url, path)
        partial = f"{dest_path}.part"
        for attempt in (1, 2):
            try:
                with self._session.get(url, stream=True, timeout=DEFAULT_TIMEOUT) as resp:
                    if resp.status_code == 401 and attempt == 1 and self.refresh_access_token():
                        continue
                    if resp.status_code >= 400:
                        raise ApiError(
                            _("Download failed (HTTP %d).") % resp.status_code,
                            resp.status_code,
                        )
                    total = int(resp.headers.get("Content-Length") or 0)
                    done = 0
                    with open(partial, "wb") as fh:
                        for chunk in resp.iter_content(chunk_size=1 << 16):
                            if chunk:
                                fh.write(chunk)
                                done += len(chunk)
                                if progress_cb and total:
                                    progress_cb(done, total)
                    os.replace(partial, dest_path)
                    return dest_path
            except requests.RequestException as exc:
                _remove_quietly(partial)
                raise ApiError(_("Network error during download: %s") % exc) from exc
            except OSError as exc:
                _remove_quietly(partial)
                raise ApiError(_("Could not write the downloaded file: %s") % exc) from exc
            except BaseException:
                _remove_quietly(partial)
                raise
        raise AuthExpiredError()

    # --- internal request helper ------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
        auth_required: bool = True,
        headers: dict[str, str] | None = None,
        allow_refresh: bool = True,
    ) -> Any:
        if auth_required:
            if not self.token:
                raise ApiError(_("Not signed in."), 401)
            if allow_refresh:
                self.ensure_fresh_token()
        url = urlhelp.join_base(self.server_url, path)
        if params:
            url = f"{url}?{urlencode(params)}"

        for attempt in (1, 2):
            try:
                resp = self._session.request(
                    method, url, json=json, headers=headers, timeout=DEFAULT_TIMEOUT
                )
            except requests.Timeout as exc:
                raise ApiError(_("The server did not respond in time.")) from exc
            except requests.ConnectionError as exc:
                raise ApiError(_("Cannot reach the server: %s") % exc) from exc
            except requests.RequestException as exc:
                raise ApiError(_("Network error: %s") % exc) from exc

            if resp.status_code == 401:
                if attempt == 1 and allow_refresh and auth_required and self.refresh_access_token():
                    continue
                log.info("Unauthorised response for %s %s", method, path)
                if not auth_required:
                    # /login and /auth/refresh: these credentials were rejected.
                    raise ApiError(_("Invalid username or password."), 401)
                raise AuthExpiredError()
            if resp.status_code == 403:
                raise ApiError(
                    _("Your account is not allowed to perform this action."), 403
                )
            if resp.status_code == 404:
                raise ApiError(_("The server does not know this address (404)."), 404)
            if resp.status_code >= 400:
                detail = truncate(resp.text, 200)
                log.warning("HTTP %s for %s %s: %s", resp.status_code, method, path, detail)
                message = (
                    _("Server error %(status)d: %(detail)s")
                    % {"status": resp.status_code, "detail": detail}
                    if detail
                    else _("Server error %d.") % resp.status_code
                )
                raise ApiError(message, resp.status_code)
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError:
                log.warning("Non-JSON response for %s %s", method, path)
                return {}
        raise AuthExpiredError()
