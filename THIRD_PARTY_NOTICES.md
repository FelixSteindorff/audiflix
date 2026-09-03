# Third-party notices

Audiflix itself is licensed under the [MIT License](LICENSE). The released
Windows application additionally contains, or is built from, the third-party
components listed below. This file is installed alongside the application as
`THIRD_PARTY_NOTICES.txt`.

---

## VLC media player / libVLC (VideoLAN)

Audiflix **bundles the VLC runtime**, so users do not have to install VLC
separately. The binaries are VideoLAN's official Windows 64-bit build,
redistributed **unmodified**.

* Project: <https://www.videolan.org/vlc/>
* Copyright © the VideoLAN team and VLC authors (see
  `_internal/vlc/licenses/AUTHORS.txt` in an installation)
* Licence: **GNU General Public License, version 2 or later** for the media
  player and its plugins; the core library `libvlc` is additionally available
  under the **GNU Lesser General Public License, version 2.1 or later**. Because
  the bundle includes GPL-licensed plugins, the VLC portion of this
  distribution is governed by the GPL v2 or later.
* Full licence text: `_internal/vlc/licenses/COPYING.txt` (installed with the
  application) and <https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>

### Which version is included

Every Audiflix build records the exact VLC version and the SHA-256 checksum of
the archive it was built from:

* the pinned version lives in [`vlc.lock.json`](vlc.lock.json) in this
  repository,
* the version actually used by a build is written to
  `build/vlc-version.json` and shipped as `_internal/vlc/vlc-version.json`,
* an installed copy reports it via `audiflix.exe --version` and in
  **Help → About Audiflix**.

### Written offer of source code

The complete corresponding source code for the bundled VLC version is published
by VideoLAN and can be downloaded from:

```
https://download.videolan.org/pub/videolan/vlc/<version>/vlc-<version>.tar.xz
```

where `<version>` is the version recorded as described above. For VLC 3.0.23,
for example, that is
<https://download.videolan.org/pub/videolan/vlc/3.0.23/vlc-3.0.23.tar.xz>.

If that address is ever unavailable, open an issue at
<https://github.com/FelixSteindorff/audiflix/issues> and the maintainer will
provide the corresponding source for any released Audiflix build.

Audiflix does not modify VLC. It links against libVLC through the `python-vlc`
bindings and calls the public libVLC API only. VLC is included as an internal
audio engine; it is not registered as an application, does not appear in the
start menu, and does not touch any separate VLC installation.

### Trademarks

"VLC", "VideoLAN" and the VLC traffic-cone logo are trademarks of the VideoLAN
association. Audiflix is **not** endorsed by or affiliated with VideoLAN. The
VLC cone logo is not used anywhere in Audiflix.

---

## Audiobookshelf

Audiflix is an independent third-party client for
[Audiobookshelf](https://www.audiobookshelf.org/) and contains no Audiobookshelf
code. The name is used solely to describe compatibility. Audiflix is not
affiliated with, endorsed by, or supported by the Audiobookshelf project.

---

## Python dependencies

| Component | Purpose | Licence |
|---|---|---|
| [wxPython](https://wxpython.org/) | GUI toolkit | wxWindows Library Licence (LGPL-based, with a binary-distribution exception) |
| [python-vlc](https://pypi.org/project/python-vlc/) | libVLC bindings | LGPL-2.1-or-later |
| [requests](https://requests.readthedocs.io/) | HTTP client | Apache-2.0 |
| [keyring](https://github.com/jaraco/keyring) | System credential store | MIT |
| [accessible_output2](https://pypi.org/project/accessible-output2/) | Screen-reader output | MIT |
| [CPython](https://www.python.org/) | Runtime | Python Software Foundation License 2.0 |

Build-time only (not shipped inside the application):

| Component | Purpose | Licence |
|---|---|---|
| [PyInstaller](https://pyinstaller.org/) | Packaging | GPL-2.0-or-later with an exception permitting the distribution of non-free packaged applications |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Installer | Inno Setup licence (free for any use, including commercial) |
| [Ruff](https://docs.astral.sh/ruff/) | Linting | MIT |
| [pytest](https://pytest.org/) | Tests | MIT |
| [Pillow](https://python-pillow.org/) | Icon generation | MIT-CMU |

The licence texts of the Python dependencies are contained in their respective
distributions inside `_internal/` in an installation.

---

## Reporting a licensing problem

If you believe a component is attributed incorrectly or a notice is missing,
please open an issue at
<https://github.com/FelixSteindorff/audiflix/issues>. Licensing corrections are
treated as bugs and fixed promptly.
