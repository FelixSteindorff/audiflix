"""Locating and loading libVLC.

Audiflix ships its own copy of the VLC runtime, so a released build does not
need VLC to be installed. This module is the single place that decides *which*
libVLC gets loaded, and it must run before ``import vlc``: python-vlc searches
the system for a library as soon as it is imported, and - worse - calls
``sys.exit(1)`` when the library named by ``PYTHON_VLC_LIB_PATH`` fails to
load. Audiflix therefore probes the DLL itself first and raises a proper error.

Rules
-----
* **A packaged build only ever uses its own runtime.** If the bundled files are
  missing or unloadable, Audiflix reports that the installation is damaged. It
  never silently falls back to whatever VLC happens to be installed, because
  that version is untested and may be missing the plugins we rely on.
* **A source checkout prefers the bundled runtime** (``build/vlc``, created by
  ``tools/fetch_vlc.py``) and falls back to a system installation, which is the
  convenient behaviour while developing.
* No VLC version is hard-coded anywhere. The bundled version is read from the
  metadata file the build wrote, purely so it can be logged and shown in the
  About dialog.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from audiflix.i18n import _
from audiflix.logging_setup import get_logger

log = get_logger(__name__)

#: Name of the directory holding the bundled runtime, inside the app folder.
RUNTIME_DIRNAME = "vlc"
METADATA_NAME = "vlc-version.json"
LIBVLC_NAME = "libvlc.dll" if sys.platform == "win32" else "libvlc.so"

_dll_directory_cookie = None
_configured: VlcRuntime | None = None


class VlcRuntimeError(RuntimeError):
    """libVLC could not be located or loaded."""


@dataclass(frozen=True)
class VlcRuntime:
    """Where libVLC was found and what the caller should know about it."""

    source: str                 # "bundled" | "system"
    path: Path | None           # runtime directory (bundled only)
    library: Path | None        # full path of libvlc.dll (bundled only)
    plugins: Path | None        # plugin directory (bundled only)
    version: str = ""           # VLC version recorded at build time

    @property
    def is_bundled(self) -> bool:
        return self.source == "bundled"

    def describe(self) -> str:
        if self.is_bundled:
            return f"bundled VLC {self.version or '(unknown version)'} at {self.path}"
        return "system VLC installation"


def is_frozen() -> bool:
    """True when running from a PyInstaller build rather than from source."""
    return bool(getattr(sys, "frozen", False))


def _candidate_dirs() -> list[Path]:
    """Places a bundled runtime can live, most specific first."""
    candidates: list[Path] = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / RUNTIME_DIRNAME)
    if is_frozen():
        # onedir layout: audiflix.exe sits next to (or one level above) the data
        # directory, depending on the PyInstaller version.
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / RUNTIME_DIRNAME)
        candidates.append(exe_dir / "_internal" / RUNTIME_DIRNAME)
    else:
        # Source checkout: whatever tools/fetch_vlc.py produced.
        candidates.append(Path(__file__).resolve().parent.parent.parent / "build" / RUNTIME_DIRNAME)
        env = os.environ.get("AUDIFLIX_VLC_DIR")
        if env:
            candidates.insert(0, Path(env))
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _is_complete(directory: Path) -> bool:
    """A runtime is usable only with the core library *and* its plugins."""
    if not (directory / LIBVLC_NAME).is_file():
        return False
    plugins = directory / "plugins"
    return plugins.is_dir() and any(plugins.iterdir())


def find_bundled_runtime() -> Path | None:
    """First complete bundled runtime directory, or ``None``."""
    for candidate in _candidate_dirs():
        if _is_complete(candidate):
            return candidate
        if candidate.exists():
            log.warning("Ignoring incomplete VLC runtime at %s", candidate)
    return None


def bundled_version(directory: Path | None = None) -> str:
    """VLC version recorded by the build, or an empty string."""
    directory = directory or find_bundled_runtime()
    if directory is None:
        return ""
    metadata = directory / METADATA_NAME
    if not metadata.is_file():
        return ""
    try:
        return str(json.loads(metadata.read_text(encoding="utf-8")).get("vlc_version") or "")
    except (OSError, ValueError, TypeError):
        log.warning("Could not read %s", metadata, exc_info=True)
        return ""


def _probe_library(library: Path) -> None:
    """Load the DLL once so a broken bundle fails here, with a real message."""
    try:
        ctypes.CDLL(str(library))
    except OSError as exc:
        raise VlcRuntimeError(f"{library} could not be loaded: {exc}") from exc


def configure() -> VlcRuntime:
    """Point python-vlc at the bundled runtime. Safe to call more than once."""
    global _dll_directory_cookie, _configured
    if _configured is not None:
        return _configured

    directory = find_bundled_runtime()
    if directory is None:
        if is_frozen():
            raise VlcRuntimeError(
                "No bundled VLC runtime was found next to the executable "
                f"(looked in: {', '.join(str(p) for p in _candidate_dirs())})"
            )
        log.info("No bundled VLC runtime found - falling back to a system installation")
        _configured = VlcRuntime(source="system", path=None, library=None, plugins=None)
        return _configured

    library = directory / LIBVLC_NAME
    plugins = directory / "plugins"

    # Windows resolves libvlccore.dll and the plugin DLLs relative to the DLL
    # search path, which since Python 3.8 no longer includes arbitrary
    # directories. The returned cookie must stay alive for the directory to
    # remain on the search path.
    if hasattr(os, "add_dll_directory"):
        try:
            _dll_directory_cookie = os.add_dll_directory(str(directory))
        except OSError as exc:
            raise VlcRuntimeError(f"{directory} could not be added to the DLL search path: {exc}") from exc

    _probe_library(library)

    os.environ["PYTHON_VLC_LIB_PATH"] = str(library)
    os.environ["PYTHON_VLC_MODULE_PATH"] = str(plugins)
    os.environ["VLC_PLUGIN_PATH"] = str(plugins)

    if "vlc" in sys.modules:
        # Only happens if some other import pulled python-vlc in first; the
        # already-loaded library would win and silently be the wrong one.
        log.warning("python-vlc was imported before the bundled runtime was configured")

    runtime = VlcRuntime(
        source="bundled",
        path=directory,
        library=library,
        plugins=plugins,
        version=bundled_version(directory),
    )
    log.info("Using %s", runtime.describe())
    _configured = runtime
    return runtime


def load_vlc():
    """Configure the runtime and return the imported ``vlc`` module.

    Raises :class:`VlcRuntimeError` with a message meant for the user.
    """
    try:
        runtime = configure()
    except VlcRuntimeError as exc:
        log.error("VLC runtime could not be prepared: %s", exc)
        raise VlcRuntimeError(_broken_bundle_message()) from exc

    try:
        import vlc
    except Exception as exc:
        log.exception("python-vlc could not be imported")
        if runtime.is_bundled or is_frozen():
            raise VlcRuntimeError(_broken_bundle_message()) from exc
        raise VlcRuntimeError(_missing_system_vlc_message()) from exc

    if getattr(vlc, "dll", None) is None:
        message = _broken_bundle_message() if runtime.is_bundled else _missing_system_vlc_message()
        raise VlcRuntimeError(message)
    return vlc


def _broken_bundle_message() -> str:
    return _(
        "The bundled audio engine could not be loaded. Please reinstall Audiflix."
    )


def _missing_system_vlc_message() -> str:
    return _(
        "VLC is not available. Please install the VLC media player "
        "(https://www.videolan.org)."
    )


def reset_for_tests() -> None:
    """Forget the cached configuration (used by the test suite)."""
    global _configured, _dll_directory_cookie
    _configured = None
    _dll_directory_cookie = None
    for name in ("PYTHON_VLC_LIB_PATH", "PYTHON_VLC_MODULE_PATH", "VLC_PLUGIN_PATH"):
        os.environ.pop(name, None)
