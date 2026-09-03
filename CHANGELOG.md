# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-03

Audiflix becomes a self-contained Windows application: install it and nothing
else. Verified on a GitHub Actions runner with no VLC installed, where the
packaged self-test decodes audio through the bundled engine.

### Added

- **The Windows release now contains its own VLC runtime.** Audiflix no longer
  requires a separate VLC installation; libVLC and the full plugin set are
  installed as an internal part of the application.
- `tools/fetch_vlc.py` downloads the runtime at build time, verifying it against
  the SHA-256 checksum VideoLAN publishes next to the archive. It resolves the
  newest stable version by default, accepts `--version` for an exact one, and
  `--use-lock` for the version pinned in the new `vlc.lock.json`. No VLC binary
  is committed to the repository.
- Each build writes `build/vlc-version.json` (version, URL, checksum, file
  count) and ships a copy inside the runtime, so an installed Audiflix can state
  exactly which VLC it contains. The version is reported by
  `audiflix.exe --version`, in **Help → About Audiflix**, and in the log.
- `audiflix-selftest.exe` (and `audiflix --selftest` from source): a console
  diagnostic that loads the bundled engine, checks that the plugins for
  M4B/AAC/MP3/FLAC, HTTP(S) and HLS are present, and decodes a generated audio
  file. `build_exe.py` runs it automatically and refuses to publish a build that
  fails it.
- An **Inno Setup installer** (`Audiflix-<version>-Setup.exe`) with a start menu
  entry, an uninstall entry and an optional desktop icon. It installs per user by
  default, needs no administrator rights, and pre-builds the libVLC plugin cache.
  VLC is installed as an internal component only - no separate application entry.
- `THIRD_PARTY_NOTICES.md` with the VLC licence, the VideoLAN trademark notice
  and a written offer of the corresponding source code; it is installed
  alongside the application.
- A scheduled workflow that checks VideoLAN weekly for a newer stable release
  and opens a pull request updating `vlc.lock.json`. It never modifies an
  existing release.
- `--version` and `--help` command line options.

### Changed

- **The Windows build is now onedir plus an installer instead of a single
  executable.** With the VLC runtime included, a onefile build would unpack
  around 200 MB into a temporary directory on every start.
- A packaged build uses **only** its bundled runtime. If the bundled files are
  missing or unloadable it reports "The bundled audio engine could not be loaded.
  Please reinstall Audiflix." instead of silently falling back to an untested
  system VLC. Running from source still prefers `build/vlc` and falls back to a
  system installation.
- The release build workflow uses the pinned VLC version, verifies that no
  system VLC is present on the runner, and runs the packaged self-test there.

### Fixed

- python-vlc calls `sys.exit(1)` when the library named by `PYTHON_VLC_LIB_PATH`
  cannot be loaded, which would have terminated Audiflix without a message. The
  library is now probed first so the failure is reported properly.

## [0.1.0] - 2026-09-03

First public release. Audiflix was written as a private, German-only client;
this release makes it presentable, translatable and safe to hand to other
people.

### Added

- English user interface with a complete gettext setup (`audiflix.i18n`). All
  source strings are English; the original German wording ships as a
  translation catalog (`src/audiflix/locale/de`). `tools/i18n_tool.py` extracts
  the template and compiles catalogs using only the standard library, and the
  language can be chosen in the settings.
- Central logging to rotating files in `%APPDATA%\audiflix\logs`
  (5 × 1 MB) with automatic redaction of tokens in URLs and headers, plus a
  **Help → Open log folder** menu entry.
- Support for the JWT authentication introduced in Audiobookshelf 2.26:
  `x-return-tokens` on sign-in, refresh via `POST /auth/refresh`, proactive
  refresh shortly before expiry and one automatic retry after a `401`. The
  legacy long-lived `user.token` is still accepted for older servers.
- Playback URLs are re-signed when a track starts, so a long book keeps playing
  across a token refresh.
- Shortcut editor validation: unusable combinations and duplicate assignments
  are reported before the dialog closes, individual shortcuts can be cleared or
  reset, and all of them can be restored to the defaults.
- Server URL validation with `urllib.parse` and an explicit warning before
  credentials are sent over unencrypted HTTP to a non-local host.
- Progress synchronisation and "mark as finished" now address podcast episodes
  individually (`/api/me/progress/<item>/<episode>`).
- `LICENSE` (MIT), `SECURITY.md`, `CONTRIBUTING.md`, this changelog, an
  application icon, Windows version information in the executable and pinned
  build dependencies (`requirements-build.txt`).
- GitHub Actions running `pytest` (Linux and Windows, Python 3.10/3.12/3.13)
  and `ruff`, plus an on-demand Windows build workflow.

### Changed

- **Tokens are never written to disk.** The `token.json` fallback has been
  removed; without a working keyring backend the token is kept in memory for
  the current session only, and the user is told. An existing `token.json` from
  an earlier build is deleted on start-up.
- **The auth token is only attached to URLs on the configured server** (scheme,
  host and port must match). Absolute media URLs pointing elsewhere are used
  without a token, and token URLs are never logged. Downloads authenticate with
  the `Authorization` header instead of a query parameter.
- Sign-in and the automatic sign-in on start-up run on worker threads behind a
  cancellable progress dialog, so the wx main thread never blocks. The same
  applies to podcast search and adding a podcast.
- Accessibility pass over all dialogs: accessible names, associated labels with
  access keys, default and cancel buttons, sensible initial focus, and buttons
  for the bookmark actions that previously existed only as function keys.
  Duplicate screen-reader announcements are suppressed, and the media details
  dialog no longer speaks its content twice.
- Error handling: `except Exception: pass` has been replaced with specific
  exceptions and logging throughout the player, the API client, the controller
  and the configuration.
- `settings.json` is written atomically, and a corrupt file falls back to the
  defaults instead of crashing.
- Errors from Audiobookshelf are reported with useful messages (wrong password,
  expired session, insufficient permissions, unreachable server) instead of a
  generic HTTP error.

### Fixed

- Right-clicking a list fired both the context-menu and the right-click handler,
  so the menu could pop up twice.
- Starting a second title reused the previous title's media object when both
  started in their first track, so playback could continue in the old book.
- The player thread could stay dead after `stop()`, so playback did not resume.
- The "add to collection" dialog offered no name field when the library had no
  collections yet.

### Removed

- The plaintext `token.json` fallback (see above).

### Security

- See the "Changed" section: token storage, token scoping to the configured
  host, log redaction and the HTTP warning are all part of this release.

[Unreleased]: https://github.com/FelixSteindorff/audiflix/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/FelixSteindorff/audiflix/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/FelixSteindorff/audiflix/releases/tag/v0.1.0
