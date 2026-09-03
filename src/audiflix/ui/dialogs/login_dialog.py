"""Sign-in dialog: server URL plus user name and password.

The dialog performs the sign-in itself and exposes a connected
:class:`AudiobookshelfClient` on success. It is fully keyboard operable and
every field has an associated label for NVDA.

Two safety nets before any credential leaves the machine:

* the URL is parsed and normalised (:mod:`audiflix.helpers.urls`), so typos
  produce a clear message instead of a confusing network error,
* an unencrypted ``http://`` URL to a non-local host triggers an explicit
  warning that must be confirmed - the password would otherwise travel in
  plain text.
"""

from __future__ import annotations

import wx

from audiflix import speech
from audiflix.api.client import ApiError, AudiobookshelfClient
from audiflix.config import (
    Settings,
    save_tokens,
    token_storage_is_persistent,
)
from audiflix.helpers import urls as urlhelp
from audiflix.i18n import _
from audiflix.logging_setup import get_logger
from audiflix.ui.dialogs.busy_dialog import BusyDialog

log = get_logger(__name__)

URL_ERRORS = {
    "empty": lambda: _("Please enter the address of your Audiobookshelf server."),
    "scheme": lambda: _("The server address must start with http:// or https://."),
    "host": lambda: _("The server address does not contain a host name."),
    "port": lambda: _("The server address contains an invalid port number."),
    "extra": lambda: _("Please enter the server address without a query string."),
}


def storage_hint() -> str:
    """Short sentence describing where the token will be stored."""
    if token_storage_is_persistent():
        return _("The token is stored in your system credential store.")
    return _("No credential store available - the token is kept for this session only.")


class LoginDialog(wx.Dialog):
    def __init__(self, parent, settings: Settings):
        super().__init__(parent, title=_("Audiflix - Sign in"))
        self.settings = settings
        self.client: AudiobookshelfClient | None = None

        panel = wx.Panel(self)
        grid = wx.FlexGridSizer(3, 2, 8, 8)
        grid.AddGrowableCol(1, 1)

        self.server = self._add_field(
            panel, grid, _("&Server address:"), settings.get("server_url", ""),
            hint=_("For example https://abs.example.com"),
        )
        self.username = self._add_field(
            panel, grid, _("&User name:"), settings.get("username", "")
        )
        self.password = self._add_field(panel, grid, _("&Password:"), "", password=True)

        self.remember = wx.CheckBox(panel, label=_("Stay signed &in"))
        self.remember.SetValue(bool(settings.get("remember_login", True)))
        self.remember.SetName(_("Stay signed in"))

        self.storage_note = wx.StaticText(panel, label=storage_hint())

        self.message = wx.StaticText(panel, label="")
        self.message.SetForegroundColour(wx.Colour(180, 0, 0))
        self.message.SetName(_("Message"))

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self.ok_button = self.FindWindowById(wx.ID_OK, self)
        if self.ok_button:
            self.ok_button.SetLabel(_("Sign &in"))
            self.ok_button.SetDefault()

        content = wx.BoxSizer(wx.VERTICAL)
        content.Add(grid, 0, wx.EXPAND | wx.ALL, 12)
        content.Add(self.remember, 0, wx.LEFT | wx.RIGHT, 12)
        content.Add(self.storage_note, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        content.Add(self.message, 0, wx.ALL, 12)
        panel.SetSizer(content)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(outer)
        outer.Fit(self)

        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        for ctrl in (self.server, self.username, self.password):
            ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_ok)

        if self.server.GetValue():
            self.username.SetFocus()
        else:
            self.server.SetFocus()

    def _add_field(self, panel, grid, label, value, password=False, hint=""):
        static = wx.StaticText(panel, label=label)
        style = wx.TE_PROCESS_ENTER | (wx.TE_PASSWORD if password else 0)
        ctrl = wx.TextCtrl(panel, value=value, style=style)
        name = label.replace("&", "").rstrip(":")
        ctrl.SetName(name)
        if hint:
            ctrl.SetHint(hint)
            ctrl.SetToolTip(hint)
        grid.Add(static, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(ctrl, 1, wx.EXPAND)
        return ctrl

    # --- Sign-in ----------------------------------------------------------
    def _on_ok(self, event):
        raw_server = self.server.GetValue().strip()
        username = self.username.GetValue().strip()
        password = self.password.GetValue()

        try:
            server = urlhelp.normalize_server_url(raw_server)
        except urlhelp.InvalidServerUrl as exc:
            self._error(URL_ERRORS.get(str(exc), URL_ERRORS["host"])())
            self.server.SetFocus()
            return
        if not username:
            self._error(_("Please enter your user name."))
            self.username.SetFocus()
            return
        if not self._confirm_insecure(server):
            self.server.SetFocus()
            return

        self.server.SetValue(server)
        self._set_busy(True)
        ok, token, error = BusyDialog.run(
            self, _("Signing in..."), lambda: self._do_login(server, username, password)
        )
        self._set_busy(False)

        if error is not None:
            message = str(error) if isinstance(error, ApiError) else _("Sign-in failed: %s") % error
            if not isinstance(error, ApiError):
                log.exception("Unexpected sign-in failure", exc_info=error)
            self._error(message)
            self.password.SetFocus()
            self.password.SelectAll()
            return
        if not ok:
            return  # cancelled by the user

        self._finish_login(server, username, token)

    def _do_login(self, server: str, username: str, password: str) -> str:
        """Runs on a worker thread."""
        client = AudiobookshelfClient(server)
        token = client.login(username, password)
        client.fetch_me()
        self.client = client
        return token

    def _finish_login(self, server: str, username: str, token: str) -> None:
        self.settings["server_url"] = server
        self.settings["username"] = username
        self.settings["remember_login"] = self.remember.GetValue()
        self.settings.save()

        if self.remember.GetValue() and self.client is not None:
            persistent = save_tokens(server, username, token, self.client.refresh_token)
            if not persistent:
                wx.MessageBox(
                    _(
                        "No system credential store is available, so your sign-in is "
                        "kept for this session only. Audiflix never writes tokens to "
                        "disk in plain text, so you will need to sign in again next "
                        "time."
                    ),
                    _("Audiflix - sign-in not saved"),
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
        speech.announce(_("Signed in successfully."), interrupt=True)
        self.EndModal(wx.ID_OK)

    # --- Helpers ----------------------------------------------------------
    def _confirm_insecure(self, server: str) -> bool:
        """Warn before sending credentials over an unencrypted connection."""
        if not urlhelp.is_plain_http(server) or urlhelp.is_loopback(server):
            return True
        if self.settings.get("allow_insecure_http", False):
            return True
        answer = wx.MessageBox(
            _(
                "%s uses an unencrypted HTTP connection.\n\n"
                "Your user name, password and access token would be readable by "
                "anyone on the network. Use https:// whenever possible.\n\n"
                "Continue anyway?"
            ) % server,
            _("Audiflix - insecure connection"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        )
        if answer == wx.YES:
            log.warning("User confirmed an unencrypted HTTP connection to %s", server)
            self.settings["allow_insecure_http"] = True
            return True
        return False

    def _set_busy(self, busy: bool) -> None:
        for ctrl in (self.server, self.username, self.password, self.remember):
            ctrl.Enable(not busy)
        if self.ok_button:
            self.ok_button.Enable(not busy)

    def _error(self, text: str) -> None:
        self.message.SetLabel(text)
        self.Layout()
        speech.announce(text, interrupt=True, force=True)
