# PyInstaller specification for Audiflix.
#
# Build:  python build_exe.py   (or)   pyinstaller audiflix.spec
# Result: dist/Audiflix/audiflix.exe plus its data directory.
#
# Audiflix ships its own VLC runtime (build/vlc, produced by
# tools/fetch_vlc.py), so the installed application needs no separate VLC
# installation. That runtime is around 140 MB, which is why this is a onedir
# build: a onefile executable would unpack all of it into a temporary folder on
# every single start. The user-facing artifact is the Inno Setup installer
# created by packaging/audiflix.iss.

import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
sys.path.insert(0, str(SPEC_DIR / "tools"))

from version_info import read_version, write_version_file  # noqa: E402

VERSION = read_version()
VERSION_FILE = write_version_file(SPEC_DIR / "build" / "version_info.txt", VERSION)
ICON = SPEC_DIR / "src" / "audiflix" / "resources" / "audiflix.ico"
LOCALE_DIR = SPEC_DIR / "src" / "audiflix" / "locale"
VLC_DIR = SPEC_DIR / "build" / "vlc"

if not (VLC_DIR / "libvlc.dll").is_file():
    raise SystemExit(
        "The bundled VLC runtime is missing.\n"
        "Run:  python tools/fetch_vlc.py --use-lock"
    )

# Icon and compiled translation catalogs.
datas = [(str(ICON), "resources")]
for mo_file in LOCALE_DIR.rglob("*.mo"):
    datas.append((str(mo_file), str(Path("locale") / mo_file.relative_to(LOCALE_DIR).parent)))

# The VLC runtime is copied verbatim - these are VideoLAN's signed binaries and
# must not be rewritten by PyInstaller's dependency analysis, so they are added
# as data rather than as binaries.
vlc_tree = Tree(str(VLC_DIR), prefix="vlc")

COMMON = dict(
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'vlc',
        'accessible_output2',
        'accessible_output2.outputs.auto',
        'accessible_output2.outputs.nvda',
        'accessible_output2.outputs.sapi5',
        'keyring.backends.Windows',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'pytest', 'PIL'],
    noarchive=False,
)

# Two executables share one data directory: the windowed application and a
# console-mode diagnostic. A windowed build has nowhere to print, so
# "does the bundled engine work here?" needs its own console executable.
a = Analysis(['src/audiflix/__main__.py'], **COMMON)
a_selftest = Analysis(['packaging/selftest_entry.py'], **COMMON)

pyz = PYZ(a.pure, a.zipped_data)
pyz_selftest = PYZ(a_selftest.pure, a_selftest.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='audiflix',
    debug=False,
    strip=False,
    # UPX is off: it makes builds non-reproducible, and some antivirus products
    # flag UPX-packed binaries.
    upx=False,
    console=False,
    windowed=True,
    icon=str(ICON) if ICON.is_file() else None,
    version=str(VERSION_FILE),
)

exe_selftest = EXE(
    pyz_selftest,
    a_selftest.scripts,
    exclude_binaries=True,
    name='audiflix-selftest',
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ICON) if ICON.is_file() else None,
    version=str(VERSION_FILE),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    exe_selftest,
    a_selftest.binaries,
    a_selftest.zipfiles,
    a_selftest.datas,
    vlc_tree,
    strip=False,
    upx=False,
    name='Audiflix',
)
