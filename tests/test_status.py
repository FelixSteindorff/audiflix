"""Tests for the download registry and the progress index."""

import audiflix.config as config
from audiflix.helpers import status


def test_download_registry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(status, "config_dir", lambda: tmp_path)

    reg = status.DownloadRegistry()
    book = tmp_path / "book.zip"
    book.write_text("x")

    assert reg.is_downloaded("a") is False
    reg.mark("a", str(book))
    assert reg.is_downloaded("a") is True
    assert reg.path_for("a") == str(book)

    # persistence: a new instance reads the file again
    reg2 = status.DownloadRegistry()
    assert reg2.is_downloaded("a") is True

    reg2.remove("a")
    assert reg2.is_downloaded("a") is False


def test_download_registry_missing_file_is_not_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "config_dir", lambda: tmp_path)
    reg = status.DownloadRegistry()
    reg.mark("b", str(tmp_path / "missing.zip"))
    assert reg.is_downloaded("b") is False


def test_progress_index():
    user = {
        "mediaProgress": [
            {"libraryItemId": "1", "progress": 0.5, "currentTime": 120, "isFinished": False},
            {"libraryItemId": "2", "progress": 1.0, "currentTime": 999, "isFinished": True},
        ]
    }
    idx = status.ProgressIndex(user)
    assert idx.progress_for("1") == 0.5
    assert idx.current_time("1") == 120
    assert idx.is_finished("1") is False
    assert idx.is_finished("2") is True
    assert idx.progress_for("unknown") == 0.0


def test_progress_index_keeps_podcast_episodes_apart():
    """Every episode of a podcast carries the same libraryItemId."""
    user = {
        "mediaProgress": [
            {"libraryItemId": "p", "episodeId": "e1", "progress": 1.0, "isFinished": True},
            {"libraryItemId": "p", "episodeId": "e2", "progress": 0.25, "isFinished": False},
        ]
    }
    idx = status.ProgressIndex(user)
    assert idx.is_finished("p", "e1") is True
    assert idx.progress_for("p", "e2") == 0.25
    assert idx.is_finished("p", "e2") is False
    # The podcast itself has no progress of its own.
    assert idx.progress_for("p") == 0.0
