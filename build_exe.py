"""Build the standalone ``audiflix.exe`` with PyInstaller.

    pip install -r requirements-build.txt
    python build_exe.py
    # result: dist/audiflix.exe

The script compiles the translation catalogs first (the .mo files are not
checked into the repository) and prints the SHA-256 of the result so a build
can be compared against a published release.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "audiflix.spec"
RESULT = ROOT / "dist" / "audiflix.exe"


def compile_catalogs() -> int:
    return subprocess.call([sys.executable, str(ROOT / "tools" / "i18n_tool.py"), "compile"])


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is missing. Install it with: pip install -r requirements-build.txt")
        return 1

    if compile_catalogs() != 0:
        print("Could not compile the translation catalogs.")
        return 1

    if not (ROOT / "src" / "audiflix" / "resources" / "audiflix.ico").is_file():
        print("Warning: the application icon is missing (run: python tools/make_icon.py)")

    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)]
    print("Running:", " ".join(command))
    code = subprocess.call(command)
    if code != 0:
        return code

    if RESULT.is_file():
        digest = hashlib.sha256(RESULT.read_bytes()).hexdigest()
        print(f"\nBuilt {RESULT} ({RESULT.stat().st_size:,} bytes)")
        print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
