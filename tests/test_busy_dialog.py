"""Tests for the worker-thread dialog that keeps the wx main thread free.

Skipped where wxPython is not installed. These actually run a modal event loop,
which is the only way to prove the worker result really arrives on the main
thread.
"""

import threading

import pytest

wx = pytest.importorskip("wx")

from audiflix.ui.dialogs.busy_dialog import ID_FAILED, BusyDialog


@pytest.fixture(scope="module", autouse=True)
def wx_app():
    app = wx.App()
    yield app


def test_worker_result_is_returned():
    ok, result, error = BusyDialog.run(None, "Working...", lambda: 21 * 2)
    assert (ok, result, error) == (True, 42, None)


def test_worker_runs_off_the_main_thread():
    """The whole point: the blocking call must not run on the wx main thread."""
    seen = {}

    def worker():
        seen["thread"] = threading.current_thread()
        seen["is_main"] = threading.current_thread() is threading.main_thread()
        return None

    BusyDialog.run(None, "Working...", worker)
    assert seen["is_main"] is False


def test_worker_exception_is_handed_back():
    error = RuntimeError("boom")

    def worker():
        raise error

    ok, result, returned = BusyDialog.run(None, "Working...", worker)
    assert ok is False
    assert result is None
    assert returned is error


def test_failure_uses_a_dedicated_return_code():
    dlg = BusyDialog(None, "Working...", lambda: 1 / 0)
    try:
        assert dlg.ShowModal() == ID_FAILED
        assert isinstance(dlg.error, ZeroDivisionError)
    finally:
        dlg.Destroy()


def test_dialog_has_a_cancel_button_and_escape_id():
    dlg = BusyDialog(None, "Working...", lambda: None)
    try:
        assert dlg.GetEscapeId() == wx.ID_CANCEL
        assert dlg.cancel_button.GetId() == wx.ID_CANCEL
    finally:
        dlg.Destroy()
