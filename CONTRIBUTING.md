# Contributing to Audiflix

Thanks for taking the time. Audiflix is an accessibility-first project, so the
most valuable contributions are often bug reports from people who use it with a
screen reader.

## Reporting bugs

Please include:

- the Audiflix version (Help → About) and your operating system,
- your Audiobookshelf server version,
- your screen reader and its version, and **what it announced** (or failed to)
  if the report is about accessibility,
- the relevant part of `%APPDATA%\audiflix\logs\audiflix.log`
  (Help → Open log folder). Tokens are redacted automatically, but do have a
  look before posting.

For anything security-related, follow [SECURITY.md](SECURITY.md) instead of
opening an issue.

## Development setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e .
pip install -r requirements-dev.txt
python tools/i18n_tool.py compile
python -m audiflix
```

Set `AUDIFLIX_LOG_LEVEL=DEBUG` for a more talkative log, and
`AUDIFLIX_CONFIG_DIR=<path>` to keep a test configuration away from your real
one.

## Before opening a pull request

```bash
ruff check .
pytest
```

Both run in CI on Linux and Windows, so a green local run usually means a green
CI run.

## Ground rules for the code

- **Keep the layout.** `api/` talks to the server, `audio/` plays, `helpers/`
  is UI-independent logic, `ui/` is wxPython. Anything worth unit testing
  belongs outside `ui/`, so the tests keep running without a GUI toolkit.
- **Every user-visible string goes through `_()`** from `audiflix.i18n`, in
  English. Use `N_()` for strings in module-level tables that are translated
  when they are displayed. After adding strings run
  `python tools/i18n_tool.py extract`, add the German translation to
  `src/audiflix/locale/de/LC_MESSAGES/audiflix.po`, and commit both - a test
  fails if a message has no German translation.
- **No network calls on the wx main thread.** Use `ctx.run_async(...)` for
  background work with a UI callback, or `BusyDialog.run(...)` when the user has
  to wait for the result.
- **No silent failures.** `except Exception: pass` is not acceptable; catch the
  specific exception and log it (`log.exception` / `log.warning`). Never log a
  token or a URL that contains one.
- **Accessibility is part of "done".** New controls need an accessible name
  (`SetName`) and a label with an access key; new dialogs need a default button,
  an escape id and a sensible initial focus. Say things once - the status bar
  and the screen reader should not repeat each other.
- Match the surrounding style: type hints on new functions, docstrings that
  explain *why*, and comments only where the reason is not obvious from the
  code.

## Translations

To add a language, copy `src/audiflix/locale/audiflix.pot` to
`src/audiflix/locale/<code>/LC_MESSAGES/audiflix.po`, translate it, run
`python tools/i18n_tool.py compile`, add the display name to `LANGUAGE_NAMES`
in `ui/dialogs/settings_dialog.py` and select the language in the settings.
Only `.po` files are committed - `.mo` files are generated.

## Commits and pull requests

- One topic per pull request, with a short description of the user-visible
  effect.
- Update `CHANGELOG.md` under "Unreleased" for anything a user would notice.
- By contributing you agree that your work is released under the
  [MIT License](LICENSE).
