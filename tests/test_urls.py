"""Tests for server URL validation and same-origin checks."""

import pytest

from audiflix.helpers import urls


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abs.example.com", "https://abs.example.com"),
        ("https://abs.example.com/", "https://abs.example.com"),
        ("https://abs.example.com:443", "https://abs.example.com"),
        ("http://localhost:13378", "http://localhost:13378"),
        ("http://localhost:80", "http://localhost"),
        ("  https://abs.example.com/audiobookshelf/  ", "https://abs.example.com/audiobookshelf"),
        ("HTTPS://ABS.example.com", "https://abs.example.com"),
        ("https://[::1]:8080", "https://[::1]:8080"),
    ],
)
def test_normalize_server_url(raw, expected):
    assert urls.normalize_server_url(raw) == expected


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("ftp://abs.example.com", "scheme"),
        ("https://", "host"),
        ("https://abs.example.com:notaport", "port"),
        ("https://abs.example.com/?a=b", "extra"),
    ],
)
def test_normalize_server_url_rejects(raw, reason):
    with pytest.raises(urls.InvalidServerUrl) as excinfo:
        urls.normalize_server_url(raw)
    assert str(excinfo.value) == reason


def test_is_plain_http():
    assert urls.is_plain_http("http://abs.example.com") is True
    assert urls.is_plain_http("https://abs.example.com") is False


def test_is_loopback():
    assert urls.is_loopback("http://localhost:13378") is True
    assert urls.is_loopback("http://127.0.0.1") is True
    assert urls.is_loopback("https://abs.example.com") is False


def test_same_origin_for_relative_urls():
    assert urls.is_same_origin("https://abs.example.com", "/api/items/1") is True


def test_same_origin_matches_default_port():
    assert urls.is_same_origin("https://abs.example.com", "https://abs.example.com:443/x") is True


def test_same_origin_rejects_other_host_scheme_or_port():
    base = "https://abs.example.com"
    assert urls.is_same_origin(base, "https://cdn.example.net/x") is False
    assert urls.is_same_origin(base, "http://abs.example.com/x") is False
    assert urls.is_same_origin(base, "https://abs.example.com:8443/x") is False


def test_same_origin_is_case_insensitive_for_host():
    assert urls.is_same_origin("https://ABS.example.com", "https://abs.EXAMPLE.com/x") is True


def test_join_base_handles_missing_slash():
    assert urls.join_base("https://abs.example.com/", "api/x") == "https://abs.example.com/api/x"
    assert urls.join_base("https://abs.example.com", "/api/x") == "https://abs.example.com/api/x"


def test_with_token_picks_the_right_separator():
    assert urls.with_token("https://h/x", "t") == "https://h/x?token=t"
    assert urls.with_token("https://h/x?a=b", "t") == "https://h/x?a=b&token=t"


def test_with_token_quotes_special_characters():
    assert urls.with_token("https://h/x", "a b&c") == "https://h/x?token=a%20b%26c"


def test_redact_token_hides_the_secret():
    redacted = urls.redact_token("https://h/x?token=supersecret")
    assert "supersecret" not in redacted
    assert "token=<redacted>" in redacted
