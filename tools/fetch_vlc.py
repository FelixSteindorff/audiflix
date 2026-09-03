#!/usr/bin/env python3
"""Download and unpack the VLC Windows runtime that ships inside Audiflix.

Audiflix bundles libVLC so users do not have to install VLC themselves. The
binaries are **never committed** - they are fetched here at build time from
the official VideoLAN server and verified against the checksum VideoLAN
publishes next to the archive.

    # what a release build does: exactly the version pinned in vlc.lock.json
    python tools/fetch_vlc.py --use-lock

    # what a developer gets by default: the current stable release
    python tools/fetch_vlc.py

    # reproduce an old build, or prepare a pin
    python tools/fetch_vlc.py --version 3.0.21
    python tools/fetch_vlc.py --update-lock

    # for the "is there a newer VLC?" workflow
    python tools/fetch_vlc.py --check-only

The resolved version, URL and checksum are written to ``build/vlc-version.json``
so every build records precisely which VLC it contains. Only the standard
library is used, so this runs on a bare CI image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = ROOT / "build" / "vlc"
DEFAULT_CACHE = ROOT / "build" / "_cache"
DEFAULT_METADATA = ROOT / "build" / "vlc-version.json"
LOCK_FILE = ROOT / "vlc.lock.json"

DOWNLOAD_BASE = "https://download.videolan.org/pub/videolan/vlc"
LATEST_LISTING = f"{DOWNLOAD_BASE}/last/win64/"
ARCHIVE_PATTERN = re.compile(r"vlc-(\d+\.\d+\.\d+)-win64\.zip")

USER_AGENT = "audiflix-build/1.0 (+https://github.com/FelixSteindorff/audiflix)"
TIMEOUT = 120
CHUNK = 1 << 20

#: Directories copied from the archive in full.
BUNDLED_TREES = (
    "plugins",  # every codec, access, demux and audio-output module
    "lua",      # playlist/stream-filter scripts several plugins rely on
    "hrtfs",    # data files for the binaural audio filter
)

#: Individual files copied from the archive root.
BUNDLED_FILES = (
    "libvlc.dll",
    "libvlccore.dll",
    "vlc-cache-gen.exe",  # lets the installer pre-build the plugin cache
)

#: Legal texts copied next to the runtime (see THIRD_PARTY_NOTICES.md).
LICENSE_FILES = ("COPYING.txt", "AUTHORS.txt", "THANKS.txt", "README.txt", "NEWS.txt")

#: Deliberately left out: vlc.exe and the Qt interface, the browser plugins
#: (axvlc/npvlc), the skins, the MSI helper files and VLC's own UI
#: translations. None of them are reachable through libVLC.


class VlcFetchError(RuntimeError):
    """Downloading or verifying the VLC runtime failed."""


# --- Remote lookups --------------------------------------------------------

def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise VlcFetchError(f"Could not fetch {url}: {exc}") from exc


def resolve_latest_version() -> str:
    """Newest stable win64 release, taken from VideoLAN's own "last" pointer."""
    listing = _get(LATEST_LISTING).decode("utf-8", "replace")
    versions = sorted(
        {match.group(1) for match in ARCHIVE_PATTERN.finditer(listing)},
        key=lambda value: tuple(int(part) for part in value.split(".")),
    )
    if not versions:
        raise VlcFetchError(f"No win64 archive found in {LATEST_LISTING}")
    return versions[-1]


def archive_name(version: str) -> str:
    return f"vlc-{version}-win64.zip"


def archive_url(version: str) -> str:
    return f"{DOWNLOAD_BASE}/{version}/win64/{archive_name(version)}"


def official_sha256(version: str) -> str:
    """The checksum VideoLAN publishes next to the archive."""
    text = _get(archive_url(version) + ".sha256").decode("utf-8", "replace")
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not match:
        raise VlcFetchError(f"Could not read the official checksum for VLC {version}")
    return match.group(1).lower()


# --- Lock file -------------------------------------------------------------

