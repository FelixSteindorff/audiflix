"""Central definition of the menu structure and keyboard shortcuts.

The whole application is operable from the menu bar; every entry carries its
shortcut as an accelerator so screen readers announce it and all functions are
reachable without a mouse. Shortcuts come from the settings and can therefore
be customised.

Labels are stored untranslated (marked with :func:`N_`) and translated when the
menu bar is built, so the menu follows the language chosen at start-up.
"""

from __future__ import annotations

import wx

from audiflix.config import Settings
from audiflix.i18n import N_, _
from audiflix.logging_setup import get_logger
from audiflix.ui import shortcuts

log = get_logger(__name__)

# Logical action -> (menu label, optional settings shortcut key, fixed accelerator).
# Order per list = order in the menu. None = separator.
MENUS: list[tuple[str, list]] = [
    (N_("&File"), [
        ("refresh", N_("&Refresh"), None, "F5"),
        ("scan_library", N_("Re-&scan library (re-read files and tags)"), None, None),
        None,
        ("select_library", N_("Select &library..."), "select_library", None),
        ("settings", N_("&Settings..."), "settings", None),
        None,
        ("logout", N_("Sign &out"), None, None),
        ("quit", N_("E&xit"), "quit", None),
    ]),
    (N_("&Playback"), [
        ("play_pause", N_("Play / &Pause"), "play_pause", None),
        ("skip_back", N_("Skip &back"), "skip_back", None),
        ("skip_forward", N_("Skip &forward"), "skip_forward", None),
        None,
        ("prev_chapter", N_("Previous &chapter"), "prev_chapter", None),
        ("next_chapter", N_("Ne&xt chapter"), "next_chapter", None),
        ("chapter_list", N_("Chapter &list..."), "chapter_list", None),
        ("announce_chapter", N_("Announce current chapter"), None, None),
        None,
        ("speed_up", N_("Faster"), "speed_up", None),
        ("speed_down", N_("Slower"), "speed_down", None),
        ("speed_reset", N_("Reset speed"), "speed_reset", None),
        None,
        ("volume_up", N_("Volume up"), "volume_up", None),
        ("volume_down", N_("Volume down"), "volume_down", None),
        None,
        ("announce_time", N_("Announce position and time remaining"), "announce_time", None),
        ("sleep_timer", N_("Sleep &timer..."), "sleep_timer", None),
        ("add_bookmark", N_("Add book&mark"), "add_bookmark", None),
        ("manage_bookmarks", N_("Mana&ge bookmarks..."), "manage_bookmarks", None),
    ]),
    (N_("&View"), [
        ("tab_overview", N_("Tab 1: &Overview"), None, "Ctrl+1"),
        ("tab_library", N_("Tab 2: &Books / Podcasts"), None, "Ctrl+2"),
        ("tab_authors", N_("Tab 3: &Authors"), None, "Ctrl+3"),
        ("tab_series", N_("Tab 4: Se&ries"), None, "Ctrl+4"),
        ("tab_collections", N_("Tab 5: &Collections"), None, "Ctrl+5"),
        None,
        ("search", N_("&Search"), "search", None),
        ("media_info", N_("&Media details"), "media_info", None),
    ]),
    (N_("&Item"), [
        ("ctx_collection", N_("Add to c&ollection..."), None, None),
        ("ctx_finished", N_("Mark as &finished"), None, None),
        ("ctx_info", N_("Item &details"), None, None),
        ("ctx_author", N_("Go to &author"), None, None),
        ("ctx_edit", N_("&Edit media details..."), None, None),
        ("ctx_download", N_("Do&wnload"), None, None),
    ]),
    (N_("&Help"), [
        ("shortcuts", N_("&Keyboard shortcuts"), None, "F1"),
        ("log_folder", N_("Open &log folder"), None, None),
        ("about", N_("&About Audiflix"), None, None),
    ]),
]


def build_menubar(settings: Settings, handlers: dict) -> tuple[wx.MenuBar, dict]:
    """Build the menu bar. ``handlers`` maps action_key -> callable.

    Returns ``(MenuBar, item_ids)`` where ``item_ids`` maps action_key -> wx id
    so callers can reuse entries later (in a context menu, for example).
    """
    menubar = wx.MenuBar()
    item_ids: dict[str, int] = {}
    for menu_label, entries in MENUS:
        menu = wx.Menu()
        for entry in entries:
            if entry is None:
                menu.AppendSeparator()
                continue
            action, label, shortcut_key, fixed_accel = entry
            accel = settings.shortcut(shortcut_key) if shortcut_key else (fixed_accel or "")
            if accel and not shortcuts.is_valid(accel):
                log.warning("Ignoring invalid shortcut '%s' for action %s", accel, action)
                accel = ""
            text = _(label)
            if accel:
                text = f"{text}\t{accel}"
            item = menu.Append(wx.ID_ANY, text)
            item_ids[action] = item.GetId()
            handler = handlers.get(action)
            if handler:
                menu.Bind(wx.EVT_MENU, _wrap(action, handler), item)
            else:
                log.debug("No handler bound for menu action %s", action)
        menubar.Append(menu, _(menu_label))
    return menubar, item_ids


def _wrap(action: str, handler):
    def on_event(event):
        try:
            handler()
        except Exception:
            # A crashing menu handler would otherwise take down the event loop.
            log.exception("Menu action '%s' failed", action)

    return on_event


def accel_to_entry(shortcut: str, command_id: int) -> wx.AcceleratorEntry | None:
    """Convert a shortcut string (e.g. 'Ctrl+Space') into an AcceleratorEntry."""
    return shortcuts.to_entry(shortcut, command_id)


def is_valid_shortcut(shortcut: str) -> bool:
    """True when wx can turn ``shortcut`` into a working accelerator."""
    return shortcuts.is_valid(shortcut)
