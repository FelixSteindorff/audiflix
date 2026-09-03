# Audiflix

**Accessible, keyboard-driven desktop player for Audiobookshelf.**

I started this project because I wanted a straightforward, accessible Audiobookshelf client for desktop. Audiflix is built around keyboard use and screen readers, with native wxPython controls and libVLC for playback.

The Windows builds include the audio engine, so you do not need to install VLC separately.

> Audiflix is an independent third-party client for Audiobookshelf. It is not affiliated with or supported by the Audiobookshelf project.

[![CI](https://github.com/FelixSteindorff/audiflix/actions/workflows/ci.yml/badge.svg)](https://github.com/FelixSteindorff/audiflix/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Features

- Browse books, podcasts, authors, series and collections
- Continue listening, recently added and finished views
- Search and sorting for books, podcasts, authors and series
- Podcast search and adding new podcasts
- Check podcast feeds for new episodes
- Automatic podcast episode downloads on the server
- Filter books by listening state: not started, in progress, finished, downloaded
- Playback speed control, remembered per title
- Skip forward and backward
- Chapter navigation and chapter list
- Navigation by audio file, and jumping to any position
- Sleep timer that can be extended and fades the volume out
- Bookmarks
- Playback progress sync with Audiobookshelf
- Progress shown in every list, including the remaining time
- Download books for offline listening
- Media keys that work while Audiflix is in the background
- Mark items as finished
- Edit media information
- Spoken feedback for status, playback position and remaining time
- Configurable keyboard shortcuts
- English and German interface

Most item actions are also available from the context menu.

If a stream breaks - a laptop leaving the flat's Wi-Fi, a server restarting - Audiflix reopens it at the position it left off instead of stopping.

## Accessibility

Audiflix is mainly built for people who use a keyboard and screen reader.

The interface uses native wxPython controls where possible. Lists work with the usual arrow-key navigation, context menus can be opened with the Applications key or `Shift+F10`, and the important actions are available from the menu bar or through keyboard shortcuts.

Dialogs have labelled controls, a sensible initial focus and support Escape where appropriate. Longer network operations run in the background instead of freezing the window.

Audiflix also provides spoken feedback for things such as playback position, remaining time and status messages.

The Windows version is mainly tested with **NVDA**. Screen-reader output is handled through [accessible_output2](https://pypi.org/project/accessible-output2/).

If something does not work properly with a screen reader or keyboard-only use, please open an issue and mention what your screen reader announced, or what it did not announce.

## Requirements

For the Windows builds you need:

- Windows 10 or newer
- An Audiobookshelf 2.x server

That's it. VLC is included.

Python 3.10+ is only needed when running Audiflix from source.

Audiflix supports both the older long-lived Audiobookshelf token and the newer access/refresh-token system.

## Installation

### Windows

There are two Windows downloads on the [Releases page](https://github.com/FelixSteindorff/audiflix/releases).

**Installer**

```text
Audiflix-<version>-Setup.exe
```

The installer does not need administrator rights. It adds Audiflix to the Start menu and creates an uninstall entry.

**Portable**

```text
Audiflix-<version>-portable-win64.zip
```

Unpack it anywhere and run `audiflix.exe`. The application itself does not need to be installed.

Both versions include the VLC runtime used for playback.

### Portable data

The portable build carries the application, but your personal data normally stays on the computer you run it on.

| Data | Location |
|---|---|
| Settings, logs and download registry | `%APPDATA%\audiflix` |
| Downloaded books | `%USERPROFILE%\Audiflix` by default |
| Sign-in token | Windows Credential Manager |

This also means that using the portable build on another computer will normally ask you to sign in again.

If you want the configuration itself to live next to the portable copy, set `AUDIFLIX_CONFIG_DIR` before starting Audiflix:

```bat
set AUDIFLIX_CONFIG_DIR=%~dp0data
audiflix.exe
```

Authentication tokens are still kept in the system credential store rather than written into the portable folder.

### Running from source

```bash
git clone https://github.com/FelixSteindorff/audiflix.git
cd audiflix

python -m venv .venv
.venv\Scripts\activate

pip install -e .
python tools/i18n_tool.py compile
python -m audiflix
```

On Linux or macOS:

```bash
source .venv/bin/activate
```

Running from source normally uses a system VLC installation. You can also fetch a bundled VLC runtime with:

```bash
python tools/fetch_vlc.py
```

On first start, enter your Audiobookshelf server address, username and password. If **Stay signed in** is enabled, Audiflix stores the token through the system credential store.

## Playback and VLC

Audiflix uses libVLC for playback.

The packaged Windows builds include their own VLC runtime and do not depend on whatever VLC version may or may not already be installed on the computer.

The VLC version is pinned per Audiflix release in:

```text
vlc.lock.json
```

The build checks the downloaded runtime against VideoLAN's published SHA-256 checksum. The exact bundled version is also shown in **Help → About Audiflix**.

This keeps the application code independent of one specific VLC version while still making release builds reproducible.

For VLC licensing information, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Keyboard shortcuts

These are the defaults. They can be changed under **Settings → Keyboard shortcuts**.

| Function | Shortcut |
|---|---|
| Play / Pause | `Ctrl+Space` |
| Skip back / forward | `Ctrl+Left` / `Ctrl+Right` |
| Previous / next chapter | `Ctrl+Shift+Left` / `Ctrl+Shift+Right` |
| Chapter list | `Ctrl+Shift+C` |
| Previous / next audio file | `Ctrl+Alt+Left` / `Ctrl+Alt+Right` |
| Jump to position | `Ctrl+G` |
| Slower / faster / normal speed | `Ctrl+-` / `Ctrl++` / `Ctrl+0` |
| Volume up / down | `Ctrl+Up` / `Ctrl+Down` |
| Announce position and remaining time | `Ctrl+T` |
| Sleep timer | `Ctrl+L` |
| Announce sleep timer | `Ctrl+Alt+L` |
| Add bookmark | `Ctrl+B` |
| Manage bookmarks | `Ctrl+Shift+B` |
| Media details | `Ctrl+I` |
| Select library | `Ctrl+Shift+L` |
| Settings | `Ctrl+,` |
| Search | `Ctrl+F` |
| Tabs 1–5 | `Ctrl+1` … `Ctrl+5` |
| Refresh | `F5` |
| Shortcut overview | `F1` |
| Exit | `Ctrl+Q` |

Inside lists:

- Arrow keys move through items
- Enter opens an item or starts playback
- Backspace goes back
- Applications key or `Shift+F10` opens the context menu

The shortcut editor checks for invalid or conflicting shortcuts. Shortcuts can also be cleared or reset.

The media keys on a keyboard or headset also work while Audiflix is in the background: play/pause, and next/previous chapter. If another player has already claimed a key, Audiflix leaves it alone. The whole thing can be switched off in Settings.

## Offline listening

**Download for offline listening** in the item menu or the context menu fetches every audio file of a book into a folder of its own, together with a small `audiflix.json` holding the track order and the chapter marks.

After that the book plays from those files. Audiflix still asks the server for a playback session, because that is where the resume position comes from. If the server does not answer, playback starts anyway and the position is written into the manifest instead. It is sent on the next time the server is reachable, at the latest when Audiflix starts.

A few details worth knowing:

- Lists show **Available offline** for such a book.
- **Remove download** deletes the files again and asks first.
- Playing a downloaded book while online still syncs progress normally, so the same book continues correctly in the web player or on a phone.
- Only books can be downloaded. Podcast episodes are always streamed.
- A `.zip` archive downloaded by Audiflix 0.2 still counts as downloaded but cannot be played. Downloading such a book again replaces it with a playable folder.

## Playback speed

Settings hold one default speed for everything.

While a book is playing, `Ctrl++` and `Ctrl+-` change the speed **and remember it for that book**, so a fast reader and a slow one keep their own pace. `Ctrl+0` drops a book's own speed and goes back to the default.

**Playback → Set speed for this title** does the same with an exact value and can also make it the new default.

The remembered speeds are kept in `settings.json`. They can be cleared all at once in Settings, and remembering them can be turned off there as well.

## Libraries

`Ctrl+Shift+L` opens the library selector.

**All books** combines all book libraries. Podcast libraries are currently selected individually.

## Security

Audiflix does not store authentication tokens in plain-text files.

When a supported credential store is available, tokens are stored there. On Windows this means the Windows Credential Manager. If no credential store is available, the login only lasts for the current session.

Authentication is only attached to URLs belonging to the configured Audiobookshelf server. Downloads use the `Authorization` header rather than putting the token into the URL.

Audiflix warns before sending credentials to a non-local server over plain HTTP.

Log files automatically redact authentication tokens and sensitive headers.

Access tokens are refreshed before they expire and once automatically after a `401` response.

Audiflix talks to your own server and to nothing else on its own. The update check under **Help → Check for updates** is the only request to a third party, and it only happens when you choose that menu entry.

Downloaded books carry no secrets either: the download folder holds audio files and a manifest, never a token or a user name.

Security issues should be reported as described in [SECURITY.md](SECURITY.md).

## Data locations

On Windows:

| Data | Location |
|---|---|
| Settings | `%APPDATA%\audiflix\settings.json` |
| Download registry | `%APPDATA%\audiflix\downloads.json` |
| Logs | `%APPDATA%\audiflix\logs\audiflix.log` |
| Authentication tokens | Windows Credential Manager |
| Downloaded books | `%USERPROFILE%\Audiflix` by default |

The download folder can be changed in Settings. Each downloaded book gets its own folder there, named after the book, containing its audio files and `audiflix.json`.

On Linux and macOS the configuration directory is `$XDG_CONFIG_HOME/audiflix` or `~/.config/audiflix`.

You can override it with:

```text
AUDIFLIX_CONFIG_DIR
```

The log directory can also be opened from **Help → Open log folder**.

For a bug report, **Help → Copy diagnostics** puts the version, the system, the audio engine, the credential store and whether a screen reader was found on the clipboard. It contains no server address and no user name.

## Building the Windows version

The Windows release uses PyInstaller and Inno Setup.

Install the build dependencies:

```bash
pip install -r requirements-build.txt
```

Build the application and installer:

```bash
python build_exe.py --installer
```

The results are placed in `dist`:

```text
dist\Audiflix\
dist\Audiflix-<version>-Setup.exe
```

The build process:

1. fetches the VLC runtime pinned in `vlc.lock.json`
2. verifies its checksum
3. compiles the translation catalogs
4. builds Audiflix with PyInstaller in onedir mode
5. runs the packaged audio self-test
6. builds the Inno Setup installer
7. prints the SHA-256 of the result

Useful variants:

```bash
python build_exe.py
python build_exe.py --skip-vlc
python build_exe.py --latest-vlc
python tools/fetch_vlc.py --update-lock
python tools/fetch_vlc.py --check-only
```

`--latest-vlc` is useful for testing a newer stable VLC version. Published Audiflix releases still use the pinned version from `vlc.lock.json` so old releases remain reproducible.

## Tests and linting

```bash
pip install -r requirements-dev.txt
python tools/i18n_tool.py compile
pytest
ruff check .
```

GitHub Actions runs the tests on Windows and Linux with Python 3.10, 3.12 and 3.13.

Most of the test suite does not need a running Audiobookshelf server, VLC or wxPython.

## Translations

English is the source language. German is included as a gettext translation.

After changing user-visible text:

```bash
python tools/i18n_tool.py extract
```

Compile translations with:

```bash
python tools/i18n_tool.py compile
```

Additional languages can be added under:

```text
src/audiflix/locale/<language>/LC_MESSAGES/
```

## Project structure

```text
src/audiflix/
  api/              Audiobookshelf API
  audio/            playback
  helpers/          shared helpers
  locale/           translations
  ui/               wxPython interface
  app.py            application startup
  config.py         settings and credentials
  i18n.py           translations
  logging_setup.py  logging and token redaction
  selftest.py       audio-engine self test
  updates.py        update check and diagnostics report
  vlc_runtime.py    bundled VLC handling

packaging/          Windows installer
tools/              build and translation tools
```

## Known limitations

Audiflix is still a young project, so there are a few things to be aware of:

- The Windows downloads are fairly large because VLC is included.
- Playback currently uses direct play. Audiflix does not request transcoding from the server.
- Linux and macOS builds do not currently bundle VLC.
- Only books can be downloaded for offline listening. Podcast episodes are always streamed.
- Podcast libraries cannot yet be combined into one "all podcasts" view.
- Changing the interface language currently requires a restart.
- Windows with NVDA is the main tested platform. Linux and macOS support is less tested.

If you find another limitation or bug, please open an issue.

## AI-assisted development

Most of the code in Audiflix has been created with the help of AI coding agents. I use them heavily for implementation, refactoring and tests, while I decide what the application should do, review the changes and test the result in actual use, especially with NVDA and keyboard-only workflows.

This note is here simply to be transparent about how the project is developed.

## Contributing

Bug reports and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and a few project conventions.

Accessibility reports are especially useful. If possible, mention your screen reader, its version and what Audiflix announced or failed to announce.

## License

Audiflix is released under the MIT License. See [LICENSE](LICENSE).
