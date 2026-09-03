# Audiflix

A lightweight, **fully keyboard-operable and screen-reader friendly** desktop
client for [Audiobookshelf](https://www.audiobookshelf.org/), built with
wxPython and VLC.

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

1. **Python 3.10+** (only for running from source)
2. **VLC media player** must be installed - `python-vlc` uses the system-wide
   libvlc, and the packaged `.exe` needs it too.
   Download: <https://www.videolan.org/vlc/>
3. An **Audiobookshelf server**, version 2.x. Both the classic long-lived token
   and the JWT access/refresh tokens introduced in ABS 2.26 are supported.

## Installation

### From source

```bash
git clone https://github.com/FelixSteindorff/audiflix.git
cd audiflix
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -e .
python tools/i18n_tool.py compile   # build the translation catalogs
python -m audiflix
```

### Windows executable

Download `audiflix.exe` from the [releases
page](https://github.com/FelixSteindorff/audiflix/releases), or build it
yourself (see [Building](#building)). VLC still has to be installed separately.

On first start the sign-in dialog asks for the server address, user name and
password. With "Stay signed in" enabled the token is stored in the Windows
Credential Manager (via `keyring`).

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

```bash
pip install -r requirements-build.txt
python build_exe.py
# result: dist/audiflix.exe   (VLC must be installed)
```

`requirements-build.txt` pins every build dependency so a release can be
reproduced. The build compiles the translation catalogs, embeds the application
icon and the Windows version resource (generated from `audiflix.__version__`),
and prints the SHA-256 of the resulting executable.

## Tests and linting

```bash
pip install -r requirements-dev.txt
python tools/i18n_tool.py compile
pytest
ruff check .
```

The test suite runs without a server, without VLC and - apart from the shortcut
tests, which are skipped automatically - without wxPython. GitHub Actions runs
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
  ui/               MainFrame, menus, panels (tabs), dialogs
tools/              i18n, icon and version-resource tooling
```

## Known limitations

- **VLC must be installed separately.** The executable does not bundle libvlc.
- **Streams are direct-play only.** Audiflix asks the server for direct play and
  does not transcode; a format your VLC cannot decode will not play.
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

## Contributing

Bug reports and pull requests are welcome - see
[CONTRIBUTING.md](CONTRIBUTING.md). Reports from screen-reader users are
especially valuable; please mention your screen reader, its version and what it
announced.

## License

MIT - see [LICENSE](LICENSE).
