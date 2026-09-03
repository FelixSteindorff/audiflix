"""Tests for the VLC download tool - version resolution, checksums, extraction.

Nothing here touches the network: every remote lookup is stubbed. What is being
protected is the promise that a released Audiflix records exactly which VLC it
contains and refuses to build from an archive that does not match.
"""

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

fetch_vlc = pytest.importorskip("fetch_vlc")

LISTING = """
<html><body>
<a href="vlc-3.0.21-win64.zip">vlc-3.0.21-win64.zip</a>
<a href="vlc-3.0.23-win64.7z">vlc-3.0.23-win64.7z</a>
<a href="vlc-3.0.23-win64.zip">vlc-3.0.23-win64.zip</a>
<a href="vlc-3.0.23-win64.zip.sha256">vlc-3.0.23-win64.zip.sha256</a>
<a href="vlc-3.0.9-win64.zip">vlc-3.0.9-win64.zip</a>
</body></html>
"""


# --- URLs and versions -----------------------------------------------------

def test_archive_name_and_url():
    assert fetch_vlc.archive_name("3.0.23") == "vlc-3.0.23-win64.zip"
    assert fetch_vlc.archive_url("3.0.23") == (
        "https://download.videolan.org/pub/videolan/vlc/3.0.23/win64/vlc-3.0.23-win64.zip"
    )


def test_latest_version_is_resolved_numerically(monkeypatch):
    """3.0.9 must not beat 3.0.23 - a plain string sort would get this wrong."""
    monkeypatch.setattr(fetch_vlc, "_get", lambda url: LISTING.encode())
    assert fetch_vlc.resolve_latest_version() == "3.0.23"


def test_empty_listing_is_an_error(monkeypatch):
    monkeypatch.setattr(fetch_vlc, "_get", lambda url: b"<html></html>")
    with pytest.raises(fetch_vlc.VlcFetchError):
        fetch_vlc.resolve_latest_version()


def test_official_checksum_is_parsed(monkeypatch):
    digest = "992d19dbd0b8a7cde9167d2f7780b1ef6f92acc8a71acfa736101a21f35181e1"
    monkeypatch.setattr(
        fetch_vlc, "_get", lambda url: f"{digest} *vlc-3.0.23-win64.zip\n".encode()
    )
    assert fetch_vlc.official_sha256("3.0.23") == digest


def test_unparsable_checksum_file_is_an_error(monkeypatch):
    monkeypatch.setattr(fetch_vlc, "_get", lambda url: b"404 not found")
    with pytest.raises(fetch_vlc.VlcFetchError):
        fetch_vlc.official_sha256("9.9.9")


# --- Lock file -------------------------------------------------------------

def test_lock_roundtrip(tmp_path):
    lock = tmp_path / "vlc.lock.json"
    fetch_vlc.write_lock("3.0.23", "b" * 64, lock)
    data = fetch_vlc.read_lock(lock)
    assert data["version"] == "3.0.23"
    assert data["sha256"] == "b" * 64
    assert data["url"].endswith("vlc-3.0.23-win64.zip")


def test_missing_lock_file_explains_the_fix(tmp_path):
    with pytest.raises(fetch_vlc.VlcFetchError) as excinfo:
        fetch_vlc.read_lock(tmp_path / "absent.json")
    assert "--update-lock" in str(excinfo.value)


def test_incomplete_lock_file_is_rejected(tmp_path):
    lock = tmp_path / "vlc.lock.json"
    lock.write_text(json.dumps({"version": "3.0.23"}), encoding="utf-8")
    with pytest.raises(fetch_vlc.VlcFetchError):
        fetch_vlc.read_lock(lock)


def test_the_committed_lock_file_is_valid():
    """The pin that release builds depend on must always be readable."""
    data = fetch_vlc.read_lock(ROOT / "vlc.lock.json")
    assert len(data["sha256"]) == 64
    assert data["version"].count(".") == 2


# --- Download verification -------------------------------------------------

class FakeResponse(io.BytesIO):
    """Just enough of an HTTP response for download_archive()."""

    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}


