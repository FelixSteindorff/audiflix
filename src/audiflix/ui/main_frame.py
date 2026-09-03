"""The main application window: notebook tabs, menu, status bar, shortcuts.

MainFrame connects the five tab panels with the :class:`AppContext` and
dispatches the global actions (playback, library selection, settings, item
actions) coming from the menu and the keyboard shortcuts.
"""

from __future__ import annotations

import wx

from audiflix import APP_DISPLAY_NAME, __version__, speech
from audiflix.api.client import AudiobookshelfClient
from audiflix.config import Settings, clear_tokens
from audiflix.i18n import _
from audiflix.logging_setup import get_logger, log_dir
from audiflix.resources import app_icon_path
from audiflix.ui import item_actions, menus
from audiflix.ui.controller import AppContext
from audiflix.ui.dialogs.bookmarks_dialog import BookmarksDialog
from audiflix.ui.dialogs.busy_dialog import BusyDialog
from audiflix.ui.dialogs.chapter_list_dialog import ChapterListDialog
from audiflix.ui.dialogs.library_select_dialog import LibrarySelectDialog
from audiflix.ui.dialogs.settings_dialog import SettingsDialog
from audiflix.ui.dialogs.sleep_timer_dialog import SleepTimerDialog
from audiflix.ui.panels.authors_panel import AuthorsPanel
from audiflix.ui.panels.base_list_panel import BaseListPanel
from audiflix.ui.panels.collections_panel import CollectionsPanel
from audiflix.ui.panels.library_panel import LibraryPanel
from audiflix.ui.panels.overview_panel import OverviewPanel
from audiflix.ui.panels.series_panel import SeriesPanel

log = get_logger(__name__)

TAB_OVERVIEW, TAB_LIBRARY, TAB_AUTHORS, TAB_SERIES, TAB_COLLECTIONS = range(5)


