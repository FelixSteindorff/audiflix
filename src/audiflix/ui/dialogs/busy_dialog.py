"""A small modal dialog that runs a blocking call on a worker thread.

Network calls must never run on the wx main thread: while they block, the
window stops repainting and - much more importantly for a screen-reader user -
the application stops responding to keyboard input and NVDA reports it as not
responding.

:class:`BusyDialog` shows a short message, runs ``worker`` on a background
thread and closes itself via ``wx.CallAfter`` when the call returns. Because
``ShowModal`` keeps the event loop running, the UI stays responsive and the
user can cancel with Escape.

Typical use::

    ok, result, error = BusyDialog.run(parent, _("Signing in..."), do_login)
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import wx

from audiflix import speech
from audiflix.i18n import _
from audiflix.logging_setup import get_logger

log = get_logger(__name__)

#: Returned by ``ShowModal`` when the worker raised an exception.
ID_FAILED = wx.ID_HIGHEST + 1


class BusyDialog(wx.Dialog):
    def __init__(self, parent: wx.Window | None, message: str, worker: Callable[[], Any],
                 title: str = ""):
        super().__init__(
            parent,
            title=title or _("Please wait"),
            style=wx.CAPTION | wx.SYSTEM_MENU | wx.CLOSE_BOX,
        )
        self.result: Any = None
        self.error: BaseException | None = None
        self._worker = worker
        self._cancelled = False

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self._label = wx.StaticText(panel, label=message)
        self._label.SetName(message)
        self.cancel_button = wx.Button(panel, wx.ID_CANCEL, _("&Cancel"))
        sizer.Add(self._label, 0, wx.ALL, 16)
        sizer.Add(self.cancel_button, 0, wx.ALIGN_RIGHT | wx.ALL, 12)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        outer.Fit(self)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self._on_cancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_SHOW, self._on_show)
        self.cancel_button.SetFocus()

    def _on_show(self, event: wx.ShowEvent) -> None:
        if event.IsShown():
            speech.announce(self._label.GetLabel(), interrupt=True)
            threading.Thread(target=self._run, name="audiflix-busy", daemon=True).start()
        event.Skip()

    def _run(self) -> None:
        try:
            result = self._worker()
        except BaseException as exc:  # noqa: BLE001 - handed to the caller
            log.debug("Background call failed: %s", exc)
            wx.CallAfter(self._finish, ID_FAILED, None, exc)
            return
        wx.CallAfter(self._finish, wx.ID_OK, result, None)

    def _finish(self, code: int, result: Any, error: BaseException | None) -> None:
        # The worker cannot be interrupted; if the user cancelled we simply
        # discard its outcome.
        if self._cancelled or not self.IsModal():
            return
        self.result = result
        self.error = error
        self.EndModal(code)

    def _on_cancel(self, event: wx.CommandEvent) -> None:
        self._cancelled = True
        self.EndModal(wx.ID_CANCEL)

    @classmethod
    def run(
        cls,
        parent: wx.Window | None,
        message: str,
        worker: Callable[[], Any],
        title: str = "",
    ) -> tuple[bool, Any, BaseException | None]:
        """Run ``worker`` while showing the dialog.

        Returns ``(succeeded, result, error)``; ``succeeded`` is False both when
        the worker raised and when the user cancelled (``error`` is then None).
        """
        dlg = cls(parent, message, worker, title=title)
        try:
            code = dlg.ShowModal()
            return code == wx.ID_OK, dlg.result, dlg.error
        finally:
            dlg.Destroy()
