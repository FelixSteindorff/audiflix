"""Persistence and conflict handling must also work without wx or a server."""

from concurrent.futures import ThreadPoolExecutor

from audiflix.helpers.progress_sync import ProgressOutbox


def test_progress_survives_restart_and_separates_episodes(tmp_path):
    path = tmp_path / "progress.sqlite3"
    outbox = ProgressOutbox(path, "https://server/", "alice")
    outbox.record("podcast", "one", 42, 100)
    outbox.record("podcast", "two", 100, 100, True)
    outbox.record("book", None, 0, 600)
    restored = ProgressOutbox(path, "https://server", "alice").pending()
    assert {(e.item_id, e.episode_id, e.position, e.finished) for e in restored} == {
        ("podcast", "one", 42, False), ("podcast", "two", 100, True), ("book", "", 0, False),
    }


def test_acknowledging_old_report_cannot_erase_a_new_position(tmp_path):
    outbox = ProgressOutbox(tmp_path / "progress.sqlite3", "server", "user")
    old = outbox.record("book", None, 80, 100)
    latest = outbox.record("book", None, 20, 100)
    assert not outbox.acknowledge(old)
    assert outbox.pending() == [latest]
    assert outbox.acknowledge(latest)
    assert outbox.pending() == []


def test_accounts_and_servers_cannot_replay_each_others_progress(tmp_path):
    path = tmp_path / "progress.sqlite3"
    outbox = ProgressOutbox(path, "https://one", "alice")
    entry = outbox.record("book", None, 60, 100)
    for server, user in (("https://one", "bob"), ("https://two", "alice")):
        other = ProgressOutbox(path, server, user)
        assert other.pending() == []
        assert not other.acknowledge(entry)
    assert outbox.pending() == [entry]


def test_newer_timestamp_wins_even_when_position_is_earlier(tmp_path):
    outbox = ProgressOutbox(tmp_path / "progress.sqlite3", "server", "user")
    entry = outbox.record("book", None, 80, 100, updated_at=1000)
    assert entry.server_is_newer({"lastUpdate": 2000, "currentTime": 10})
    assert not entry.server_is_newer({"lastUpdate": 900, "currentTime": 90})
    assert not entry.server_is_newer(None)


def test_concurrent_episode_writes_are_all_durable(tmp_path):
    outbox = ProgressOutbox(tmp_path / "progress.sqlite3", "server", "user")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: outbox.record("podcast", str(i), i, 100), range(20)))
    assert len(outbox.pending()) == 20