def read_lock(path: Path = LOCK_FILE) -> dict:
    if not path.is_file():
        raise VlcFetchError(
            f"{path.name} is missing - run 'python tools/fetch_vlc.py --update-lock' first"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("version", "sha256"):
        if not data.get(key):
            raise VlcFetchError(f"{path.name} has no '{key}' entry")
    return data


def write_lock(version: str, sha256: str, path: Path = LOCK_FILE) -> None:
    payload = {
        "_comment": (
            "VLC runtime pinned for reproducible Audiflix release builds. "
            "Update with: python tools/fetch_vlc.py --update-lock"
        ),
        "version": version,
        "sha256": sha256,
        "url": archive_url(version),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# --- Download and extraction ----------------------------------------------

def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_archive(version: str, cache_dir: Path, expected_sha256: str) -> Path:
    """Download (or reuse) the archive and verify it against ``expected_sha256``."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / archive_name(version)

    if target.is_file():
        actual = sha256_of(target)
        if actual == expected_sha256:
            print(f"Using cached {target.name}")
            return target
        print(f"Cached {target.name} has the wrong checksum - downloading again")
        target.unlink()

    url = archive_url(version)
    print(f"Downloading {url}")
    partial = target.with_suffix(".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, \
                partial.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        print()
    except urllib.error.URLError as exc:
        partial.unlink(missing_ok=True)
        raise VlcFetchError(f"Download failed: {exc}") from exc

    actual = sha256_of(partial)
    if actual != expected_sha256:
        partial.unlink(missing_ok=True)
        raise VlcFetchError(
            "Checksum mismatch for the downloaded VLC archive.\n"
            f"  expected: {expected_sha256}\n  actual:   {actual}\n"
            "The download was discarded."
        )
    partial.replace(target)
    return target


def extract_runtime(archive: Path, version: str, dest: Path) -> dict:
    """Unpack the parts of the archive Audiflix ships. Returns a small summary."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    licenses = dest / "licenses"
    licenses.mkdir()

    prefix = f"vlc-{version}/"
    wanted_trees = tuple(prefix + name + "/" for name in BUNDLED_TREES)
    wanted_files = {prefix + name for name in BUNDLED_FILES}
    wanted_licenses = {prefix + name for name in LICENSE_FILES}

    copied = 0
    total_bytes = 0
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.namelist()
        if not any(name.startswith(prefix) for name in members):
            raise VlcFetchError(
                f"The archive does not contain the expected '{prefix}' directory"
            )
        for name in members:
            if name.endswith("/"):
                continue
            if name in wanted_files or name.startswith(wanted_trees):
                target = dest / name[len(prefix):]
            elif name in wanted_licenses:
                target = licenses / name[len(prefix):]
            else:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(name) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            copied += 1
            total_bytes += target.stat().st_size

    _verify_runtime(dest)
    return {"files": copied, "bytes": total_bytes}


def _verify_runtime(dest: Path) -> None:
    """Fail loudly here rather than at application start-up."""
    missing = [name for name in ("libvlc.dll", "libvlccore.dll") if not (dest / name).is_file()]
    if missing:
        raise VlcFetchError(f"Extracted runtime is incomplete, missing: {', '.join(missing)}")
    plugins = dest / "plugins"
    if not plugins.is_dir() or not any(plugins.rglob("*.dll")):
        raise VlcFetchError("Extracted runtime has no VLC plugins")


def write_metadata(path: Path, version: str, sha256: str, summary: dict, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "vlc_version": version,
        "archive": archive_name(version),
        "url": archive_url(version),
        "sha256": sha256,
        "version_source": source,
        "extracted_files": summary["files"],
        "extracted_bytes": summary["bytes"],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


# --- Command line ----------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--version", help="fetch this exact VLC version")
    source.add_argument(
        "--use-lock", action="store_true",
        help="fetch the version pinned in vlc.lock.json (used by release builds)",
    )
    parser.add_argument(
        "--update-lock", action="store_true",
        help="write the fetched version and checksum to vlc.lock.json",
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="print the latest stable version and the pinned one, then exit",
    )
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--lock", type=Path, default=LOCK_FILE)
    args = parser.parse_args(argv)

    try:
        if args.check_only:
            return _check_only(args)

        if args.version:
            version, expected, origin = args.version, None, "command line"
        elif args.use_lock:
            lock = read_lock(args.lock)
            version, expected, origin = lock["version"], lock["sha256"].lower(), "vlc.lock.json"
        else:
            version, expected, origin = resolve_latest_version(), None, "latest stable"

        published = official_sha256(version)
        if expected and expected != published:
            raise VlcFetchError(
                f"vlc.lock.json pins a checksum for VLC {version} that VideoLAN does not "
                f"publish.\n  locked:    {expected}\n  published: {published}\n"
                "Refusing to build. Investigate before updating the lock file."
            )

        print(f"VLC {version} ({origin})")
        archive = download_archive(version, args.cache, published)
        summary = extract_runtime(archive, version, args.dest)
        print(
            f"Extracted {summary['files']} files "
            f"({summary['bytes'] / 1e6:.1f} MB) to {args.dest}"
        )
        write_metadata(args.metadata, version, published, summary, origin)
        # A copy inside the runtime travels with the bundle, so the packaged
        # application can report which VLC it contains.
        write_metadata(args.dest / "vlc-version.json", version, published, summary, origin)

        if args.update_lock:
            write_lock(version, published, args.lock)
            print(f"Updated {args.lock} to VLC {version}")
    except VlcFetchError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    return 0


def _check_only(args) -> int:
    latest = resolve_latest_version()
    try:
        pinned = read_lock(args.lock)["version"]
    except VlcFetchError:
        pinned = ""
    print(json.dumps({
        "latest": latest,
        "pinned": pinned,
        "update_available": bool(pinned) and pinned != latest,
        "sha256": official_sha256(latest),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
