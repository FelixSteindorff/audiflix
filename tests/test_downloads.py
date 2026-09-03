"""Tests for downloaded titles: the manifest, the registry and the download."""

from pathlib import Path

import pytest

import audiflix.helpers.status as status_module
from audiflix.api.models import LibraryItem
from audiflix.helpers import actions, downloads
from audiflix.helpers.status import DownloadRegistry


def _write_download(folder: Path, files=("001.mp3", "002.mp3")) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    tracks = []
    offset = 0.0
    for index, name in enumerate(files):
        (folder / name).write_bytes(b"audio")
        tracks.append(
            {"file": name, "ino": str(index), "start_offset": offset, "duration": 100.0}
        )
        offset += 100.0
    downloads.write_manifest(
        folder,
        item_id="li_1",
        title="A Book",
        duration=offset,
        tracks=tracks,
        chapters=[{"start": 0.0, "end": 100.0, "title": "One"}],
    )
    return folder


def test_manifest_roundtrip(tmp_path):
    folder = _write_download(tmp_path / "book")
    manifest = downloads.read_manifest(folder)
    assert manifest["item_id"] == "li_1"
    assert manifest["duration"] == 200.0
    assert [t["file"] for t in manifest["tracks"]] == ["001.mp3", "002.mp3"]
    assert manifest["chapters"][0]["title"] == "One"
    assert downloads.is_complete(folder) is True


def test_local_tracks_point_at_the_files(tmp_path):
    folder = _write_download(tmp_path / "book")
    tracks = downloads.local_tracks(folder)
    assert len(tracks) == 2
    assert tracks[0]["local"] is True
    assert Path(tracks[0]["url"]).exists()
    assert tracks[1]["start_offset"] == 100.0


def test_a_missing_file_makes_the_download_unusable(tmp_path):
    """Half a book is worse than streaming it, so nothing is offered at all."""
    folder = _write_download(tmp_path / "book")
    (folder / "002.mp3").unlink()
    assert downloads.is_complete(folder) is False
    assert downloads.local_tracks(folder) == []


def test_missing_manifest_is_not_an_error(tmp_path):
    assert downloads.read_manifest(tmp_path) is None
    assert downloads.local_tracks(tmp_path) == []
    assert downloads.is_complete(tmp_path) is False


def test_broken_manifest_is_ignored(tmp_path):
    downloads.manifest_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert downloads.read_manifest(tmp_path) is None


def test_offline_position_is_remembered_until_it_is_synced(tmp_path):
    folder = _write_download(tmp_path / "book")
    assert downloads.pending_position(folder) is None

    downloads.update_position(folder, 123.0, synced=False)
    assert downloads.pending_position(folder) == 123.0

    downloads.update_position(folder, 123.0, synced=True)
    assert downloads.pending_position(folder) is None
    # The position itself stays, so playback can resume there while offline.
    assert downloads.read_manifest(folder)["position"] == 123.0


def test_track_file_names_keep_the_order_visible():
    assert downloads.track_file_name(0, ".m4b") == "001.m4b"
    assert downloads.track_file_name(11, "mp3") == "012mp3"


# --- registry ---------------------------------------------------------------

@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(status_module, "config_dir", lambda: tmp_path)
    return DownloadRegistry()


def test_registry_records_a_playable_folder(registry, tmp_path):
    folder = _write_download(tmp_path / "book")
    registry.mark_folder("li_1", str(folder))
    assert registry.is_downloaded("li_1") is True
    assert registry.is_playable_offline("li_1") is True
    assert len(registry.local_tracks("li_1")) == 2
    assert registry.manifest("li_1")["title"] == "A Book"


def test_registry_still_understands_a_legacy_zip(registry, tmp_path):
    """Audiflix < 0.3 stored a zip archive; it marks the title as downloaded
    but cannot be played."""
    archive = tmp_path / "Book.zip"
    archive.write_bytes(b"zip")
    registry.mark("li_2", str(archive))
    assert registry.is_downloaded("li_2") is True
    assert registry.is_playable_offline("li_2") is False
    assert registry.local_tracks("li_2") == []


