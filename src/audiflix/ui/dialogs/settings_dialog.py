"""Settings dialog (Ctrl+,): adjust the important options.

Changes are written to :class:`Settings` and saved when OK is pressed.
Shortcuts are edited as text in wx accelerator syntax (``Ctrl+Space``) and are
validated before the dialog closes: an unparsable shortcut or one that is used
twice is reported, announced and the offending field is focused, instead of
silently producing a key that never works.
"""

from __future__ import annotations

import wx

from audiflix import speech
from audiflix.config import DEFAULT_SHORTCUTS, Settings
from audiflix.i18n import N_, _, available_languages
from audiflix.ui import shortcuts as shortcut_utils

#: Display names for the languages that ship with Audiflix.
LANGUAGE_NAMES = {
    "en": "English",
    "de": "Deutsch",
}

SHORTCUT_LABELS: list[tuple[str, str]] = [
    ("play_pause", N_("Play / Pause")),
    ("skip_back", N_("Skip back")),
    ("skip_forward", N_("Skip forward")),
    ("prev_chapter", N_("Previous chapter")),
    ("next_chapter", N_("Next chapter")),
    ("chapter_list", N_("Chapter list")),
    ("prev_track", N_("Previous audio file")),
    ("next_track", N_("Next audio file")),
    ("jump_to_time", N_("Jump to position")),
    ("speed_down", N_("Slower")),
    ("speed_up", N_("Faster")),
    ("speed_reset", N_("Reset speed")),
    ("volume_up", N_("Volume up")),
    ("volume_down", N_("Volume down")),
    ("announce_time", N_("Announce position")),
    ("sleep_timer", N_("Sleep timer")),
    ("announce_sleep", N_("Announce sleep timer")),
    ("add_bookmark", N_("Add bookmark")),
    ("manage_bookmarks", N_("Manage bookmarks")),
    ("media_info", N_("Media details")),
    ("select_library", N_("Select library")),
    ("settings", N_("Settings")),
    ("search", N_("Search")),
    ("quit", N_("Exit")),
]


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, settings: Settings):
        super().__init__(
            parent,
            title=_("Settings"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.settings = settings
        self.language_changed = False

        self.notebook = wx.Notebook(self)
        self.notebook.SetName(_("Settings pages"))
        self._general = _GeneralPage(self.notebook, settings)
        self._shortcuts = _ShortcutPage(self.notebook, settings)
        self.notebook.AddPage(self._general, _("General"))
        self.notebook.AddPage(self._shortcuts, _("Keyboard shortcuts"))

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 6)
        sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(sizer)
        self.SetSize((520, 520))

        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self._general.skip_back.SetFocus()

    def _on_ok(self, event):
        problem = self._shortcuts.validate()
        if problem is not None:
            message, ctrl = problem
            wx.MessageBox(message, _("Audiflix - invalid shortcut"), wx.OK | wx.ICON_WARNING, self)
            self.notebook.SetSelection(1)
            ctrl.SetFocus()
            ctrl.SelectAll()
            return
        previous_language = self.settings.get("language", "auto")
        self._general.apply()
        self._shortcuts.apply()
        self.settings.save()
        self.language_changed = self.settings.get("language", "auto") != previous_language
        self.EndModal(wx.ID_OK)


class _GeneralPage(wx.Panel):
    def __init__(self, parent, settings: Settings):
        super().__init__(parent)
        self.settings = settings
        grid = wx.FlexGridSizer(0, 2, 8, 10)
        grid.AddGrowableCol(1, 1)

        self.skip_back = self._spin(
            grid, _("Skip back (seconds):"), settings.get("skip_back_seconds", 15), 1, 600
        )
        self.skip_fwd = self._spin(
            grid, _("Skip forward (seconds):"), settings.get("skip_forward_seconds", 30), 1, 600
        )
        self.speed = self._float_spin(
            grid, _("Default speed:"), settings.get("default_speed", 1.0)
        )
        self.volume = self._spin(
            grid, _("Default volume (percent):"), settings.get("default_volume", 100), 0, 100
        )
        self.volume_step = self._spin(
            grid, _("Volume step (percent):"), settings.get("volume_step", 5), 1, 50
        )
        self.sleep_default = self._spin(
            grid, _("Sleep timer default (minutes):"),
            settings.get("sleep_timer_default_minutes", 15), 1, 240,
        )
        self.sleep_fade = self._spin(
            grid, _("Fade out before the sleep timer (seconds, 0 = off):"),
            settings.get("sleep_fade_seconds", 20), 0, 120,
        )
        self.sync = self._spin(
            grid, _("Sync progress every (seconds):"),
            settings.get("progress_sync_seconds", 15), 5, 120,
        )

        self._languages = ["auto", *available_languages()]
        language_label = wx.StaticText(self, label=_("&Language:"))
        self.language = wx.Choice(self, choices=[self._language_name(c) for c in self._languages])
        self.language.SetName(_("Language"))
        current = str(settings.get("language", "auto") or "auto")
        self.language.SetSelection(
            self._languages.index(current) if current in self._languages else 0
        )
        grid.Add(language_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.language, 1, wx.EXPAND)

        download_label = wx.StaticText(self, label=_("&Download folder:"))
        self.download_dir = wx.DirPickerCtrl(self, path=settings.get("download_dir", ""))
        self.download_dir.SetName(_("Download folder"))
        grid.Add(download_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.download_dir, 1, wx.EXPAND)

        self.announce = wx.CheckBox(self, label=_("&Announce position after skipping"))
        self.announce.SetValue(bool(settings.get("announce_on_seek", True)))

        self.announce_chapter = wx.CheckBox(
            self, label=_("Announce a new &chapter while listening")
        )
        self.announce_chapter.SetValue(bool(settings.get("announce_chapter_change", True)))

        self.remember_speed = wx.CheckBox(
            self, label=_("Remember the speed &per title")
        )
        self.remember_speed.SetValue(bool(settings.get("remember_speed_per_title", True)))

        self.media_keys = wx.CheckBox(
            self, label=_("Use the &media keys even when Audiflix is in the background")
        )
        self.media_keys.SetValue(bool(settings.get("global_media_keys", True)))

        self.forget_speeds = wx.Button(self, label=_("&Forget all saved title speeds"))
        self.forget_speeds.Bind(wx.EVT_BUTTON, self._on_forget_speeds)
        self._update_forget_button()

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)
        outer.Add(self.announce, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        outer.Add(self.announce_chapter, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        outer.Add(self.remember_speed, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        outer.Add(self.media_keys, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        outer.Add(self.forget_speeds, 0, wx.ALL, 12)
        self.SetSizer(outer)

    def _saved_speed_count(self) -> int:
        return len(self.settings.get("book_speeds") or {})

    def _update_forget_button(self) -> None:
        count = self._saved_speed_count()
        self.forget_speeds.Enable(count > 0)
        self.forget_speeds.SetLabel(
            _("&Forget all saved title speeds (%d)") % count if count
            else _("&Forget all saved title speeds")
        )

    def _on_forget_speeds(self, event) -> None:
        count = self._saved_speed_count()
        if not count:
            return
        answer = wx.MessageBox(
            _("Forget the speed saved for %d title(s)?") % count,
            _("Audiflix"), wx.YES_NO | wx.ICON_QUESTION, self,
        )
        if answer != wx.YES:
            return
        self.settings["book_speeds"] = {}
        self.settings.save()
        self._update_forget_button()
        speech.announce(_("Saved title speeds cleared."), interrupt=True)

    @staticmethod
    def _language_name(code: str) -> str:
        if code == "auto":
            return _("Automatic (system language)")
        return LANGUAGE_NAMES.get(code, code)

    def _spin(self, grid, label, value, lo, hi):
        static = wx.StaticText(self, label=label)
        ctrl = wx.SpinCtrl(self, min=lo, max=hi, initial=int(value))
        ctrl.SetName(label.replace("&", "").rstrip(":"))
        grid.Add(static, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(ctrl, 1, wx.EXPAND)
        return ctrl

    def _float_spin(self, grid, label, value):
        static = wx.StaticText(self, label=label)
        ctrl = wx.SpinCtrlDouble(self, min=0.5, max=3.5, initial=float(value), inc=0.1)
        ctrl.SetDigits(2)
        ctrl.SetName(label.replace("&", "").rstrip(":"))
        grid.Add(static, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(ctrl, 1, wx.EXPAND)
        return ctrl

    def apply(self):
        settings = self.settings
        settings["skip_back_seconds"] = self.skip_back.GetValue()
        settings["skip_forward_seconds"] = self.skip_fwd.GetValue()
        settings["default_speed"] = round(self.speed.GetValue(), 2)
        settings["default_volume"] = self.volume.GetValue()
        settings["volume_step"] = self.volume_step.GetValue()
        settings["sleep_timer_default_minutes"] = self.sleep_default.GetValue()
        settings["sleep_fade_seconds"] = self.sleep_fade.GetValue()
        settings["progress_sync_seconds"] = self.sync.GetValue()
        settings["download_dir"] = self.download_dir.GetPath()
        settings["announce_on_seek"] = self.announce.GetValue()
        settings["announce_chapter_change"] = self.announce_chapter.GetValue()
        settings["remember_speed_per_title"] = self.remember_speed.GetValue()
        settings["global_media_keys"] = self.media_keys.GetValue()
        index = self.language.GetSelection()
        if 0 <= index < len(self._languages):
            settings["language"] = self._languages[index]


class _ShortcutPage(wx.ScrolledWindow):
    """Editable list of shortcuts with validation, clear and reset."""

    def __init__(self, parent, settings: Settings):
        super().__init__(parent)
        self.settings = settings
        self.SetScrollRate(0, 10)
        self._ctrls: dict[str, wx.TextCtrl] = {}
        self._focused_key: str | None = None

        hint = wx.StaticText(
            self,
            label=_(
                "Enter shortcuts in the form Ctrl+Shift+B. Leave a field empty to "
                "disable that shortcut."
            ),
        )
        grid = wx.FlexGridSizer(0, 2, 6, 10)
        grid.AddGrowableCol(1, 1)
        stored = settings.get("shortcuts", {})
        for key, label in SHORTCUT_LABELS:
            static = wx.StaticText(self, label=f"{_(label)}:")
            ctrl = wx.TextCtrl(self, value=stored.get(key, ""))
            ctrl.SetName(_("Shortcut for %s") % _(label))
            ctrl.Bind(wx.EVT_SET_FOCUS, lambda event, k=key: self._on_focus(event, k))
            grid.Add(static, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            self._ctrls[key] = ctrl

        self.clear_button = wx.Button(self, label=_("C&lear this shortcut"))
        self.reset_button = wx.Button(self, label=_("R&eset this shortcut"))
        self.reset_all_button = wx.Button(self, label=_("Reset &all shortcuts"))
        self.clear_button.Bind(wx.EVT_BUTTON, self._on_clear)
        self.reset_button.Bind(wx.EVT_BUTTON, self._on_reset_one)
        self.reset_all_button.Bind(wx.EVT_BUTTON, self._on_reset_all)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(self.clear_button, 0, wx.RIGHT, 6)
        buttons.Add(self.reset_button, 0, wx.RIGHT, 6)
        buttons.Add(self.reset_all_button, 0)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(hint, 0, wx.ALL, 12)
        outer.Add(grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        outer.Add(buttons, 0, wx.ALL, 12)
        self.SetSizer(outer)

    # --- Buttons ----------------------------------------------------------
    def _on_focus(self, event: wx.FocusEvent, key: str) -> None:
        self._focused_key = key
        event.Skip()

    def _current_ctrl(self) -> tuple[str, wx.TextCtrl] | None:
        key = self._focused_key or (SHORTCUT_LABELS[0][0] if SHORTCUT_LABELS else None)
        if key is None:
            return None
        return key, self._ctrls[key]

    def _label_for(self, key: str) -> str:
        for action, label in SHORTCUT_LABELS:
            if action == key:
                return _(label)
        return key

    def _on_clear(self, event) -> None:
        current = self._current_ctrl()
        if current is None:
            return
        key, ctrl = current
        ctrl.SetValue("")
        ctrl.SetFocus()
        speech.announce(_("Shortcut for %s cleared.") % self._label_for(key), interrupt=True)

    def _on_reset_one(self, event) -> None:
        current = self._current_ctrl()
        if current is None:
            return
        key, ctrl = current
        default = DEFAULT_SHORTCUTS.get(key, "")
        ctrl.SetValue(default)
        ctrl.SetFocus()
        speech.announce(
            _("Shortcut for %(action)s reset to %(shortcut)s.")
            % {"action": self._label_for(key), "shortcut": default or _("not set")},
            interrupt=True,
        )

    def _on_reset_all(self, event) -> None:
        answer = wx.MessageBox(
            _("Reset all keyboard shortcuts to their default values?"),
            _("Audiflix"),
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        )
        if answer != wx.YES:
            return
        for key, ctrl in self._ctrls.items():
            ctrl.SetValue(DEFAULT_SHORTCUTS.get(key, ""))
        speech.announce(_("All shortcuts reset to their defaults."), interrupt=True)

    # --- Validation -------------------------------------------------------
    def values(self) -> dict[str, str]:
        return {key: ctrl.GetValue().strip() for key, ctrl in self._ctrls.items()}

    def validate(self) -> tuple[str, wx.TextCtrl] | None:
        """Return ``(message, control)`` for the first problem, or ``None``."""
        values = self.values()
        for key, value in values.items():
            if value and not shortcut_utils.is_valid(value):
                return (
                    _(
                        "'%(shortcut)s' is not a valid shortcut for %(action)s.\n\n"
                        "Use a form such as Ctrl+Shift+B, F5 or Alt+Right, or leave "
                        "the field empty to disable it."
                    )
                    % {"shortcut": value, "action": self._label_for(key)},
                    self._ctrls[key],
                )
        conflicts = shortcut_utils.find_conflicts(values)
        if conflicts:
            shortcut, actions = next(iter(conflicts.items()))
            names = ", ".join(self._label_for(action) for action in actions)
            return (
                _("The shortcut %(shortcut)s is assigned to several actions: %(actions)s.")
                % {"shortcut": shortcut, "actions": names},
                self._ctrls[actions[0]],
            )
        return None

    def apply(self):
        stored = dict(self.settings.get("shortcuts", {}))
        stored.update(self.values())
        self.settings["shortcuts"] = stored
