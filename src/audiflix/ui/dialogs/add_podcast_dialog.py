"""Search for podcasts and add one to the library.

A search field and a search button fill a navigable results list; the selected
podcast is added to the library with "Add". Both the search and the add call
run on worker threads (see :class:`BusyDialog`), so the dialog stays responsive.
"""

from __future__ import annotations

import wx

from audiflix import speech
from audiflix.api.client import ApiError, AudiobookshelfClient
from audiflix.helpers.text import safe_folder_name
from audiflix.i18n import _
from audiflix.logging_setup import get_logger
from audiflix.ui.dialogs.busy_dialog import BusyDialog

log = get_logger(__name__)


class AddPodcastDialog(wx.Dialog):
    def __init__(self, parent, client: AudiobookshelfClient, library_id: str):
        super().__init__(
            parent,
            title=_("Search and add a podcast"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.client = client
        self.library_id = library_id
        self._results: list[dict] = []

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        search_label = wx.StaticText(panel, label=_("&Search for a podcast:"))
        self.term = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.term.SetName(_("Podcast search term"))
        self.search_btn = wx.Button(panel, label=_("Sea&rch"))
        search_row = wx.BoxSizer(wx.HORIZONTAL)
        search_row.Add(self.term, 1, wx.EXPAND | wx.RIGHT, 6)
        search_row.Add(self.search_btn, 0)

        results_label = wx.StaticText(panel, label=_("R&esults:"))
        self.results = wx.ListBox(panel, style=wx.LB_SINGLE)
        self.results.SetName(_("Podcast results"))

        self.add_btn = wx.Button(panel, wx.ID_OK, _("&Add"))
        self.add_btn.Disable()
        close_btn = wx.Button(panel, wx.ID_CANCEL, _("&Close"))
        button_row = wx.BoxSizer(wx.HORIZONTAL)
        button_row.AddStretchSpacer()
        button_row.Add(self.add_btn, 0, wx.RIGHT, 6)
        button_row.Add(close_btn, 0)

        sizer.Add(search_label, 0, wx.LEFT | wx.TOP, 8)
        sizer.Add(search_row, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(results_label, 0, wx.LEFT, 8)
        sizer.Add(self.results, 1, wx.EXPAND | wx.ALL, 8)
        sizer.Add(button_row, 0, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.SetSize((560, 460))

        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.search_btn.SetDefault()
        self.search_btn.Bind(wx.EVT_BUTTON, self._on_search)
        self.term.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.Bind(wx.EVT_BUTTON, self._on_add, id=wx.ID_OK)
        self.results.Bind(wx.EVT_LISTBOX, self._on_select)
        self.results.Bind(wx.EVT_LISTBOX_DCLICK, self._on_add)
        self.term.SetFocus()

    # --- Search -------------------------------------------------------------
    def _on_search(self, event):
        term = self.term.GetValue().strip()
        if not term:
            speech.announce(_("Please enter a search term."), interrupt=True)
            self.term.SetFocus()
            return
        ok, results, error = BusyDialog.run(
            self, _("Searching for podcasts..."), lambda: self.client.search_podcasts(term)
        )
        if error is not None:
            self._report(_("Search failed: %s") % error)
            return
        if not ok:
            return

        self._results = results or []
        labels = []
        for entry in self._results:
            title = entry.get("title") or entry.get("name") or _("(untitled)")
            author = entry.get("author") or ""
            labels.append(f"{title} - {author}" if author else title)
        self.results.Set(labels)
        self.add_btn.Enable(bool(labels))
        speech.announce(
            _("%d result(s).") % len(self._results), interrupt=True, force=True
        )
        if labels:
            self.results.SetSelection(0)
            self.add_btn.SetDefault()
            self.results.SetFocus()

    def _on_select(self, event):
        self.add_btn.Enable(self.results.GetSelection() >= 0)

    # --- Adding -------------------------------------------------------------
    def _on_add(self, event):
        index = self.results.GetSelection()
        if index < 0 or index >= len(self._results):
            speech.announce(_("Please select a podcast first."), interrupt=True)
            return
        podcast = self._results[index]
        feed_url = podcast.get("feedUrl") or podcast.get("feed_url")
        if not feed_url:
            self._report(_("This search result has no feed URL."))
            return

        ok, _result, error = BusyDialog.run(
            self,
            _("Adding the podcast..."),
            lambda: self._add_podcast(podcast, feed_url),
        )
        if error is not None:
            self._report(_("Could not add the podcast: %s") % error)
            return
        if not ok:
            return
        speech.announce(
            _("Podcast %s added.") % podcast.get("title", ""), interrupt=True, force=True
        )
        self.EndModal(wx.ID_OK)

    def _add_podcast(self, podcast: dict, feed_url: str):
        """Runs on a worker thread."""
        folders = self.client.library_folders(self.library_id)
        if not folders:
            raise ApiError(_("The library has no folder to store the podcast in."))
        folder = folders[0]
        folder_id = folder.get("id")
        if not folder_id:
            raise ApiError(_("The library folder returned by the server has no id."))
        folder_path = (folder.get("fullPath") or "").rstrip("/\\")
        title = podcast.get("title", "")
        # ABS requires a path inside the folder (folder name = podcast title)
        path = f"{folder_path}/{safe_folder_name(title)}"
        metadata = {
            "title": title,
            "author": podcast.get("author", ""),
            "feedUrl": feed_url,
            "imageUrl": podcast.get("cover", ""),
        }
        return self.client.add_podcast(self.library_id, folder_id, path, metadata)

    def _report(self, message: str) -> None:
        log.warning("%s", message)
        speech.announce(message, interrupt=True, force=True)
        wx.MessageBox(message, _("Audiflix"), wx.OK | wx.ICON_WARNING, self)
