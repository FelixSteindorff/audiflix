# Audiflix

**Accessible, keyboard-driven desktop player for Audiobookshelf.**

I started this project because I wanted a straightforward, accessible Audiobookshelf client for desktop. The Windows version is built with wxPython and uses libVLC for playback.

The Windows release is self-contained and brings its own audio engine, so VLC does not have to be installed separately.

> Audiflix is an **independent third-party client**. It is not affiliated with,
> endorsed by, or supported by the Audiobookshelf project. "Audiobookshelf" is
> the name of that project and is used here only to describe compatibility.

[![CI](https://github.com/FelixSteindorff/audiflix/actions/workflows/ci.yml/badge.svg)](https://github.com/FelixSteindorff/audiflix/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Features

- **Tab 1 - Overview:** continue listening, recently added, finished. Every row
  shows title, author, narrator, series and whether the title is downloaded.
- **Tab 2 - Books / Podcasts:** sorting (newest / alphabetical) and title
  search. Podcast libraries additionally offer a podcast search and the option
  to add new podcasts. The context menu of a podcast can check the feed for new
  episodes (the server downloads them), toggle automatic episode downloads and
  show podcast details. Enter opens the episode list.
- **Tab 3 - Authors:** sorting, author search, books per author.
- **Tab 4 - Series:** sorting, series search; Enter opens the books of a series
  in reading order.
- **Tab 5 - Collections:** browse and open collections.
- **Playback** through VLC with speed control, skip back/forward, chapter
  navigation (previous/next, chapter list with jump), a sleep timer, bookmarks
  (add, jump to, rename, delete) and progress synchronisation back to the
  server.
- **Item context menu:** add to collection, mark as finished, item details, go
  to author, edit media details, download.
- **Spoken feedback** for status, playback position and remaining time.
- **English and German** user interface (gettext; more languages can be added
  without touching the code).

## Accessibility

Accessibility is the reason this client exists, not a feature bolted on later.

- Every function is reachable from the **menu bar**, from a **keyboard
  shortcut**, and - where it applies to a single item - from the **context
  menu** (applications key or `Shift+F10`).
- Lists are native `wx.ListCtrl` controls, so the screen reader reads the row
  and its columns with the usual navigation keys.
- Every list, field and dialog carries an explicit **accessible name**; every
  input has an associated label with an access key (`Alt+letter`).
- Dialogs define a **default button** and respond to **Escape**, and the
  keyboard focus is placed on the most useful control when they open.
- Status messages are shown in the status bar **and** announced. Identical
  messages within one second are suppressed, so nothing is announced twice.
- Long network operations show a **"Please wait" dialog** with a Cancel button
  instead of freezing the window.
- Tested with **NVDA** on Windows. Audiflix uses
  [accessible_output2](https://pypi.org/project/accessible-output2/), which also
  supports JAWS and SAPI5; the application runs normally when no screen reader
  is present.

## Requirements

1. **Windows 10 or newer** for the installer. Audiflix also runs from source on
   Linux and macOS, where a system VLC is used.
2. An **Audiobookshelf server**, version 2.x. Both the classic long-lived token
   and the JWT access/refresh tokens introduced in ABS 2.26 are supported.
3. **Python 3.10+**, but only when running from source.

**No separate VLC installation is needed.** The Windows release contains its own
copy of the VLC libraries; see [Audio engine](#audio-engine).

## Installation

### Windows

Two downloads on the [releases
page](https://github.com/FelixSteindorff/audiflix/releases); both contain the
audio engine, so nothing else has to be installed.

**Installer** - `Audiflix-<version>-Setup.exe`. Needs no administrator rights,
creates a start menu entry and an uninstall entry.

**Portable** - `Audiflix-<version>-portable-win64.zip`. Unpack it anywhere,
including a USB stick, and run `audiflix.exe`. Nothing is installed or
registered, and no traces are left in the registry.

To check that everything works on a machine, run `audiflix-selftest.exe` from
the installation or portable folder: it loads the bundled engine and decodes a
test tone, then prints PASS or FAIL.

#### What the portable build does not carry

The application travels with you; your data stays on the machine you run it on:

| | Where it lives |
|---|---|
| Settings, logs, download registry | `%APPDATA%\audiflix` |
| Downloaded books | `%USERPROFILE%\Audiflix` (configurable) |
| Sign-in token | the Windows Credential Manager of that machine |

So a new computer starts with the default settings and asks you to sign in
again. This is deliberate: putting the token on the stick would mean writing it
somewhere Audiflix cannot protect it. Nothing secret is ever written into the
portable folder.

If you do want the settings to travel, point `AUDIFLIX_CONFIG_DIR` at a folder
inside the portable directory before starting:

```bat
set AUDIFLIX_CONFIG_DIR=%~dp0data
audiflix.exe
```

### From source

```bash
git clone https://github.com/FelixSteindorff/audiflix.git
cd audiflix
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -e .
python tools/i18n_tool.py compile   # build the translation catalogs
python tools/fetch_vlc.py           # optional: use a bundled VLC instead of the system one
python -m audiflix
```

Running from source uses `build/vlc` when `tools/fetch_vlc.py` has been run, and
otherwise falls back to a VLC installed on the system (<https://www.videolan.org/vlc/>).

On first start the sign-in dialog asks for the server address, user name and
password. With "Stay signed in" enabled the token is stored in the Windows
Credential Manager (via `keyring`).

## Audio engine

Audiflix plays audio through **libVLC, which ships inside the application**.
Users do not install VLC, and Audiflix does not touch a VLC installation that
may already be on the machine.

- A packaged build uses **only** its bundled runtime. If those files are missing
  or damaged it says so and asks you to reinstall - it never silently falls back
  to a different VLC whose plugins have not been tested with Audiflix.
- The VLC version is **not hard-coded anywhere**. It is pinned per release in
  [`vlc.lock.json`](vlc.lock.json), fetched at build time by
  `tools/fetch_vlc.py`, and verified against the SHA-256 checksum VideoLAN
  publishes next to the archive.
- Every build records what it contains: `build/vlc-version.json`,
  `audiflix.exe --version`, and **Help → About Audiflix** all report the exact
  bundled VLC version.
- Rebuilding an old tag reproduces the same VLC, because the pin is committed
  alongside the code.

VLC is licensed under the GPL v2 or later. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the licence, the trademark
notice and where to obtain the corresponding source code.

## Keyboard shortcuts

Defaults; all of them can be changed in **Settings → Keyboard shortcuts**
(`Ctrl+,`).

| Function | Shortcut |
|---|---|
| Play / Pause | `Ctrl+Space` |
| Skip back / forward | `Ctrl+Left` / `Ctrl+Right` |
| Previous / next chapter | `Ctrl+Shift+Left` / `Ctrl+Shift+Right` |
| Chapter list | `Ctrl+Shift+C` |
| Slower / faster / reset speed | `Ctrl+-` / `Ctrl++` / `Ctrl+0` |
| Volume up / down | `Ctrl+Up` / `Ctrl+Down` |
| Announce position and time remaining | `Ctrl+T` |
| Sleep timer | `Ctrl+L` |
| Add bookmark | `Ctrl+B` |
| Manage bookmarks | `Ctrl+Shift+B` |
| Media details | `Ctrl+I` |
| Select library | `Ctrl+Shift+L` |
| Settings | `Ctrl+,` |
| Search | `Ctrl+F` |
| Tabs 1-5 | `Ctrl+1` … `Ctrl+5` |
| Refresh | `F5` |
| Shortcut overview | `F1` |
| Exit | `Ctrl+Q` |

**In lists:** arrow keys navigate, **Enter** opens (a book starts playing),
**Backspace** goes back, **applications key / Shift+F10** opens the context
menu.

The shortcut editor validates what you type: an unusable combination or one
that is already assigned to another action is reported before the dialog
closes. Individual shortcuts can be cleared (an empty field disables the
shortcut) or reset, and all of them can be restored to the defaults at once.

## Library selection

`Ctrl+Shift+L` opens the selection. "All books" combines every book library.
Podcast libraries can only be selected one at a time.

## Security

- **Tokens are never written to disk in plain text.** They are stored through
  `keyring` (Windows Credential Manager, macOS Keychain, Secret Service). If no
  keyring backend is available, the token is kept in memory for the current
  session only and you are told that you will have to sign in again next time.
  A `token.json` written by a pre-release version is deleted on start-up.
- **The auth token is only ever sent to your own server.** Audiobookshelf may
  return absolute media URLs; Audiflix compares scheme, host and port against
  the configured server and refuses to attach the token to anything else.
  Downloads use the `Authorization` header rather than a URL parameter.
- **Unencrypted HTTP is called out.** Signing in over `http://` to a non-local
  host requires an explicit confirmation, because credentials and token would
  otherwise be readable on the network.
- **Logs are redacted.** Tokens in URLs and `Authorization` /
  `x-refresh-token` headers are replaced with `<redacted>` before anything is
  written, so a log file is safe to attach to a bug report.
- Access tokens are refreshed before they expire and once automatically after a
  `401`.

Please report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Where Audiflix stores data

| What | Where |
|---|---|
| Settings | `%APPDATA%\audiflix\settings.json` |
| Download registry | `%APPDATA%\audiflix\downloads.json` |
| Log files (rotating, 5 × 1 MB) | `%APPDATA%\audiflix\logs\audiflix.log` |
| Access and refresh token | System credential store (never a file) |
| Downloaded books | `%USERPROFILE%\Audiflix` (configurable) |

On Linux and macOS the config directory is `$XDG_CONFIG_HOME/audiflix` or
`~/.config/audiflix`. `AUDIFLIX_CONFIG_DIR` overrides it entirely.
**Help → Open log folder** opens the log directory.

## Building

Needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer step.

```bash
pip install -r requirements-build.txt
python build_exe.py --installer
# results: dist/Audiflix/                    (the application)
#          dist/Audiflix-<version>-Setup.exe (the installer)
```

The build

1. fetches the VLC runtime pinned in `vlc.lock.json` and verifies its checksum,
2. compiles the translation catalogs,
3. runs PyInstaller in **onedir** mode - a onefile build would unpack about
   200 MB into a temporary folder on every start,
4. runs the packaged self-test and **aborts if the bundled engine cannot decode
   audio**, so a broken bundle can never be published,
5. builds the installer and prints its SHA-256.

`requirements-build.txt` pins every Python build dependency, and
`vlc.lock.json` pins the VLC runtime, so a release can be reproduced.

Useful variants:

```bash
python build_exe.py                   # application only, no installer
python build_exe.py --skip-vlc        # reuse an already fetched build/vlc
python build_exe.py --latest-vlc      # try the newest stable VLC
python tools/fetch_vlc.py --version 3.0.21   # fetch one specific version
python tools/fetch_vlc.py --update-lock      # adopt the newest version as the pin
python tools/fetch_vlc.py --check-only       # is a newer VLC available?
```

## Tests and linting

```bash
pip install -r requirements-dev.txt
python tools/i18n_tool.py compile
pytest
ruff check .
```

The test suite runs without a server, without VLC and - apart from the shortcut
and dialog tests, which are skipped automatically - without wxPython. GitHub Actions runs
`pytest` on Linux and Windows against Python 3.10, 3.12 and 3.13, plus `ruff`.

## Translations

All source strings are English and wrapped in `_()`; German ships as a gettext
catalog.

```bash
python tools/i18n_tool.py extract   # update src/audiflix/locale/audiflix.pot
python tools/i18n_tool.py compile   # .po -> .mo
```

To add a language, copy `audiflix.pot` to
`src/audiflix/locale/<code>/LC_MESSAGES/audiflix.po`, translate it, compile, and
pick the language in the settings. The tooling only uses the standard library,
so no gettext installation is required.

## Project layout

```
src/audiflix/
  app.py            entry point (auto sign-in + MainFrame)
  config.py         settings and secure token storage
  i18n.py           gettext setup
  logging_setup.py  rotating log files, token redaction
  resources.py      bundled icon lookup
  speech.py         screen-reader output
  api/              API client and data models
  audio/            VLC player
  helpers/          shared helpers: formatting, status, text, urls, actions
  locale/           translation catalogs
  selftest.py       diagnostic for the bundled audio engine
  vlc_runtime.py    locating and loading the bundled libVLC
  ui/               MainFrame, menus, panels (tabs), dialogs
packaging/          Inno Setup script and installer notes
tools/              VLC fetcher, i18n, icon and version-resource tooling
```

## Known limitations

- **The Windows download is large** (around 90 MB installer, 200 MB installed)
  because the VLC runtime travels with it. That is the price of not asking users
  to install VLC themselves.
- **Streams are direct-play only.** Audiflix asks the server for direct play and
  does not transcode; a format the bundled VLC cannot decode will not play.
- **Only the Windows build bundles VLC.** Running from source on Linux or macOS
  uses a system VLC installation.
- Audiobookshelf access tokens are short-lived. Audiflix refreshes them and
  re-signs every track URL when a track starts, but a *single* track that plays
  for longer than the token lifetime can still fail on a late range request.
  Pressing play again resumes at the stored position.
- **Downloads are stored as the `.zip` the server returns** and are only used as
  a "downloaded" marker in the lists; playback always streams from the server.
- **The library scan** (File → Re-scan library) requires an admin account.
- Podcast libraries are selected one at a time; there is no combined
  "all podcasts" view.
- Only tested on Windows with NVDA. It should run on Linux and macOS, but the
  accessibility behaviour there is unverified.
- Changing the interface language takes effect after a restart.

## AI-assisted development

Most of the code in Audiflix was created with the help of AI coding agents. I use them heavily for implementation, refactoring and tests, while I decide what the app should do, review the changes and test the application in actual use, especially with NVDA and keyboard-only workflows.

I'm mentioning this simply to be transparent about how the project is developed.

## Contributing

Bug reports and pull requests are welcome - see
[CONTRIBUTING.md](CONTRIBUTING.md). Reports from screen-reader users are
especially valuable; please mention your screen reader, its version and what it
announced.

## License

MIT - see [LICENSE](LICENSE).
