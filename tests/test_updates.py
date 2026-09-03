"""Tests for the update check and the diagnostics report."""

from audiflix import updates


def test_parse_version_reads_the_numbers():
    assert updates.parse_version("v1.2.3") == (1, 2, 3)
    assert updates.parse_version("0.2.0") == (0, 2, 0)
    assert updates.parse_version("1.10") == (1, 10)
    assert updates.parse_version("nonsense") == (0,)


def test_is_newer_compares_numerically():
    assert updates.is_newer("v0.10.0", "0.9.0") is True
    assert updates.is_newer("0.2.0", "0.2.0") is False
    assert updates.is_newer("0.1.0", "0.2.0") is False
    # A pre-release compares as the release it precedes, which is close enough
    # for "is there something newer than what I run".
    assert updates.is_newer("0.3.0-rc1", "0.2.0") is True


class _Response:
    def __init__(self, status=200, payload=None, text="{}"):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_latest_release_reads_the_tag(monkeypatch):
    monkeypatch.setattr(
        updates.requests, "get",
        lambda *a, **kw: _Response(payload={
            "tag_name": "v9.9.9", "html_url": "https://example/release", "body": "notes",
        }),
    )
    release = updates.latest_release()
    assert release["version"] == "v9.9.9"
    assert release["url"] == "https://example/release"


def test_a_failing_request_is_reported(monkeypatch):
    def boom(*args, **kwargs):
        raise updates.requests.RequestException("no network")

    monkeypatch.setattr(updates.requests, "get", boom)
    try:
        updates.latest_release()
    except updates.UpdateCheckError as exc:
        assert "no network" in str(exc)
    else:  # pragma: no cover - the call must not succeed
        raise AssertionError("expected an UpdateCheckError")


def test_a_bad_status_is_reported(monkeypatch):
    monkeypatch.setattr(updates.requests, "get", lambda *a, **kw: _Response(status=503))
    try:
        updates.latest_release()
    except updates.UpdateCheckError as exc:
        assert "503" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected an UpdateCheckError")


def test_diagnostics_carry_no_personal_data():
    report = updates.diagnostics(
        server_url="https://books.example",
        server_version="2.26.0",
        vlc_version="3.0.21",
        keyring_backend="WinVaultKeyring",
        speech_available=True,
        language="de",
    )
    assert "Audiflix" in report
    assert "3.0.21" in report
    assert "2.26.0" in report
    # The address of a private server is nobody's business but its owner's.
    assert "books.example" not in report
