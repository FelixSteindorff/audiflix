"""Diagnostic self-test for the bundled audio engine.

Run with ``audiflix --selftest`` (or ``audiflix.exe --selftest`` in an
installation). It answers the one question a packaged build has to get right:
*does audio playback work here, without VLC being installed?*

The check is deliberately end-to-end - it loads the bundled libVLC, verifies
that the plugins needed for the formats Audiobookshelf serves are present, and
then actually decodes a generated audio file through libVLC and watches the
playback clock advance. It uses the dummy audio output, so it also works on a
build server with no sound hardware.

Exit code 0 means every check passed.
"""

from __future__ import annotations

import math
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

from audiflix import APP_DISPLAY_NAME, __version__, vlc_runtime

#: Plugins Audiflix depends on, grouped by what breaks without them.
REQUIRED_PLUGINS: dict[str, tuple[str, ...]] = {
    "HTTP(S) streaming": ("access/libhttp_plugin.dll", "access/libhttps_plugin.dll"),
    "HLS / adaptive streaming": ("demux/libadaptive_plugin.dll",),
    "M4B/M4A container": ("demux/libmp4_plugin.dll",),
    "AAC and general decoding": ("codec/libavcodec_plugin.dll",),
    "MP3 decoding": ("codec/libmpg123_plugin.dll",),
    "FLAC decoding": ("codec/libflac_plugin.dll",),
    "Windows audio output": (
        "audio_output/libmmdevice_plugin.dll",
        "audio_output/libdirectsound_plugin.dll",
    ),
}

#: How long the decode check may take before it is considered failed.
PLAYBACK_TIMEOUT = 30.0
TONE_SECONDS = 2
TONE_RATE = 22050


class SelfTestFailure(RuntimeError):
    """A check failed; the message explains which one."""


def _ok(label: str, detail: str = "") -> None:
    print(f"  [ok]   {label}" + (f": {detail}" if detail else ""))


def _fail(label: str, detail: str) -> None:
    print(f"  [FAIL] {label}: {detail}")


def write_test_tone(path: Path) -> Path:
    """A two-second sine wave - small, generated, and free of licensing issues."""
    frames = bytearray()
    for index in range(TONE_RATE * TONE_SECONDS):
        value = int(16000 * math.sin(2 * math.pi * 440 * index / TONE_RATE))
        frames += struct.pack("<h", value)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(TONE_RATE)
        handle.writeframes(bytes(frames))
    return path


def check_runtime() -> vlc_runtime.VlcRuntime:
    runtime = vlc_runtime.configure()
    if vlc_runtime.is_frozen() and not runtime.is_bundled:
        raise SelfTestFailure(
            "a packaged build must use its bundled runtime, but it resolved to "
            f"{runtime.describe()}"
        )
    _ok("VLC runtime", runtime.describe())
    return runtime


def check_plugins(runtime: vlc_runtime.VlcRuntime) -> None:
    if not runtime.is_bundled:
        print("  [skip] plugin inventory (using a system VLC installation)")
        return
    missing: list[str] = []
    for purpose, candidates in REQUIRED_PLUGINS.items():
        if not any((runtime.plugins / name).is_file() for name in candidates):
            missing.append(f"{purpose} ({' or '.join(candidates)})")
    if missing:
        raise SelfTestFailure("missing plugins for: " + "; ".join(missing))
    total = sum(1 for _ in runtime.plugins.rglob("*.dll"))
    _ok("Plugin inventory", f"{total} modules, all required families present")


def check_library() -> object:
    vlc = vlc_runtime.load_vlc()
    version = vlc.libvlc_get_version().decode("utf-8", "replace")
    library = getattr(getattr(vlc, "dll", None), "_name", "?")
    _ok("libVLC loaded", f"{version} from {library}")
    return vlc


def check_audio_outputs(vlc, instance) -> None:
    outputs = instance.audio_output_list_get()
    names = []
    try:
        entry = outputs
        while entry:
            names.append(entry.contents.name.decode("utf-8", "replace"))
            entry = entry.contents.next
    finally:
        if outputs:
            vlc.libvlc_audio_output_list_release(outputs)
    if not names:
        raise SelfTestFailure("libVLC reports no audio output modules")
    _ok("Audio outputs", ", ".join(names))


def check_playback(vlc, instance, media_path: Path) -> None:
    """Decode a real file and require the playback clock to advance."""
    player = instance.media_player_new()
    media = instance.media_new_path(str(media_path))
    player.set_media(media)
    if player.play() != 0:
        raise SelfTestFailure("libVLC refused to start playback")

    deadline = time.monotonic() + PLAYBACK_TIMEOUT
    seen_playing = False
    max_time = 0
    try:
        while time.monotonic() < deadline:
            state = player.get_state()
            max_time = max(max_time, player.get_time())
            if state == vlc.State.Playing:
                seen_playing = True
            if state == vlc.State.Error:
                raise SelfTestFailure("libVLC reported a playback error")
            if state == vlc.State.Ended:
                break
            time.sleep(0.1)
        else:
            raise SelfTestFailure(f"playback did not finish within {PLAYBACK_TIMEOUT:.0f} s")
    finally:
        player.stop()
        player.release()

    if not seen_playing:
        raise SelfTestFailure("the player never reached the Playing state")
    if max_time <= 0:
        raise SelfTestFailure("the playback clock never advanced")
    _ok("Decode and playback", f"reached {max_time} ms of a {TONE_SECONDS} s file")


def run_selftest() -> int:
    """Run every check and return a process exit code."""
    print(f"{APP_DISPLAY_NAME} {__version__} self-test")
    print(f"  Python {sys.version.split()[0]} on {sys.platform}, "
          f"{'packaged build' if vlc_runtime.is_frozen() else 'source checkout'}")
    try:
        runtime = check_runtime()
        check_plugins(runtime)
        vlc = check_library()
        instance = vlc.Instance("--no-video", "--quiet", "--aout=dummy")
        if instance is None:
            raise SelfTestFailure("libVLC could not create an instance")
        check_audio_outputs(vlc, instance)
        with tempfile.TemporaryDirectory(prefix="audiflix-selftest-") as tmp:
            media = write_test_tone(Path(tmp) / "tone.wav")
            check_playback(vlc, instance, media)
    except SelfTestFailure as exc:
        _fail("Self-test", str(exc))
        print("\nRESULT: FAILED")
        return 1
    except Exception as exc:  # noqa: BLE001 - a diagnostic must report anything
        _fail("Self-test", f"unexpected error: {exc!r}")
        print("\nRESULT: FAILED")
        return 1
    print("\nRESULT: PASSED - audio playback works without a separate VLC installation")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_selftest())
