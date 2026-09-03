"""Tests for settings persistence and token storage.

The security requirement under test: a token is either handed to the system
keyring or kept in memory for this session - it is never written to a file.
"""

import json

import pytest

import audiflix.config as config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point the config directory at a temporary folder for every test."""
    monkeypatch.setenv("AUDIFLIX_CONFIG_DIR", str(tmp_path))
    config.clear_session_tokens()
    monkeypatch.setattr(config, "_keyring_unavailable", False, raising=False)
    yield tmp_path
    config.clear_session_tokens()


class FakeKeyring:
    """Minimal in-memory stand-in for the keyring module."""

    def __init__(self, working=True):
        self.store: dict[tuple[str, str], str] = {}
        self.working = working

    def set_password(self, service, account, password):
        if not self.working:
            raise RuntimeError("no backend")
        self.store[(service, account)] = password

    def get_password(self, service, account):
        if not self.working:
            raise RuntimeError("no backend")
        return self.store.get((service, account))

    def delete_password(self, service, account):
        if not self.working:
            raise RuntimeError("no backend")
        self.store.pop((service, account), None)

    def get_keyring(self):
        return self


def test_settings_roundtrip(isolated_config):
    settings = config.Settings.load()
    settings["skip_back_seconds"] = 42
    assert settings.save() is True

    reloaded = config.Settings.load()
    assert reloaded.get("skip_back_seconds") == 42


def test_settings_merge_adds_new_defaults(isolated_config):
    (isolated_config / "settings.json").write_text(
        json.dumps({"skip_back_seconds": 5}), encoding="utf-8"
    )
    settings = config.Settings.load()
    assert settings.get("skip_back_seconds") == 5
    assert settings.get("skip_forward_seconds") == 30
    assert settings.shortcut("play_pause") == "Ctrl+Space"


def test_settings_survive_a_broken_file(isolated_config):
    (isolated_config / "settings.json").write_text("{not json", encoding="utf-8")
    settings = config.Settings.load()
    assert settings.get("skip_back_seconds") == 15


def test_legacy_shortcut_is_migrated(isolated_config):
    settings = config.Settings({"shortcuts": {"chapter_list": "Ctrl+K"}})
    assert settings.shortcut("chapter_list") == "Ctrl+Shift+C"


def test_customised_shortcut_is_not_migrated(isolated_config):
    settings = config.Settings({"shortcuts": {"chapter_list": "Ctrl+J"}})
    assert settings.shortcut("chapter_list") == "Ctrl+J"


def test_token_is_stored_in_the_keyring(monkeypatch, isolated_config):
    fake = FakeKeyring()
    monkeypatch.setattr(config, "keyring", fake)

    assert config.save_token("https://abs.example.com", "felix", "tok") is True
    assert config.load_token("https://abs.example.com", "felix") == "tok"
    assert fake.store[("audiflix", "https://abs.example.com|felix")] == "tok"


def test_token_is_never_written_to_disk(monkeypatch, isolated_config):
    """Without a keyring backend the token stays in memory - and only there."""
    monkeypatch.setattr(config, "keyring", None)

    assert config.save_token("https://abs.example.com", "felix", "sekrit") is False
    assert config.load_token("https://abs.example.com", "felix") == "sekrit"

    for path in isolated_config.rglob("*"):
        if path.is_file():
            assert "sekrit" not in path.read_text(encoding="utf-8", errors="ignore")


def test_session_token_is_dropped_on_clear(monkeypatch, isolated_config):
    monkeypatch.setattr(config, "keyring", None)
    config.save_token("https://abs.example.com", "felix", "tok")
    config.clear_session_tokens()
    assert config.load_token("https://abs.example.com", "felix") is None


def test_failing_keyring_falls_back_to_the_session(monkeypatch, isolated_config):
    monkeypatch.setattr(config, "keyring", FakeKeyring(working=False))
    assert config.save_token("https://abs.example.com", "felix", "tok") is False
    assert config.load_token("https://abs.example.com", "felix") == "tok"


def test_clear_token_removes_it_everywhere(monkeypatch, isolated_config):
    fake = FakeKeyring()
    monkeypatch.setattr(config, "keyring", fake)
    config.save_token("https://abs.example.com", "felix", "tok")
    config.clear_token("https://abs.example.com", "felix")
    assert config.load_token("https://abs.example.com", "felix") is None


def test_access_and_refresh_tokens_use_separate_entries(monkeypatch, isolated_config):
    fake = FakeKeyring()
    monkeypatch.setattr(config, "keyring", fake)

    config.save_tokens("https://abs.example.com", "felix", "access", "refresh")
    assert config.load_tokens("https://abs.example.com", "felix") == ("access", "refresh")

    config.clear_tokens("https://abs.example.com", "felix")
    assert config.load_tokens("https://abs.example.com", "felix") == (None, None)


def test_saving_without_refresh_token_clears_the_old_one(monkeypatch, isolated_config):
    fake = FakeKeyring()
    monkeypatch.setattr(config, "keyring", fake)
    config.save_tokens("https://abs.example.com", "felix", "access", "refresh")
    config.save_tokens("https://abs.example.com", "felix", "access2", None)
    assert config.load_tokens("https://abs.example.com", "felix") == ("access2", None)


def test_accounts_are_scoped_per_server_and_user(monkeypatch, isolated_config):
    monkeypatch.setattr(config, "keyring", FakeKeyring())
    config.save_token("https://a.example.com", "felix", "token-a")
    config.save_token("https://b.example.com", "felix", "token-b")
    assert config.load_token("https://a.example.com", "felix") == "token-a"
    assert config.load_token("https://b.example.com", "felix") == "token-b"
    assert config.load_token("https://a.example.com", "other") is None


def test_legacy_plaintext_token_file_is_purged(isolated_config):
    legacy = isolated_config / "token.json"
    legacy.write_text('{"https://abs|felix": "plaintext"}', encoding="utf-8")

    assert config.purge_legacy_token_file() is True
    assert not legacy.exists()
    # A second call is a no-op.
    assert config.purge_legacy_token_file() is False
