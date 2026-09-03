# PyInstaller specification for Audiflix.
#
# Build:  python build_exe.py   (or)   pyinstaller audiflix.spec
#
# Note: VLC must be installed on the target system - python-vlc uses the
# system-wide libvlc. The .exe does NOT bundle VLC.

import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
sys.path.insert(0, str(SPEC_DIR / "tools"))

from version_info import read_version, write_version_file  # noqa: E402

VERSION = read_version()
VERSION_FILE = write_version_file(SPEC_DIR / "build" / "version_info.txt", VERSION)
ICON = SPEC_DIR / "src" / "audiflix" / "resources" / "audiflix.ico"
LOCALE_DIR = SPEC_DIR / "src" / "audiflix" / "locale"

# Ship the compiled catalogs and the icon next to the executable's data root.
datas = [(str(ICON), "resources")]
for mo_file in LOCALE_DIR.rglob("*.mo"):
    datas.append((str(mo_file), str(Path("locale") / mo_file.relative_to(LOCALE_DIR).parent)))

a = Analysis(
    ['src/audiflix/__main__.py'],
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

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='audiflix',
    debug=False,
    strip=False,
    # UPX is off by default: it makes the build non-reproducible and some
    # antivirus products flag UPX-packed binaries.
    upx=False,
    console=False,
    windowed=True,
    icon=str(ICON) if ICON.is_file() else None,
    version=str(VERSION_FILE),
)
