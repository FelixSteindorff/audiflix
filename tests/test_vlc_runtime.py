"""Tests for locating and loading the bundled VLC runtime.

The rule these tests protect: a packaged Audiflix uses *its own* libVLC or
fails with a clear message - it must never quietly pick up whatever VLC happens
to be installed on the machine, because that version is untested.

No real DLL is loaded here; the probe is stubbed so the suite runs anywhere.
"""

import json

import pytest

from audiflix import vlc_runtime
from audiflix.vlc_runtime import VlcRuntimeError


@pytest.fixture(autouse=True)
def clean_runtime_state():
    vlc_runtime.reset_for_tests()
    yield
    vlc_runtime.reset_for_tests()


def make_runtime(tmp_path, *, version="3.0.23", plugins=True, library=True):
    """Build a directory that looks like a bundled VLC runtime."""
    directory = tmp_path / "vlc"
    directory.mkdir(parents=True, exist_ok=True)
    if library:
        (directory / vlc_runtime.LIBVLC_NAME).write_bytes(b"not really a dll")
        (directory / "libvlccore.dll").write_bytes(b"not really a dll")
    if plugins:
        plugin_dir = directory / "plugins" / "codec"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "libavcodec_plugin.dll").write_bytes(b"plugin")
    if version:
        (directory / vlc_runtime.METADATA_NAME).write_text(
            json.dumps({"vlc_version": version, "sha256": "a" * 64}), encoding="utf-8"
        )
    return directory


@pytest.fixture
def bundled(tmp_path, monkeypatch):
    directory = make_runtime(tmp_path)
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [directory])
    monkeypatch.setattr(vlc_runtime, "_probe_library", lambda library: None)
    return directory


# --- Finding the runtime ---------------------------------------------------

def test_finds_a_complete_bundled_runtime(bundled):
    assert vlc_runtime.find_bundled_runtime() == bundled


def test_runtime_without_plugins_is_rejected(tmp_path, monkeypatch):
    directory = make_runtime(tmp_path, plugins=False)
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [directory])
    assert vlc_runtime.find_bundled_runtime() is None


def test_runtime_without_the_library_is_rejected(tmp_path, monkeypatch):
    directory = make_runtime(tmp_path, library=False)
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [directory])
    assert vlc_runtime.find_bundled_runtime() is None


def test_missing_directory_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [tmp_path / "nope"])
    assert vlc_runtime.find_bundled_runtime() is None


def test_first_complete_candidate_wins(tmp_path, monkeypatch):
    broken = make_runtime(tmp_path / "a", plugins=False)
    good = make_runtime(tmp_path / "b")
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [broken, good])
    assert vlc_runtime.find_bundled_runtime() == good


def test_env_override_is_used_in_a_source_checkout(tmp_path, monkeypatch):
    directory = make_runtime(tmp_path)
    monkeypatch.setattr(vlc_runtime, "is_frozen", lambda: False)
    monkeypatch.setenv("AUDIFLIX_VLC_DIR", str(directory))
    assert directory in vlc_runtime._candidate_dirs()


def test_candidates_are_deduplicated(monkeypatch, tmp_path):
    monkeypatch.setattr(vlc_runtime, "is_frozen", lambda: True)
    monkeypatch.setattr(vlc_runtime.sys, "executable", str(tmp_path / "audiflix.exe"))
    candidates = vlc_runtime._candidate_dirs()
    assert len(candidates) == len(set(candidates))


# --- Version metadata ------------------------------------------------------

def test_reads_the_version_recorded_by_the_build(bundled):
    assert vlc_runtime.bundled_version(bundled) == "3.0.23"


def test_version_is_empty_without_metadata(tmp_path, monkeypatch):
    directory = make_runtime(tmp_path, version="")
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [directory])
    assert vlc_runtime.bundled_version(directory) == ""


def test_corrupt_metadata_does_not_raise(bundled):
    (bundled / vlc_runtime.METADATA_NAME).write_text("{not json", encoding="utf-8")
    assert vlc_runtime.bundled_version(bundled) == ""