class MainFrame(wx.Frame):
    def __init__(self, client: AudiobookshelfClient, settings: Settings):
        super().__init__(None, title=f"{APP_DISPLAY_NAME} {__version__}", size=(900, 640))
        self.settings = settings
        self.ctx = AppContext(client, settings)
        self.ctx.status_cb = self._set_status
        self.ctx.auth_expired_cb = self._on_auth_expired
        self._loaded: set[int] = set()
        self._auth_prompt_open = False

        self._apply_icon()
        self.CreateStatusBar()
        self._set_status(_("Connecting..."))

        self.notebook = wx.Notebook(self)
        self.notebook.SetName(_("Sections"))
        self.overview = OverviewPanel(self.notebook, self)
        self.library = LibraryPanel(self.notebook, self)
        self.authors = AuthorsPanel(self.notebook, self)
        self.series = SeriesPanel(self.notebook, self)
        self.collections = CollectionsPanel(self.notebook, self)
        self.notebook.AddPage(self.overview, _("Overview"))
        self.notebook.AddPage(self.library, _("Books / Podcasts"))
        self.notebook.AddPage(self.authors, _("Authors"))
        self.notebook.AddPage(self.series, _("Series"))
        self.notebook.AddPage(self.collections, _("Collections"))

        self._panels = [
            self.overview, self.library, self.authors, self.series, self.collections
        ]

        menubar, self._menu_ids = menus.build_menubar(settings, self._handlers())
        self.SetMenuBar(menubar)

        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_tab_changed)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self._load_libraries()
        # Give the keyboard focus to the first tab's list, so a screen reader
        # user lands somewhere useful instead of on the frame itself.
        wx.CallAfter(self.overview.focus_default)

    def _apply_icon(self) -> None:
        """Set the window/taskbar icon when it is bundled with the package."""
        path = app_icon_path()
        if path is None:
            return
        try:
            self.SetIcon(wx.Icon(str(path), wx.BITMAP_TYPE_ICO))
        except Exception:
            log.exception("Could not load the application icon from %s", path)

    # --- Action handler table ---------------------------------------------
    def _handlers(self) -> dict:
        return {
            "refresh": self.refresh_active_panel,
            "scan_library": self.scan_library,
            "select_library": self.choose_library,
            "settings": self.open_settings,
            "logout": self.logout,
            "quit": self.Close,
            "play_pause": self.ctx.toggle_play,
            "skip_back": self.ctx.skip_back,
            "skip_forward": self.ctx.skip_forward,
            "prev_chapter": self.ctx.prev_chapter,
            "next_chapter": self.ctx.next_chapter,
            "chapter_list": self.open_chapter_list,
            "announce_chapter": self.ctx.announce_chapter,
            "speed_up": self.ctx.speed_up,
            "speed_down": self.ctx.speed_down,
            "speed_reset": self.ctx.speed_reset,
            "volume_up": self.ctx.volume_up,
            "volume_down": self.ctx.volume_down,
            "announce_time": self.ctx.announce_time,
            "sleep_timer": self.open_sleep_timer,
            "add_bookmark": self.ctx.add_bookmark,
            "manage_bookmarks": self.open_bookmarks,
            "tab_overview": lambda: self._goto_tab(TAB_OVERVIEW),
            "tab_library": lambda: self._goto_tab(TAB_LIBRARY),
            "tab_authors": lambda: self._goto_tab(TAB_AUTHORS),
            "tab_series": lambda: self._goto_tab(TAB_SERIES),
            "tab_collections": lambda: self._goto_tab(TAB_COLLECTIONS),
            "search": self.focus_search,
            "media_info": self.show_media_info,
            "ctx_collection": lambda: self._item_action(item_actions.add_to_collection),
            "ctx_finished": lambda: self._item_action(item_actions.mark_finished),
            "ctx_info": lambda: self._item_action(item_actions.show_info),
            "ctx_author": lambda: self._item_action(item_actions.go_to_author),
            "ctx_edit": lambda: self._item_action(item_actions.edit_metadata),
            "ctx_download": lambda: self._item_action(item_actions.download),
            "shortcuts": self.show_shortcuts,
            "log_folder": self.open_log_folder,
            "about": self.show_about,
        }

    # --- Loading libraries -------------------------------------------------
    def _load_libraries(self):
        def fetch():
            return self.ctx.client.libraries()

        def done(libraries):
            self.ctx.set_libraries(libraries)
            # restore the last selection, otherwise pick a sensible default
            if not self.ctx.restore_last_library():
                default_id = self.ctx.client.user.get("userDefaultLibraryId")
                book_libs = [lib for lib in libraries if lib.get("mediaType") != "podcast"]
                default = next((lib for lib in book_libs if lib["id"] == default_id), None)
                if len(book_libs) > 1:
                    self.ctx.select_all_books()
                elif book_libs:
                    self.ctx.select_library(default or book_libs[0])
                elif libraries:
                    self.ctx.select_library(libraries[0])
                else:
                    self._set_status(_("This server has no libraries."))
                    return
            self._on_library_changed()

        self.ctx.run_async(fetch, on_done=done, description="load-libraries")

    def _on_library_changed(self):
        # One message only: notify() writes the status bar *and* announces it,
        # so the screen reader does not say the same thing twice.
        self.ctx.notify(_("Library: %s") % self.ctx.active_library_label)
        self.library.update_mode()
        self._loaded.clear()
        self._load_current_tab()

    # --- Tabs --------------------------------------------------------------
    def _goto_tab(self, index: int):
        self.notebook.SetSelection(index)
        self._load_current_tab()
        self._panels[index].focus_default()

    def _on_tab_changed(self, event):
        self._load_current_tab()
        index = self.notebook.GetSelection()
        if 0 <= index < len(self._panels):
            wx.CallAfter(self._panels[index].focus_default)
        event.Skip()

    def _load_current_tab(self):
        index = self.notebook.GetSelection()
        if index in self._loaded or index < 0:
            return
        self._loaded.add(index)
        self._panels[index].load()

    def refresh_active_panel(self):
        index = self.notebook.GetSelection()
        if 0 <= index < len(self._panels):
            self._panels[index].refresh()
            self.ctx.notify(_("Refreshed."))

    # --- Global actions ----------------------------------------------------
    def choose_library(self):
        dlg = LibrarySelectDialog(self, self.ctx.libraries, self.ctx.active_library_label)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            selection = dlg.get_selection()
        finally:
            dlg.Destroy()
        if selection == "all":
            self.ctx.select_all_books()
        elif selection:
            self.ctx.select_library(selection)
        else:
            return
        self._on_library_changed()

    def scan_library(self):
        """Trigger a full server-side scan of the active library or libraries.

        ABS re-reads the files including embedded tags. The scan continues on
        the server in the background; progress while starting it is reported in
        the status bar.
        """
        lib_ids = list(self.ctx.active_library_ids)
        if not lib_ids:
            self.ctx.notify(_("No library selected."))
            return
        names = {lib["id"]: lib.get("name", lib["id"]) for lib in self.ctx.libraries}
        total = len(lib_ids)
        self.ctx.notify(_("Starting a scan of %d library/libraries...") % total)

        def do():
            for index, lib_id in enumerate(lib_ids, start=1):
                name = names.get(lib_id, lib_id)
                wx.CallAfter(
                    self._set_status,
                    _("Scanning %(name)s (%(index)d/%(total)d)...")
                    % {"name": name, "index": index, "total": total},
                )
                self.ctx.client.scan_library(lib_id)
            return total

        def done(count):
            self.ctx.notify(
                _(
                    "Library scan started for %d library/libraries. The server "
                    "re-reads the files in the background - press F5 afterwards to "
                    "refresh the list."
                ) % count
            )

        self.ctx.run_async(do, on_done=done, description="scan-library")

    def open_settings(self):
        dlg = SettingsDialog(self, self.settings)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            language_changed = dlg.language_changed
        finally:
            dlg.Destroy()
        self.ctx.player.sync_interval = float(self.settings.get("progress_sync_seconds", 15))
        self.ctx.player.set_volume(int(self.settings.get("default_volume", 100)))
        self._rebuild_menubar()
        self.ctx.notify(_("Settings saved."))
        if language_changed:
            wx.MessageBox(
                _("The new language will be used the next time Audiflix starts."),
                APP_DISPLAY_NAME, wx.OK | wx.ICON_INFORMATION, self,
            )

    def _rebuild_menubar(self):
        menubar, self._menu_ids = menus.build_menubar(self.settings, self._handlers())
        self.SetMenuBar(menubar)

    def open_sleep_timer(self):
        dlg = SleepTimerDialog(self, int(self.settings.get("sleep_timer_default_minutes", 15)))
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            minutes, until_chapter = dlg.get_selection()
        finally:
            dlg.Destroy()
        self.ctx.set_sleep_timer(minutes, until_chapter)

    def open_bookmarks(self):
        item = self.ctx.current_item
        if not item:
            self.ctx.notify(
                _("No title loaded - bookmarks belong to the title that is playing.")
            )
            return
        self.ctx.notify(_("Loading bookmarks..."))

        def show(bookmarks):
            dlg = BookmarksDialog(self, self.ctx, item, bookmarks)
            try:
                jump = dlg.ShowModal() == wx.ID_OK and dlg.jump_time is not None
                target = dlg.jump_time
            finally:
                dlg.Destroy()
            if jump:
                self.ctx.jump_to_time(target)

        self.ctx.run_async(
            lambda: self.ctx.client.bookmarks(item.id), on_done=show, description="bookmarks"
        )

    def open_chapter_list(self):
        if not self.ctx.player.has_media:
            self.ctx.notify(_("No title loaded."))
            return
        chapters = self.ctx.player.chapters
        if len(chapters) <= 1:
            self.ctx.notify(_("This title has no chapters."))
            return
        dlg = ChapterListDialog(self, chapters, self.ctx.player.current_chapter_index)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            index = dlg.selected_index()
        finally:
            dlg.Destroy()
        if index >= 0:
            self.ctx.jump_to_chapter(index)

    def focus_search(self):
        index = self.notebook.GetSelection()
        panel = self._panels[index]
        if hasattr(panel, "focus_search"):
            panel.focus_search()
        else:
            self.ctx.notify(_("This tab has no search field."))

    def show_media_info(self):
        item = self.focused_item() or self.ctx.current_item
        if not item:
            self.ctx.notify(_("No title selected."))
            return
        item_actions.show_info(self, item)

    def logout(self):
        answer = wx.MessageBox(
            _("Sign out of Audiflix?"), APP_DISPLAY_NAME,
            wx.YES_NO | wx.ICON_QUESTION, self,
        )
        if answer != wx.YES:
            return
        self._sign_out()
        self.Close()

    def _sign_out(self) -> None:
        clear_tokens(self.settings.get("server_url", ""), self.settings.get("username", ""))
        # Telling the server runs on a worker thread; the local token is gone
        # either way, so a failing request must not hold up the sign-out.
        _ok, _result, error = BusyDialog.run(
            self, _("Signing out..."), self.ctx.client.logout
        )
        if error is not None:
            log.warning("Sign-out request failed: %s", error)
        self.ctx.shutdown()

    def _on_auth_expired(self) -> None:
        """The token expired and could not be refreshed - tell the user once."""
        if self._auth_prompt_open:
            return
        self._auth_prompt_open = True
        try:
            wx.MessageBox(
                _(
                    "Your session has expired and could not be renewed.\n\n"
                    "Please restart Audiflix and sign in again."
                ),
                APP_DISPLAY_NAME, wx.OK | wx.ICON_WARNING, self,
            )
        finally:
            self._auth_prompt_open = False

    # --- Item actions from the menu ---------------------------------------
    def _item_action(self, func):
        item = self.focused_item()
        if not item:
            self.ctx.notify(_("No item selected."))
            return
        func(self, item)

    def focused_item(self):
        """The item selected in the list that currently has the focus."""
        focus = wx.Window.FindFocus()
        if isinstance(focus, wx.ListCtrl):
            panel = focus.GetParent()
            if isinstance(panel, BaseListPanel):
                selected = panel.selected()
                # Author and series rows are not items themselves.
                if hasattr(selected, "is_podcast"):
                    return selected
        return None

    # --- Navigating to an author (from item actions) ----------------------
    def open_author(self, author_id: str, author_name: str):
        self.notebook.SetSelection(TAB_AUTHORS)
        self._loaded.add(TAB_AUTHORS)
        self.authors.show_author(author_id, author_name)

    # --- Help --------------------------------------------------------------
    def show_shortcuts(self):
        from audiflix.ui.dialogs.settings_dialog import SHORTCUT_LABELS

        stored = self.settings.get("shortcuts", {})
        lines = [_("Keyboard shortcuts:"), ""]
        for key, label in SHORTCUT_LABELS:
            value = stored.get(key, "")
            lines.append(f"{_(label)}: {value or _('not set')}")
        lines += [
            "",
            _("Tabs 1 to 5: Ctrl+1 ... Ctrl+5"),
            _("Refresh: F5"),
            _(
                "In lists: arrow keys navigate, Enter opens, Backspace goes back, "
                "and the applications key or Shift+F10 opens the context menu."
            ),
        ]
        self._show_text_dialog(_("Keyboard shortcuts"), "\n".join(lines))

    def open_log_folder(self):
        """Open the folder containing the log files in the file manager."""
        path = log_dir()
        if not wx.LaunchDefaultApplication(str(path)):
            wx.MessageBox(
                _("The log files are stored in:\n%s") % path,
                APP_DISPLAY_NAME, wx.OK | wx.ICON_INFORMATION, self,
            )

    def show_about(self):
        text = "\n".join([
            f"{APP_DISPLAY_NAME} {__version__}",
            _("An accessible, keyboard-driven client for Audiobookshelf."),
            "",
            _(
                "Audiflix is an independent third-party client and is not "
                "affiliated with the Audiobookshelf project."
            ),
            _("Licensed under the MIT License."),
        ])
        self._show_text_dialog(_("About Audiflix"), text)

    def _show_text_dialog(self, title: str, text: str) -> None:
        """Read-only text in a dialog a screen reader can navigate line by line."""
        dlg = wx.Dialog(self, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        panel = wx.Panel(dlg)
        ctrl = wx.TextCtrl(
            panel, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP
        )
        ctrl.SetName(title)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(ctrl, 1, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        outer.Add(dlg.CreateStdDialogButtonSizer(wx.OK), 0, wx.EXPAND | wx.ALL, 8)
        dlg.SetSizer(outer)
        dlg.SetSize((560, 480))
        dlg.SetEscapeId(wx.ID_OK)
        ctrl.SetInsertionPoint(0)
        ctrl.SetFocus()
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    # --- Internal ----------------------------------------------------------
    def _set_status(self, text: str):
        self.SetStatusText(text)

    def _on_close(self, event):
        log.info("Closing the main window")
        speech.announce(_("Closing Audiflix."), interrupt=True)
        self.ctx.shutdown()
        event.Skip()