def test_registry_deletes_the_files(registry, tmp_path):
    folder = _write_download(tmp_path / "book")
    registry.mark_folder("li_1", str(folder))
    assert registry.delete_files("li_1") is True
    assert not folder.exists()
    assert registry.is_downloaded("li_1") is False


def test_registry_collects_pending_offline_positions(registry, tmp_path):
    folder = _write_download(tmp_path / "book")
    registry.mark_folder("li_1", str(folder))
    registry.record_offline_position("li_1", 42.0)
    assert registry.pending_positions() == {"li_1": 42.0}

    registry.clear_offline_position("li_1", 42.0)
    assert registry.pending_positions() == {}


# --- the download itself -----------------------------------------------------

class _FakeClient:
    """Serves one expanded item and writes a byte per audio file."""

    def __init__(self, item):
        self._item = item
        self.requested: list[str] = []

    def item(self, item_id, expanded=True):
        return self._item

    def download_audio_file(self, item_id, ino, dest_path, progress_cb=None):
        self.requested.append(ino)
        Path(dest_path).write_bytes(b"audio")
        if progress_cb:
            progress_cb(100, 100)
        return dest_path


def _book(audio_files=2):
    return LibraryItem({
        "id": "li_1",
        "media": {
            "metadata": {"title": "A Book"},
            "duration": 200.0,
            "chapters": [{"start": 0.0, "end": 200.0, "title": "One"}],
            "audioFiles": [
                {
                    "ino": f"ino{i}",
                    "index": i + 1,
                    "duration": 100.0,
                    "metadata": {"filename": f"track{i}.m4b", "ext": ".m4b"},
                }
                for i in range(audio_files)
            ],
        },
    })


def test_download_fetches_every_file_and_writes_a_manifest(registry, tmp_path):
    item = _book()
    client = _FakeClient(item)
    percentages: list[int] = []

    message = actions.download(
        client, item, registry, str(tmp_path / "downloads"),
        progress_cb=lambda done, total: percentages.append(done),
    )

    assert client.requested == ["ino0", "ino1"]
    assert "A Book" in message
    assert registry.is_playable_offline("li_1") is True
    tracks = registry.local_tracks("li_1")
    assert [Path(t["url"]).name for t in tracks] == ["001.m4b", "002.m4b"]
    assert tracks[1]["start_offset"] == 100.0
    assert registry.manifest("li_1")["chapters"][0]["title"] == "One"
    # Progress is reported across the whole title, not per file.
    assert percentages == [50, 100]


def test_download_without_audio_files_is_reported(registry, tmp_path):
    item = _book(audio_files=0)
    with pytest.raises(actions.DownloadError):
        actions.download(_FakeClient(item), item, registry, str(tmp_path))
    assert registry.is_downloaded("li_1") is False


def test_remove_download_reports_what_happened(registry, tmp_path):
    item = _book()
    actions.download(_FakeClient(item), item, registry, str(tmp_path / "downloads"))
    assert "deleted" in actions.remove_download(item, registry)
    assert registry.is_downloaded("li_1") is False
    assert "not downloaded" in actions.remove_download(item, registry)


def test_two_books_with_the_same_title_get_their_own_folders(tmp_path):
    """A library can hold several editions of one work."""
    first = downloads.folder_for(tmp_path, "A Book", "li_1")
    _write_download(first)
    assert downloads.read_manifest(first)["item_id"] == "li_1"

    second = downloads.folder_for(tmp_path, "A Book", "li_2")
    assert second != first
    assert "li_2" in second.name

    # The same item keeps its own folder, so downloading it again replaces it.
    assert downloads.folder_for(tmp_path, "A Book", "li_1") == first