def test_a_cached_archive_with_a_wrong_checksum_is_replaced(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    stale = cache / fetch_vlc.archive_name("3.0.23")
    stale.write_bytes(b"stale content")

    downloads = []

    def fake_urlopen(request, timeout=0):
        downloads.append(request.full_url)
        return FakeResponse(b"fresh content")

    monkeypatch.setattr(fetch_vlc.urllib.request, "urlopen", fake_urlopen)
    expected = fetch_vlc.hashlib.sha256(b"fresh content").hexdigest()
    result = fetch_vlc.download_archive("3.0.23", cache, expected)

    assert downloads, "a stale cache entry must trigger a fresh download"
    assert result.read_bytes() == b"fresh content"


def test_a_matching_cached_archive_is_reused(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    cached = cache / fetch_vlc.archive_name("3.0.23")
    cached.write_bytes(b"good content")

    def explode(*args, **kwargs):
        raise AssertionError("must not download when the cache is valid")

    monkeypatch.setattr(fetch_vlc.urllib.request, "urlopen", explode)
    expected = fetch_vlc.hashlib.sha256(b"good content").hexdigest()
    assert fetch_vlc.download_archive("3.0.23", cache, expected) == cached


def test_a_corrupted_download_is_discarded(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(
        fetch_vlc.urllib.request, "urlopen",
        lambda request, timeout=0: FakeResponse(b"tampered"),
    )
    with pytest.raises(fetch_vlc.VlcFetchError) as excinfo:
        fetch_vlc.download_archive("3.0.23", cache, "a" * 64)
    assert "Checksum mismatch" in str(excinfo.value)
    assert not list(cache.glob("*.zip")), "a bad download must not be kept"


# --- Extraction ------------------------------------------------------------

def build_fake_archive(path: Path, version: str = "3.0.23") -> Path:
    prefix = f"vlc-{version}/"
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(prefix + "libvlc.dll", b"core")
        bundle.writestr(prefix + "libvlccore.dll", b"core")
        bundle.writestr(prefix + "vlc-cache-gen.exe", b"cachegen")
        bundle.writestr(prefix + "COPYING.txt", b"GPL text")
        bundle.writestr(prefix + "AUTHORS.txt", b"authors")
        bundle.writestr(prefix + "plugins/codec/libavcodec_plugin.dll", b"plugin")
        bundle.writestr(prefix + "plugins/access/libhttp_plugin.dll", b"plugin")
        bundle.writestr(prefix + "lua/playlist/anevia.luac", b"lua")
        bundle.writestr(prefix + "hrtfs/dodeca_and_7channel_3DSL_HRTF.sofa", b"hrtf")
        # Everything below must be skipped.
        bundle.writestr(prefix + "vlc.exe", b"gui player")
        bundle.writestr(prefix + "axvlc.dll", b"activex")
        bundle.writestr(prefix + "npvlc.dll", b"npapi")
        bundle.writestr(prefix + "locale/de/LC_MESSAGES/vlc.mo", b"catalog")
        bundle.writestr(prefix + "skins/default.vlt", b"skin")
    return path


def test_extract_keeps_the_runtime_and_drops_the_gui(tmp_path):
    archive = build_fake_archive(tmp_path / "vlc.zip")
    dest = tmp_path / "out"
    summary = fetch_vlc.extract_runtime(archive, "3.0.23", dest)

    assert (dest / "libvlc.dll").is_file()
    assert (dest / "libvlccore.dll").is_file()
    assert (dest / "plugins" / "codec" / "libavcodec_plugin.dll").is_file()
    assert (dest / "lua" / "playlist" / "anevia.luac").is_file()
    assert (dest / "hrtfs").is_dir()
    assert (dest / "licenses" / "COPYING.txt").is_file()

    assert not (dest / "vlc.exe").exists()
    assert not (dest / "axvlc.dll").exists()
    assert not (dest / "npvlc.dll").exists()
    assert not (dest / "locale").exists()
    assert not (dest / "skins").exists()

    assert summary["files"] == 9
    assert summary["bytes"] > 0


def test_extract_replaces_an_existing_directory(tmp_path):
    archive = build_fake_archive(tmp_path / "vlc.zip")
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "leftover.dll").write_bytes(b"from an older build")
    fetch_vlc.extract_runtime(archive, "3.0.23", dest)
    assert not (dest / "leftover.dll").exists()


def test_extract_rejects_an_archive_without_the_expected_layout(tmp_path):
    archive = tmp_path / "vlc.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("something-else/readme.txt", b"nope")
    with pytest.raises(fetch_vlc.VlcFetchError):
        fetch_vlc.extract_runtime(archive, "3.0.23", tmp_path / "out")


def test_extract_rejects_an_archive_without_plugins(tmp_path):
    archive = tmp_path / "vlc.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("vlc-3.0.23/libvlc.dll", b"core")
        bundle.writestr("vlc-3.0.23/libvlccore.dll", b"core")
    with pytest.raises(fetch_vlc.VlcFetchError) as excinfo:
        fetch_vlc.extract_runtime(archive, "3.0.23", tmp_path / "out")
    assert "plugins" in str(excinfo.value)


# --- Build metadata --------------------------------------------------------

def test_metadata_records_version_url_and_checksum(tmp_path):
    target = tmp_path / "vlc-version.json"
    fetch_vlc.write_metadata(
        target, "3.0.23", "c" * 64, {"files": 469, "bytes": 143_477_523}, "vlc.lock.json"
    )
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["vlc_version"] == "3.0.23"
    assert data["sha256"] == "c" * 64
    assert data["version_source"] == "vlc.lock.json"
    assert data["extracted_files"] == 469
    assert data["url"].endswith("vlc-3.0.23-win64.zip")
    assert data["fetched_at"]


def test_metadata_matches_the_lock_file_after_a_locked_build():
    """If a build/vlc-version.json exists it must agree with the pin."""
    metadata_path = ROOT / "build" / "vlc-version.json"
    if not metadata_path.is_file():
        pytest.skip("no build metadata (run: python tools/fetch_vlc.py --use-lock)")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    lock = fetch_vlc.read_lock(ROOT / "vlc.lock.json")
    assert metadata["vlc_version"] == lock["version"]
    assert metadata["sha256"] == lock["sha256"]
