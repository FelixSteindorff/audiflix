"""Tests for URL building, auth handling and filters of the API client (no network)."""

import time

import pytest

from audiflix.api.client import (
    FINISHED_FILTER,
    ApiError,
    AudiobookshelfClient,
    AuthExpiredError,
    decode_jwt_expiry,
)
from audiflix.api.models import LibraryItem, Series


def test_finished_filter_is_base64():
    assert FINISHED_FILTER == "progress.ZmluaXNoZWQ="


def test_authed_url_appends_token_relative():
    client = AudiobookshelfClient("https://abs.example.com/", token="abc")
    url = client.authed_url("/api/items/42/file/9")
    assert url == "https://abs.example.com/api/items/42/file/9?token=abc"


def test_authed_url_keeps_existing_query():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    url = client.authed_url("/hls/abc/index.m3u8?foo=bar")
    assert url.endswith("&token=t")
    assert "foo=bar" in url


def test_authed_url_allows_absolute_url_on_own_host():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    url = client.authed_url("https://abs.example.com/api/items/1/file/2")
    assert url == "https://abs.example.com/api/items/1/file/2?token=t"


def test_authed_url_never_sends_token_to_foreign_host():
    """A CDN URL in the API response must not receive our auth token."""
    client = AudiobookshelfClient("https://abs.example.com", token="secret")
    url = client.authed_url("https://cdn.evil.example/a.m4b")
    assert url == "https://cdn.evil.example/a.m4b"
    assert "secret" not in url


def test_authed_url_treats_other_port_as_foreign():
    client = AudiobookshelfClient("https://abs.example.com", token="secret")
    assert "secret" not in client.authed_url("https://abs.example.com:8443/file")


def test_authed_url_without_token_is_plain():
    client = AudiobookshelfClient("https://abs.example.com")
    assert client.authed_url("/api/x") == "https://abs.example.com/api/x"


def test_authed_url_empty_input():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    assert client.authed_url("") == ""


def test_download_url():
    client = AudiobookshelfClient("https://abs.example.com", token="zzz")
    assert (
        client.download_url("99")
        == "https://abs.example.com/api/items/99/download?token=zzz"
    )


def test_server_url_trailing_slash_stripped():
    client = AudiobookshelfClient("https://abs.example.com///")
    assert client.server_url == "https://abs.example.com"


def test_library_item_defensive_accessors():
    item = LibraryItem({})
    assert item.title == "(untitled)"
    assert item.author == ""
    assert item.duration == 0.0
    assert item.author_ids == []


# --- Authentication --------------------------------------------------------