def test_version_without_a_runtime_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [tmp_path / "nope"])
    assert vlc_runtime.bundled_version() == ""


# --- configure() -----------------------------------------------------------

def test_configure_points_python_vlc_at_the_bundle(bundled, monkeypatch):
    recorded = {}
    monkeypatch.setattr(
        vlc_runtime.os, "add_dll_directory",
        lambda path: recorded.setdefault("dll_dir", path), raising=False,
    )
    runtime = vlc_runtime.configure()

    assert runtime.is_bundled
    assert runtime.version == "3.0.23"
    assert vlc_runtime.os.environ["PYTHON_VLC_LIB_PATH"] == str(bundled / vlc_runtime.LIBVLC_NAME)
    assert vlc_runtime.os.environ["PYTHON_VLC_MODULE_PATH"] == str(bundled / "plugins")
    assert vlc_runtime.os.environ["VLC_PLUGIN_PATH"] == str(bundled / "plugins")
    assert recorded["dll_dir"] == str(bundled)


def test_configure_is_cached(bundled):
    assert vlc_runtime.configure() is vlc_runtime.configure()


def test_configure_reports_the_source_in_the_description(bundled):
    assert "bundled VLC 3.0.23" in vlc_runtime.configure().describe()


def test_source_checkout_falls_back_to_a_system_installation(tmp_path, monkeypatch):
    """Convenient while developing - and only while developing."""
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [tmp_path / "nope"])
    monkeypatch.setattr(vlc_runtime, "is_frozen", lambda: False)
    runtime = vlc_runtime.configure()
    assert runtime.source == "system"
    assert runtime.is_bundled is False
    assert "PYTHON_VLC_LIB_PATH" not in vlc_runtime.os.environ


def test_packaged_build_never_falls_back_to_system_vlc(tmp_path, monkeypatch):
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [tmp_path / "nope"])
    monkeypatch.setattr(vlc_runtime, "is_frozen", lambda: True)
    with pytest.raises(VlcRuntimeError):
        vlc_runtime.configure()
    assert "PYTHON_VLC_LIB_PATH" not in vlc_runtime.os.environ


def test_an_unloadable_library_is_reported(tmp_path, monkeypatch):
    directory = make_runtime(tmp_path)
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [directory])
    monkeypatch.setattr(
        vlc_runtime, "_probe_library",
        lambda library: (_ for _ in ()).throw(VlcRuntimeError("bad dll")),
    )
    with pytest.raises(VlcRuntimeError):
        vlc_runtime.configure()


# --- load_vlc() ------------------------------------------------------------

def test_broken_bundle_asks_the_user_to_reinstall(tmp_path, monkeypatch):
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [tmp_path / "nope"])
    monkeypatch.setattr(vlc_runtime, "is_frozen", lambda: True)
    with pytest.raises(VlcRuntimeError) as excinfo:
        vlc_runtime.load_vlc()
    assert "reinstall Audiflix" in str(excinfo.value)


def test_missing_system_vlc_asks_the_user_to_install_vlc(tmp_path, monkeypatch):
    monkeypatch.setattr(vlc_runtime, "_candidate_dirs", lambda: [tmp_path / "nope"])
    monkeypatch.setattr(vlc_runtime, "is_frozen", lambda: False)

    def explode(name, *args, **kwargs):
        if name == "vlc":
            raise ImportError("no vlc")
        return original_import(name, *args, **kwargs)

    import builtins

    original_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", explode)
    with pytest.raises(VlcRuntimeError) as excinfo:
        vlc_runtime.load_vlc()
    assert "videolan.org" in str(excinfo.value)


def test_a_library_less_vlc_module_is_treated_as_broken(bundled, monkeypatch):
    """python-vlc imports fine but has no DLL when the library did not load."""
    import sys
    import types

    stub = types.ModuleType("vlc")
    stub.dll = None
    monkeypatch.setitem(sys.modules, "vlc", stub)
    with pytest.raises(VlcRuntimeError) as excinfo:
        vlc_runtime.load_vlc()
    assert "reinstall Audiflix" in str(excinfo.value)
