from audiflix.helpers.requests import RequestGate


def test_only_latest_request_for_same_view_can_update_it():
    gate = RequestGate()
    first = gate.issue("view:books")
    authors = gate.issue("view:authors")
    latest = gate.issue("view:books")
    assert not gate.current(first)
    assert gate.current(latest)
    assert gate.current(authors)


def test_library_change_invalidates_views_but_not_unrelated_operations():
    gate = RequestGate()
    view = gate.issue("view:books")
    download = gate.issue("download")
    gate.invalidate("view:")
    assert not gate.current(view)
    assert gate.current(download)
