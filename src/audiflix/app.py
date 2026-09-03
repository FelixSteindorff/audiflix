"""Application entry point: wx.App, auto sign-in and MainFrame.

On start-up Audiflix tries to sign in with a stored token. If that fails (or no
token is stored) the login dialog appears. Both paths run their network calls
on worker threads so the wx main thread never blocks.
"""

from __future__ import annotations

import sys

import wx

from audiflix import APP_DISPLAY_NAME, APP_NAME, __version__, i18n, vlc_runtime
from audiflix.api.client import ApiError, AudiobookshelfClient
from audiflix.config import (
    Settings,
    clear_tokens,
    load_tokens,
    purge_legacy_token_file,
    save_tokens,
)
from audiflix.i18n import _
from audiflix.logging_setup import get_logger, setup_logging

log = get_logger(__name__)


def make_token_saver(settings: Settings):
    """Callback that persists refreshed tokens for the signed-in account."""

    def on_tokens_changed(access_token: str | None, refresh_token: str | None) -> None:
        if not access_token or not settings.get("remember_login", True):
            return
        server = settings.get("server_url", "")
        username = settings.get("username", "")
        if server and username:
            save_tokens(server, username, access_token, refresh_token)

    return on_tokens_changed


def build_client(settings: Settings, token: str, refresh_token: str | None) -> AudiobookshelfClient:
    return AudiobookshelfClient(
        settings.get("server_url", ""),
        token=token,
        refresh_token=refresh_token,
        on_tokens_changed=make_token_saver(settings),
    )


def try_auto_login(settings: Settings) -> AudiobookshelfClient | None:
    """Validate the stored token against the server. Runs on a worker thread."""
    server = settings.get("server_url", "")
    username = settings.get("username", "")
    if not server or not username:
        return None
    token, refresh_token = load_tokens(server, username)
    if not token:
        return None
    client = build_client(settings, token, refresh_token)
    try:
        client.fetch_me()
    except ApiError as exc:
        log.info("Auto sign-in failed: %s", exc)
        if exc.status in (401, 403):
            clear_tokens(server, username)
        return None
    log.info("Auto sign-in succeeded for %s", username)
    return client


def _auto_login_with_progress(settings: Settings) -> AudiobookshelfClient | None:
    """Run :func:`try_auto_login` without blocking the main thread."""
    from audiflix.ui.dialogs.busy_dialog import BusyDialog

    if not settings.get("server_url") or not settings.get("username"):
        return None
    ok, client, error = BusyDialog.run(
        None,
        _("Signing in to %s...") % settings.get("server_url", ""),
        lambda: try_auto_login(settings),
        title=APP_DISPLAY_NAME,
    )
    if error is not None:
        log.warning("Auto sign-in raised: %s", error)
        return None
    return client if ok else None


def _handle_cli(argv: list[str]) -> int | None:
    """Handle the non-GUI command line options. Returns an exit code or None."""
    if "--version" in argv:
        print(f"{APP_DISPLAY_NAME} {__version__}")
        version = vlc_runtime.bundled_version()
        print(f"Bundled VLC: {version or 'none (using a system installation)'}")
        return 0
    if "--selftest" in argv:
        from audiflix.selftest import run_selftest

        setup_logging(console=True)
        return run_selftest()
    if "--help" in argv or "-h" in argv:
        for line in (
            f"{APP_DISPLAY_NAME} {__version__}",
            "",
            "Usage: audiflix [--selftest] [--version] [--help]",
            "",
            "  --selftest   check the bundled audio engine and exit",
            "  --version    print the Audiflix and bundled VLC versions",
            "",
            "Without options Audiflix starts normally.",
        ):
            print(line)
        return 0
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    early = _handle_cli(argv)
    if early is not None:
        return early

    setup_logging()
    log.info("Starting %s %s on %s", APP_DISPLAY_NAME, __version__, sys.platform)
    log.info("Bundled VLC: %s", vlc_runtime.bundled_version() or "none (system installation)")

    settings = Settings.load()
    i18n.install(settings.get("language", "auto"))
    if purge_legacy_token_file():
        log.warning(
            "A plaintext token file from an older version was deleted; "
            "please sign in again."
        )

    app = wx.App()
    app.SetAppName(APP_NAME)
    app.SetAppDisplayName(APP_DISPLAY_NAME)

    from audiflix.ui.dialogs.login_dialog import LoginDialog
    from audiflix.ui.main_frame import MainFrame

    client = _auto_login_with_progress(settings)
    if client is None:
        dlg = LoginDialog(None, settings)
        result = dlg.ShowModal()
        client = dlg.client
        dlg.Destroy()
        if result != wx.ID_OK or client is None:
            log.info("Sign-in cancelled - exiting")
            return 0
        # Keep refreshed tokens in the credential store for the whole session.
        client.on_tokens_changed = make_token_saver(settings)

    frame = MainFrame(client, settings)
    frame.Show()
    frame.Raise()
    app.MainLoop()
    log.info("Audiflix exited normally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