def _make_jwt(exp: float) -> str:
    import base64
    import json

    def segment(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{segment({'alg': 'HS256'})}.{segment({'exp': exp})}.signature"


def test_decode_jwt_expiry():
    token = _make_jwt(1893456000)
    assert decode_jwt_expiry(token) == 1893456000


def test_decode_jwt_expiry_rejects_garbage():
    assert decode_jwt_expiry("not-a-jwt") is None
    assert decode_jwt_expiry("") is None
    assert decode_jwt_expiry("a.b.c") is None


def test_login_prefers_access_token_and_keeps_refresh_token():
    client = AudiobookshelfClient("https://abs.example.com")
    seen = {}

    def fake(method, path, params=None, json=None, auth_required=True,
             headers=None, allow_refresh=True):
        seen["path"] = path
        seen["headers"] = headers
        return {
            "user": {"accessToken": "access-1", "token": "legacy"},
            "refreshToken": "refresh-1",
        }

    client._request = fake
    token = client.login("felix", "pw")
    assert token == "access-1"
    assert client.refresh_token == "refresh-1"
    assert seen["path"] == "/login"
    assert seen["headers"] == {"x-return-tokens": "true"}


def test_login_falls_back_to_legacy_token():
    """Audiobookshelf before 2.26 only returns user.token."""
    client = AudiobookshelfClient("https://abs.example.com")
    client._request = lambda *a, **k: {"user": {"token": "legacy-token"}}
    assert client.login("felix", "pw") == "legacy-token"
    assert client.refresh_token is None


def test_login_without_token_raises():
    client = AudiobookshelfClient("https://abs.example.com")
    client._request = lambda *a, **k: {"user": {}}
    with pytest.raises(ApiError):
        client.login("felix", "pw")


def test_refresh_uses_refresh_header_and_stores_new_token():
    client = AudiobookshelfClient("https://abs.example.com", token="old", refresh_token="r1")
    seen = {}

    def fake(method, path, params=None, json=None, auth_required=True,
             headers=None, allow_refresh=True):
        seen["path"] = path
        seen["headers"] = headers
        return {"user": {"accessToken": "new-token"}, "refreshToken": "r2"}

    client._request = fake
    assert client.refresh_access_token() is True
    assert seen["path"] == "/auth/refresh"
    assert seen["headers"] == {"x-refresh-token": "r1"}
    assert client.token == "new-token"
    assert client.refresh_token == "r2"


def test_refresh_without_refresh_token_fails_fast():
    client = AudiobookshelfClient("https://abs.example.com", token="old")
    assert client.refresh_access_token() is False


def test_refresh_gives_up_on_unauthorised_refresh_token():
    client = AudiobookshelfClient("https://abs.example.com", token="old", refresh_token="r1")

    def fake(*args, **kwargs):
        raise ApiError("nope", 401)

    client._request = fake
    assert client.refresh_access_token() is False
    assert client.refresh_token is None


def test_tokens_changed_callback_fires_on_refresh():
    seen = []
    client = AudiobookshelfClient(
        "https://abs.example.com",
        token="old",
        refresh_token="r1",
        on_tokens_changed=lambda access, refresh: seen.append((access, refresh)),
    )
    client._request = lambda *a, **k: {"user": {"accessToken": "new"}, "refreshToken": "r2"}
    client.refresh_access_token()
    assert seen == [("new", "r2")]


def test_expiring_token_triggers_proactive_refresh():
    soon = _make_jwt(time.time() + 5)
    client = AudiobookshelfClient("https://abs.example.com", token=soon, refresh_token="r1")
    calls = []
    client.refresh_access_token = lambda: calls.append(1) or True
    client.ensure_fresh_token()
    assert calls == [1]


def test_valid_token_is_not_refreshed():
    later = _make_jwt(time.time() + 3600)
    client = AudiobookshelfClient("https://abs.example.com", token=later, refresh_token="r1")
    calls = []
    client.refresh_access_token = lambda: calls.append(1) or True
    client.ensure_fresh_token()
    assert calls == []


def test_request_without_token_raises_auth_error():
    client = AudiobookshelfClient("https://abs.example.com")
    with pytest.raises(ApiError) as excinfo:
        client.libraries()
    assert excinfo.value.status == 401


def test_auth_expired_error_is_an_api_error():
    error = AuthExpiredError()
    assert isinstance(error, ApiError)
    assert error.status == 401
    assert error.is_auth_error


# --- Endpoints -------------------------------------------------------------

def _capture_client():
    """Client whose _request is captured, logging (method, path, json)."""
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    calls = []

    def fake_request(method, path, params=None, json=None, auth_required=True,
                     headers=None, allow_refresh=True):
        calls.append((method, path, json))
        return {}

    client._request = fake_request
    return client, calls


def test_add_bookmark_uses_item_endpoint():
    client, calls = _capture_client()
    client.add_bookmark("item42", 95.7, "Exciting bit")
    assert calls == [
        ("POST", "/api/me/item/item42/bookmark", {"time": 95, "title": "Exciting bit"})
    ]


def test_update_and_delete_bookmark_endpoints():
    client, calls = _capture_client()
    client.update_bookmark("item42", 95, "New")
    client.delete_bookmark("item42", 95)
    assert calls[0] == ("PATCH", "/api/me/item/item42/bookmark", {"time": 95, "title": "New"})
    assert calls[1] == ("DELETE", "/api/me/item/item42/bookmark/95", None)


def test_bookmarks_filters_and_sorts_by_item():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    client._request = lambda *a, **k: {
        "bookmarks": [
            {"libraryItemId": "a", "time": 200, "title": "Late"},
            {"libraryItemId": "b", "time": 10, "title": "Other book"},
            {"libraryItemId": "a", "time": 50, "title": "Early"},
        ]
    }
    marks = client.bookmarks("a")
    assert [m.title for m in marks] == ["Early", "Late"]


def test_progress_path_with_and_without_episode():
    client, calls = _capture_client()
    client.sync_progress("item1", 30.0, 60.0)
    client.sync_progress("item1", 30.0, 60.0, episode_id="ep9")
    assert calls[0][1] == "/api/me/progress/item1"
    assert calls[1][1] == "/api/me/progress/item1/ep9"


def test_sync_progress_clamps_progress_value():
    client, calls = _capture_client()
    client.sync_progress("item1", 120.0, 60.0)
    assert calls[0][2]["progress"] == 1.0


def test_mark_finished_payload():
    client, calls = _capture_client()
    client.mark_finished("item1")
    assert calls == [("PATCH", "/api/me/progress/item1", {"isFinished": True})]


def test_play_item_sends_client_info():
    client, calls = _capture_client()
    client.play_item("item1")
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/api/items/item1/play")
    assert body["deviceInfo"]["clientName"] == "Audiflix"
    assert body["deviceInfo"]["clientVersion"]


def test_play_item_with_episode_appends_episode_id():
    client, calls = _capture_client()
    client.play_item("item1", "ep2")
    assert calls[0][1] == "/api/items/item1/play/ep2"


def test_series_parses_results_and_books():
    client, _calls = _capture_client()
    client._request = lambda *a, **k: {
        "results": [
            {"id": "s1", "name": "The Series", "books": [
                {"id": "b1", "media": {"metadata": {"title": "Book 1"}}},
                {"id": "b2", "media": {"metadata": {"title": "Book 2"}}},
            ]},
        ]
    }
    series = client.series("lib1")
    assert len(series) == 1
    assert series[0].name == "The Series"
    assert series[0].num_books == 2
    assert [b.title for b in series[0].books] == ["Book 1", "Book 2"]


def test_check_new_episodes_endpoint_and_parsing():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    seen = {}

    def fake(method, path, params=None, json=None, auth_required=True,
             headers=None, allow_refresh=True):
        seen["method"], seen["path"], seen["params"] = method, path, params
        return {"episodes": [{"title": "New 1"}, {"title": "New 2"}]}

    client._request = fake
    episodes = client.check_new_episodes("pod1", limit=5)
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/podcasts/pod1/checknew"
    assert seen["params"] == {"limit": 5}
    assert len(episodes) == 2


def test_search_podcasts_uses_singular_path():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    seen = {}

    def fake(method, path, params=None, json=None, auth_required=True,
             headers=None, allow_refresh=True):
        seen["path"], seen["params"] = path, params
        return []

    client._request = fake
    client.search_podcasts("serial")
    assert seen["path"] == "/api/search/podcast"
    assert seen["params"] == {"term": "serial"}


def test_set_auto_download_body():
    client, calls = _capture_client()
    client.set_auto_download("pod1", True)
    assert calls == [("PATCH", "/api/items/pod1/media", {"autoDownloadEpisodes": True})]


def test_add_podcast_payload_includes_path():
    client, calls = _capture_client()
    client.add_podcast("lib1", "fold1", "/podcasts/Serial", {"title": "Serial"})
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/api/podcasts")
    assert body["libraryId"] == "lib1"
    assert body["folderId"] == "fold1"
    assert body["path"] == "/podcasts/Serial"
    assert body["media"]["metadata"]["title"] == "Serial"


def test_auto_download_episodes_property():
    on = LibraryItem({"media": {"autoDownloadEpisodes": True}})
    off = LibraryItem({"media": {}})
    assert on.auto_download_episodes is True
    assert off.auto_download_episodes is False


def test_series_paginates():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    pages = {
        0: {"results": [{"id": f"s{i}", "name": str(i)} for i in range(200)], "total": 250},
        1: {"results": [{"id": f"s{i}", "name": str(i)} for i in range(200, 250)], "total": 250},
    }
    seen = []

    def fake(method, path, params=None, json=None, auth_required=True,
             headers=None, allow_refresh=True):
        seen.append(params)
        return pages[params["page"]]

    client._request = fake
    series = client.series("lib1", page_size=200)
    assert len(series) == 250
    assert [p["page"] for p in seen] == [0, 1]
    assert all(p["limit"] == 200 for p in seen)


def test_series_all_dedupes_across_libraries():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    client.series = lambda lib_id: (
        [Series({"id": "s1", "name": "X"})]
        if lib_id == "a"
        else [Series({"id": "s1", "name": "X"}), Series({"id": "s2", "name": "Y"})]
    )
    result = client.series_all(["a", "b"])
    assert sorted(s.id for s in result) == ["s1", "s2"]


def test_search_library_collects_books_and_podcasts():
    client = AudiobookshelfClient("https://abs.example.com", token="t")
    client._request = lambda *a, **k: {
        "book": [{"libraryItem": {"id": "b1"}}],
        "podcast": [{"libraryItem": {"id": "p1"}}],
    }
    results = client.search_library("lib1", "query")
    assert [item.id for item in results] == ["b1", "p1"]
