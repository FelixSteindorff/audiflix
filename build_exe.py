"""Build the Windows application and, optionally, its installer.

    pip install -r requirements-build.txt
    python build_exe.py                 # dist/Audiflix/ (onedir application)
    python build_exe.py --installer     # additionally dist/Audiflix-<ver>-Setup.exe
    python build_exe.py --latest-vlc    # use the newest stable VLC, not the pin

Steps, in order:

1. fetch the VLC runtime pinned in ``vlc.lock.json`` (verified against
   VideoLAN's published checksum),
2. compile the translation catalogs,
3. run PyInstaller (onedir - the VLC runtime is far too large for a onefile
   build that unpacks on every start),
4. run the packaged application's ``--selftest`` so a broken bundle is caught
   here rather than by a user,
5. optionally build the Inno Setup installer.

The SHA-256 of every produced artifact is printed so a release can be verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "audiflix.spec"
DIST = ROOT / "dist"
APP_DIR = DIST / "Audiflix"
APP_EXE = APP_DIR / "audiflix.exe"
SELFTEST_EXE = APP_DIR / "audiflix-selftest.exe"
ISS = ROOT / "packaging" / "audiflix.iss"
VLC_METADATA = ROOT / "build" / "vlc-version.json"

# os.environ is case-insensitive on Windows, where these variables exist.
INNO_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
)


def run(command: list[str], what: str) -> None:
    print(f"\n=== {what} ===")
    print(" ", " ".join(command))
    code = subprocess.call(command, cwd=str(ROOT))
    if code != 0:
        raise SystemExit(f"{what} failed with exit code {code}")


def read_version() -> str:
    sys.path.insert(0, str(ROOT / "tools"))
    from version_info import read_version as read

    return read()


def vlc_version() -> str:
    try:
        return json.loads(VLC_METADATA.read_text(encoding="utf-8"))["vlc_version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def find_iscc() -> Path | None:
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return Path(found)
    for candidate in INNO_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--installer", action="store_true", help="also build the Inno Setup installer")
    parser.add_argument(
        "--latest-vlc", action="store_true",
        help="use the newest stable VLC instead of the version in vlc.lock.json",
    )
    parser.add_argument("--skip-vlc", action="store_true", help="reuse an already fetched build/vlc")
    parser.add_argument("--skip-selftest", action="store_true", help="do not run the packaged self-test")
    args = parser.parse_args(argv)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is missing. Install it with: pip install -r requirements-build.txt")
        return 1

    version = read_version()
    print(f"Building Audiflix {version}")

    if not args.skip_vlc:
        fetch = [sys.executable, str(ROOT / "tools" / "fetch_vlc.py")]
        fetch += [] if args.latest_vlc else ["--use-lock"]
        run(fetch, "Fetching the VLC runtime")
    run([sys.executable, str(ROOT / "tools" / "i18n_tool.py"), "compile"], "Compiling translations")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)], "Running PyInstaller")

    if not APP_EXE.is_file():
        raise SystemExit(f"Expected {APP_EXE} to exist after the build")

    if not args.skip_selftest:
        print("\n=== Verifying the packaged audio engine ===")
        if not SELFTEST_EXE.is_file():
            raise SystemExit(f"Expected {SELFTEST_EXE} to exist after the build")
        code = subprocess.call([str(SELFTEST_EXE)], cwd=str(APP_DIR))
        if code != 0:
            raise SystemExit(
                "The packaged application failed its self-test - the bundled VLC "
                "runtime is not usable. Refusing to publish this build."
            )

    artifacts: list[Path] = []
    if args.installer:
        iscc = find_iscc()
        if iscc is None:
            raise SystemExit(
                "Inno Setup 6 (ISCC.exe) was not found. Install it from "
                "https://jrsoftware.org/isinfo.php or drop --installer."
            )
        run(
            [
                str(iscc),
                f"/DAppVersion={version}",
                f"/DVlcVersion={vlc_version()}",
                str(ISS),
            ],
            "Building the installer",
        )
        installer = DIST / f"Audiflix-{version}-Setup.exe"
        if not installer.is_file():
            raise SystemExit(f"Expected {installer} to exist after the Inno Setup run")
        artifacts.append(installer)

    print("\n=== Result ===")
    print(f"Audiflix {version} with bundled VLC {vlc_version()}")
    print(f"  {APP_DIR}  ({directory_size(APP_DIR) / 1e6:.1f} MB unpacked)")
    for artifact in artifacts:
        print(f"  {artifact}  ({artifact.stat().st_size / 1e6:.1f} MB)")
        print(f"    SHA-256: {sha256(artifact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
