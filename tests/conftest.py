"""A single wx application owns all native controls in the test process."""

import pytest


@pytest.fixture(scope="session")
def wx_app():
    wx = pytest.importorskip("wx")
    app = wx.App()
    yield app
    for window in list(wx.GetTopLevelWindows()):
        if not window.IsBeingDeleted():
            window.Destroy()
    app.ProcessPendingEvents()
    app.Yield()
    app.Destroy()
