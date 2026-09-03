#!/usr/bin/env python3
"""One-off helper that seeds locale/de/LC_MESSAGES/audiflix.po.

Audiflix started out as a German-only application. When the sources were
translated to English for the public release, the original German wording was
kept here so it could be shipped as a proper gettext catalog instead of being
lost. Regular translation updates happen in the .po file itself; this script
only exists to document where the initial German catalog came from.

    python tools/_seed_german_catalog.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from i18n_tool import LOCALE_DIR, po_string

PLURALS: dict[str, tuple[str, str]] = {
    "%d hour": ("%d Stunde", "%d Stunden"),
    "%d minute": ("%d Minute", "%d Minuten"),
    "%d second": ("%d Sekunde", "%d Sekunden"),
}

TRANSLATIONS: dict[str, str] = {
    " (podcast)": " (Podcast)",
    "%(collection)s (%(count)d)": "%(collection)s (%(count)d)",
    "%(kind)s (%(count)d) - search '%(term)s'": "%(kind)s (%(count)d) - Suche '%(term)s'",
    "%(title)s added to collection %(collection)s.":
        "%(title)s zur Sammlung %(collection)s hinzugefügt.",
    "%(title)s: %(count)d new episode(s) found - the server is downloading them.":
        "%(title)s: %(count)d neue Episode(n) gefunden - der Server lädt sie herunter.",
    "%d result(s).": "%d Treffer.",
    "%s downloaded.": "%s heruntergeladen.",
    "%s has already been downloaded.": "%s ist bereits heruntergeladen.",
    "%s marked as finished.": "%s als abgeschlossen markiert.",
    "%s marked as not finished.": "%s als nicht abgeschlossen markiert.",
    "%s uses an unencrypted HTTP connection.\n\nYour user name, password and access "
    "token would be readable by anyone on the network. Use https:// whenever possible."
    "\n\nContinue anyway?":
        "%s verwendet eine unverschlüsselte HTTP-Verbindung.\n\nBenutzername, Passwort "
        "und Zugriffstoken wären für alle im Netzwerk lesbar. Verwenden Sie nach "
        "Möglichkeit https://.\n\nTrotzdem fortfahren?",
    "%s: automatic episode download turned off.":
        "%s: Automatischer Episoden-Download ausgeschaltet.",
    "%s: automatic episode download turned on.":
        "%s: Automatischer Episoden-Download eingeschaltet.",
    "%s: no new episodes.": "%s: keine neuen Episoden.",
    "%sx": "%s-fach",
    "&About Audiflix": "&Über Audiflix",
    "&Add": "&Hinzufügen",
    "&Announce position after skipping": "Position nach Springen &ansagen",
    "&Author:": "&Autor:",
    "&Bookmarks (Enter jumps to the position, F2 renames, Delete removes):":
        "&Lesezeichen (Enter springt zur Stelle, F2 benennt um, Entf löscht):",
    "&Cancel": "&Abbrechen",
    "&Chapters (%d):": "&Kapitel (%d):",
    "&Close": "&Schließen",
    "&Collection:": "&Sammlung:",
    "&Delete": "&Löschen",
    "&Description:": "&Beschreibung:",
    "&Details:": "&Details:",
    "&Download folder:": "&Download-Ordner:",
    "&Edit media details...": "Medieninformationen &bearbeiten...",
    "&File": "&Datei",
    "&Go to": "&Anspringen",
    "&Help": "&Hilfe",
    "&Item": "&Titel",
    "&Keyboard shortcuts": "&Tastenkürzel",
    "&Language:": "&Sprache:",
    "&Library:": "&Bibliothek:",
    "&Media details": "&Medieninfos",
    "&Name of the new collection:": "&Name der neuen Sammlung:",
    "&Narrator:": "&Sprecher:",
    "&Password:": "&Passwort:",
    "&Playback": "&Wiedergabe",
    "&Publisher:": "&Verlag:",
    "&Refresh": "&Aktualisieren",
    "&Search": "&Suchen",
    "&Search for a podcast:": "Podcast &suchen:",
    "&Server address:": "&Server-Adresse:",
    "&Settings...": "&Einstellungen...",
    "&Sort:": "&Sortieren:",
    "&Subtitle:": "&Untertitel:",
    "&Title:": "&Titel:",
    "&User name:": "&Benutzername:",
    "&View": "&Ansicht",
    "'%(shortcut)s' is not a valid shortcut for %(action)s.\n\nUse a form such as "
    "Ctrl+Shift+B, F5 or Alt+Right, or leave the field empty to disable it.":
        "'%(shortcut)s' ist kein gültiges Tastenkürzel für %(action)s.\n\nVerwenden Sie "
        "eine Schreibweise wie Ctrl+Shift+B, F5 oder Alt+Right, oder lassen Sie das Feld "
        "leer, um das Kürzel abzuschalten.",
    "(unknown)": "(unbekannt)",
    "(unnamed)": "(ohne Namen)",
    "(untitled)": "(ohne Titel)",
    "+ Create a new collection...": "+ Neue Sammlung anlegen...",
    "10 minutes": "10 Minuten",
    "15 minutes": "15 Minuten",
    "30 minutes": "30 Minuten",
    "45 minutes": "45 Minuten",
    "5 minutes": "5 Minuten",
    "60 minutes": "60 Minuten",
    "About Audiflix": "Über Audiflix",
    "Add book&mark": "&Lesezeichen setzen",
    "Add bookmark": "Lesezeichen setzen",
    "Add to c&ollection...": "Zu Sammlung &hinzufügen...",
    "Add to collection": "Zu Sammlung hinzufügen",
    "Add to collection...": "Zu Sammlung hinzufügen...",
    "Adding the podcast...": "Podcast wird hinzugefügt...",
    "All books": "Alle Bücher",
    "All shortcuts reset to their defaults.":
        "Alle Tastenkürzel auf die Standardwerte zurückgesetzt.",
    "Alphabetical": "Alphabetisch",
    "An accessible, keyboard-driven client for Audiobookshelf.":
        "Ein barrierefreier, per Tastatur bedienbarer Client für Audiobookshelf.",
    "Announce current chapter": "Aktuelles Kapitel ansagen",
    "Announce position": "Position ansagen",
    "Announce position and time remaining": "Position und Restdauer ansagen",
    "Audiflix": "Audiflix",
    "Audiflix - Sign in": "Audiflix - Anmeldung",
    "Audiflix - insecure connection": "Audiflix - unsichere Verbindung",
    "Audiflix - invalid shortcut": "Audiflix - ungültiges Tastenkürzel",
    "Audiflix - sign-in not saved": "Audiflix - Anmeldung nicht gespeichert",
    "Audio engine: VLC installed on this system (VideoLAN)":
        "Audio-Engine: auf diesem System installiertes VLC (VideoLAN)",
    "Audio engine: bundled VLC %s (VideoLAN)":
        "Audio-Engine: mitgeliefertes VLC %s (VideoLAN)",
    "Audiflix is an independent third-party client and is not affiliated with the "
    "Audiobookshelf project.":
        "Audiflix ist ein unabhängiger Client von Dritten und steht in keiner Verbindung "
        "zum Audiobookshelf-Projekt.",
    "Author": "Autor",
    "Authors": "Autoren",
    "Authors (%d)": "Autoren (%d)",
    "Automatic (system language)": "Automatisch (Systemsprache)",
    "Bookmark %d": "Lesezeichen %d",
    "Bookmark deleted.": "Lesezeichen gelöscht.",
    "Bookmark renamed.": "Lesezeichen umbenannt.",
    "Bookmark set at %s.": "Lesezeichen bei %s gesetzt.",
    "Bookmarks": "Lesezeichen",
    "Bookmarks - %s": "Lesezeichen - %s",
    "Books": "Bücher",
    "Books / Podcasts": "Bücher / Podcasts",
    "Books by %(author)s (%(count)d)": "Bücher von %(author)s (%(count)d)",
    "Books by this author": "Bücher des Autors",
    "Books in this collection": "Bücher der Sammlung",
    "Books in this series": "Bücher der Reihe",
    "C&lear this shortcut": "Kürzel &leeren",
    "Cannot reach the server: %s": "Server nicht erreichbar: %s",
    "Chapter": "Kapitel",
    "Chapter %(index)d of %(total)d: %(title)s": "Kapitel %(index)d von %(total)d: %(title)s",
    "Chapter %d": "Kapitel %d",
    "Chapter &list...": "Kapite&lliste...",
    "Chapter list": "Kapitelliste",
    "Chapters": "Kapitel",
    "Check for new episodes": "Nach neuen Episoden suchen",
    "Checking %s for new episodes...": "Suche neue Episoden von %s...",
    "Closing Audiflix.": "Audiflix wird beendet.",
    "Collection": "Sammlung",
    "Collection %(collection)s created with %(title)s.":
        "Sammlung %(collection)s mit %(title)s angelegt.",
    "Collections": "Sammlungen",
    "Collections (%d)": "Sammlungen (%d)",
    "Connecting...": "Verbinde...",
    "Continue listening": "Weiterhören",
    "Continue listening (%d)": "Weiterhören (%d)",
    "Could not add the podcast: %s": "Podcast konnte nicht hinzugefügt werden: %s",
    "Could not write the downloaded file: %s":
        "Heruntergeladene Datei konnte nicht geschrieben werden: %s",
    "Default speed:": "Standard-Tempo:",
    "Default volume (percent):": "Standard-Lautstärke (Prozent):",
    'Delete the bookmark "%s"?': 'Lesezeichen "%s" löschen?',
    "Description:": "Beschreibung:",
    "Do&wnload": "Her&unterladen",
    "Download": "Herunterladen",
    "Download failed (HTTP %d).": "Download fehlgeschlagen (HTTP %d).",
    "Download folder": "Download-Ordner",
    "Downloaded": "Heruntergeladen",
    "Downloading %s...": "Lade %s herunter...",
    "Duration": "Dauer",
    "E&xit": "&Beenden",
    "Edit media details - %s": "Medieninformationen bearbeiten - %s",
    "Edit media details...": "Medieninformationen bearbeiten...",
    "Enter shortcuts in the form Ctrl+Shift+B. Leave a field empty to disable that "
    "shortcut.":
        "Tastenkürzel in der Form Ctrl+Shift+B eingeben. Ein leeres Feld schaltet das "
        "Kürzel ab.",
    "Episode": "Episode",
    "Episodes": "Episoden",
    "Episodes: %(title)s (%(count)d)": "Episoden: %(title)s (%(count)d)",
    "Error: %s": "Fehler: %s",
    "Exit": "Beenden",
    "Faster": "Schneller",
    "Finished": "Abgeschlossen",
    "Finished (%d)": "Abgeschlossen (%d)",
    "Finished, %s": "Abgeschlossen, %s",
    "For example https://abs.example.com": "Zum Beispiel https://abs.example.com",
    "General": "Allgemein",
    "Genres": "Genres",
    "Go to &author": "Zum &Autor",
    "Go to author": "Zum Autor",
    "In lists: arrow keys navigate, Enter opens, Backspace goes back, and the "
    "applications key or Shift+F10 opens the context menu.":
        "In Listen: Pfeiltasten navigieren, Enter öffnet, Backspace geht zurück, die "
        "Anwendungstaste oder Shift+F10 öffnet das Kontextmenü.",
    "Invalid username or password.": "Benutzername oder Passwort ist falsch.",
    "Item &details": "Titel&infos",
    "Item details": "Titelinfos",
    "Keyboard shortcuts": "Tastenkürzel",
    "Keyboard shortcuts:": "Tastenkürzel:",
    "Language": "Sprache",
    "Library scan started for %d library/libraries. The server re-reads the files in "
    "the background - press F5 afterwards to refresh the list.":
        "Bibliotheks-Scan für %d Bibliothek(en) gestartet. Der Server liest die Dateien "
        "im Hintergrund neu ein - danach F5 drücken, um die Liste zu aktualisieren.",
    "Library selection": "Bibliotheksauswahl",
    "Library: %s": "Bibliothek: %s",
    "Licensed under the MIT License.": "Lizenziert unter der MIT-Lizenz.",
    "List": "Liste",
    "Loading %s...": "Lade %s...",
    "Loading bookmarks...": "Lade Lesezeichen...",
    "Loading episodes of %s...": "Lade Episoden von %s...",
    "Looking up the author...": "Suche Autor...",
    "Mana&ge bookmarks...": "Lesezeichen ver&walten...",
    "Manage bookmarks": "Lesezeichen verwalten",
    "Mark as &finished": "Als &abgeschlossen markieren",
    "Mark as finished": "Als abgeschlossen markieren",
    "Media details": "Medieninfos",
    "Media details - %s": "Medieninfos - %s",
    "Media details for %s saved.": "Medieninformationen zu %s gespeichert.",
    "Message": "Meldung",
    "Name of the new collection": "Name der neuen Sammlung",
    "Narrator": "Sprecher",
    "Ne&xt chapter": "Nächstes Ka&pitel",
    "Network error during download: %s": "Netzwerkfehler beim Download: %s",
    "Network error: %s": "Netzwerkfehler: %s",
    "New title:": "Neuer Titel:",
    "Newest": "Neu",
    "Next chapter": "Nächstes Kapitel",
    "No author is linked to this item.": "Kein Autor verknüpft.",
    "No bookmark selected.": "Kein Lesezeichen ausgewählt.",
    "No bookmarks for this title yet.": "Noch keine Lesezeichen für diesen Titel.",
    "No chapter.": "Kein Kapitel.",
    "No credential store available - the token is kept for this session only.":
        "Kein Anmeldeinformationsspeicher verfügbar - der Token gilt nur für diese Sitzung.",
    "No item selected.": "Kein Titel ausgewählt.",
    "No library selected.": "Keine Bibliothek ausgewählt.",
    "No playable audio files were found.": "Keine abspielbaren Audiodaten gefunden.",
    "No system credential store is available, so your sign-in is kept for this session "
    "only. Audiflix never writes tokens to disk in plain text, so you will need to sign "
    "in again next time.":
        "Es ist kein Anmeldeinformationsspeicher des Systems verfügbar, daher gilt die "
        "Anmeldung nur für diese Sitzung. Audiflix speichert Tokens niemals im Klartext "
        "auf der Festplatte - beim nächsten Start ist eine erneute Anmeldung nötig.",
    "No title loaded - bookmarks belong to the title that is playing.":
        "Kein Titel geladen - Lesezeichen beziehen sich auf den laufenden Titel.",
    "No title loaded.": "Kein Titel geladen.",
    "No title selected.": "Kein Titel ausgewählt.",
    "Not downloaded": "Nicht heruntergeladen",
    "Not signed in.": "Nicht angemeldet.",
    "Off": "Aus",
    "Open &log folder": "&Log-Ordner öffnen",
    "Overview": "Übersicht",
    "Paused": "Pausiert",
    "Play / &Pause": "Play / &Pause",
    "Play / Pause": "Play / Pause",
    "Playback failed. The stream may have expired - please try again.":
        "Wiedergabe fehlgeschlagen. Möglicherweise ist der Stream abgelaufen - bitte "
        "erneut versuchen.",
    "Playback reported repeated errors. See the log file.":
        "Die Wiedergabe meldet wiederholt Fehler. Details stehen in der Logdatei.",
    "Playing": "Wiedergabe",
    "Playing: %s": "Wiedergabe: %s",
    "Please enter a search term.": "Bitte einen Suchbegriff eingeben.",
    "Please enter the address of your Audiobookshelf server.":
        "Bitte die Adresse des Audiobookshelf-Servers eingeben.",
    "Please enter the server address without a query string.":
        "Bitte die Server-Adresse ohne Query-String eingeben.",
    "Please enter your user name.": "Bitte den Benutzernamen eingeben.",
    "Please select a podcast first.": "Bitte zuerst einen Podcast auswählen.",
    "Please wait": "Bitte warten",
    "Podcast %s added.": "Podcast %s hinzugefügt.",
    "Podcast details": "Podcast-Infos",
    "Podcast results": "Podcast-Ergebnisse",
    "Podcast search term": "Podcast-Suchbegriff",
    "Podcasts": "Podcasts",
    "Position": "Position",
    "Position %(position)s, %(remaining)s remaining":
        "Position %(position)s, noch %(remaining)s verbleibend",
    "Press Enter to search": "Zum Suchen Enter drücken",
    "Previous &chapter": "Voriges &Kapitel",
    "Previous chapter": "Voriges Kapitel",
    "Published": "Veröffentlicht",
    "Published &year:": "Erscheinungs&jahr:",
    "Publisher": "Verlag",
    "R&eset this shortcut": "Kürzel zurücks&etzen",
    "R&esults:": "&Ergebnisse:",
    "Re&name": "Umbe&nennen",
    "Re-&scan library (re-read files and tags)":
        "Bibliothek &neu scannen (Dateien und Tags neu einlesen)",
    "Recently added": "Zuletzt hinzugefügt",
    "Recently added (%d)": "Zuletzt hinzugefügt (%d)",
    "Refresh: F5": "Aktualisieren: F5",
    "Refreshed.": "Aktualisiert.",
    "Rename bookmark": "Lesezeichen umbenennen",
    "Reset &all shortcuts": "&Alle Kürzel zurücksetzen",
    "Reset all keyboard shortcuts to their default values?":
        "Alle Tastenkürzel auf die Standardwerte zurücksetzen?",
    "Reset speed": "Tempo zurücksetzen",
    "Scanning %(name)s (%(index)d/%(total)d)...":
        "Scanne %(name)s (%(index)d/%(total)d)...",
    "Sea&rch": "S&uchen",
    "Sea&rch:": "S&uche:",
    "Search": "Suchen",
    "Search and &add podcast...": "Podcast suchen und &hinzufügen...",
    "Search and add a podcast": "Podcast suchen und hinzufügen",
    "Search authors": "Autor suchen",
    "Search failed: %s": "Suche fehlgeschlagen: %s",
    "Search podcasts": "Podcast suchen",
    "Search series": "Reihe suchen",
    "Search titles": "Titel suchen",
    "Searching for podcasts...": "Suche Podcasts...",
    "Sections": "Bereiche",
    "Select &library...": "&Bibliothek wählen...",
    "Select library": "Bibliothek wählen",
    "Series": "Reihe",
    "Series %(name)s (%(count)d)": "Reihe %(name)s (%(count)d)",
    "Series (%d)": "Reihen (%d)",
    "Server error %(status)d: %(detail)s": "Serverfehler %(status)d: %(detail)s",
    "Server error %d.": "Serverfehler %d.",
    "Settings": "Einstellungen",
    "Settings pages": "Einstellungsseiten",
    "Settings saved.": "Einstellungen gespeichert.",
    "Shortcut for %(action)s reset to %(shortcut)s.":
        "Kürzel für %(action)s auf %(shortcut)s zurückgesetzt.",
    "Shortcut for %s": "Tastenkürzel %s",
    "Shortcut for %s cleared.": "Kürzel für %s geleert.",
    "Show books": "Bücher anzeigen",
    "Sign &in": "&Anmelden",
    "Sign &out": "Ab&melden",
    "Sign out of Audiflix?": "Wirklich von Audiflix abmelden?",
    "Sign-in failed: %s": "Anmeldung fehlgeschlagen: %s",
    "Sign-in failed: the server did not return a token.":
        "Anmeldung fehlgeschlagen: Der Server hat keinen Token geliefert.",
    "Signed in successfully.": "Anmeldung erfolgreich.",
    "Signing in to %s...": "Melde bei %s an...",
    "Signing in...": "Anmeldung läuft...",
    "Signing out...": "Abmeldung läuft...",
    "Skip &back": "&Zurück springen",
    "Skip &forward": "&Vor springen",
    "Skip back": "Zurück springen",
    "Skip back (seconds):": "Zurück springen (Sekunden):",
    "Skip forward": "Vor springen",
    "Skip forward (seconds):": "Vor springen (Sekunden):",
    "Sleep &timer...": "&Sleeptimer...",
    "Sleep timer": "Sleeptimer",
    "Sleep timer &length:": "&Länge des Sleeptimers:",
    "Sleep timer default (minutes):": "Sleeptimer-Standard (Minuten):",
    "Sleep timer elapsed - playback paused.":
        "Sleeptimer abgelaufen - Wiedergabe pausiert.",
    "Sleep timer length": "Sleeptimer-Länge",
    "Sleep timer off": "Sleeptimer ausgeschaltet",
    "Sleep timer: %d minutes": "Sleeptimer: %d Minuten",
    "Sleep timer: until the end of the chapter": "Sleeptimer: bis Kapitelende",
    "Slower": "Langsamer",
    "Sort authors": "Sortierung Autoren",
    "Sort order": "Sortierung",
    "Sort series": "Sortierung Reihen",
    "Speed %s": "Tempo %s",
    "Start": "Beginn",
    "Starting a scan of %d library/libraries...":
        "Starte Scan für %d Bibliothek(en)...",
    "Status": "Status",
    "Stay signed &in": "Angemeldet &bleiben",
    "Stay signed in": "Angemeldet bleiben",
    "Subtitle": "Untertitel",
    "Sync progress every (seconds):": "Fortschritt synchronisieren alle (Sekunden):",
    "Tab 1: &Overview": "Tab 1: &Übersicht",
    "Tab 2: &Books / Podcasts": "Tab 2: &Bücher / Podcasts",
    "Tab 3: &Authors": "Tab 3: &Autoren",
    "Tab 4: Se&ries": "Tab 4: &Reihen",
    "Tab 5: &Collections": "Tab 5: &Sammlungen",
    "Tabs 1 to 5: Ctrl+1 ... Ctrl+5": "Tabs 1 bis 5: Ctrl+1 ... Ctrl+5",
    "The audio engine could not be started. Please reinstall the VLC media player.":
        "Die Audio-Engine konnte nicht gestartet werden. Bitte den VLC Media Player neu "
        "installieren.",
    "The audio engine could not be started: %s":
        "Die Audio-Engine konnte nicht gestartet werden: %s",
    "The bundled audio engine could not be loaded. Please reinstall Audiflix.":
        "Die mitgelieferte Audio-Engine konnte nicht geladen werden. Bitte Audiflix neu "
        "installieren.",
    "The library folder returned by the server has no id.":
        "Der vom Server gelieferte Bibliotheksordner hat keine ID.",
    "The library has no folder to store the podcast in.":
        "Die Bibliothek hat keinen Ordner, in dem der Podcast abgelegt werden kann.",
    "The log files are stored in:\n%s": "Die Logdateien liegen unter:\n%s",
    "The new language will be used the next time Audiflix starts.":
        "Die neue Sprache wird beim nächsten Start von Audiflix verwendet.",
    "The server address contains an invalid port number.":
        "Die Server-Adresse enthält eine ungültige Portnummer.",
    "The server address does not contain a host name.":
        "Die Server-Adresse enthält keinen Hostnamen.",
    "The server address must start with http:// or https://.":
        "Die Server-Adresse muss mit http:// oder https:// beginnen.",
    "The server did not respond in time.":
        "Der Server hat nicht rechtzeitig geantwortet.",
    "The server does not know this address (404).":
        "Der Server kennt diese Adresse nicht (404).",
    "The shortcut %(shortcut)s is assigned to several actions: %(actions)s.":
        "Das Kürzel %(shortcut)s ist mehreren Aktionen zugewiesen: %(actions)s.",
    "The token is stored in your system credential store.":
        "Der Token wird im Anmeldeinformationsspeicher des Systems abgelegt.",
    "This search result has no feed URL.": "Zu diesem Treffer gibt es keine Feed-URL.",
    "This server has no libraries.": "Dieser Server hat keine Bibliotheken.",
    "This tab has no search field.": "Dieser Tab hat kein Suchfeld.",
    "This title has no chapters.": "Dieser Titel hat keine Kapitel.",
    "This title has no playable audio files.":
        "Dieser Titel hat keine abspielbaren Audiodateien.",
    "Title": "Titel",
    "Title finished.": "Titel beendet.",
    "Toggle automatic episode download": "Automatischen Episoden-Download umschalten",
    "Total duration: %s": "Gesamtdauer: %s",
    "Until the end of the chapter": "Bis Kapitelende",
    "Updating the setting for %s...": "Aktualisiere Einstellung für %s...",
    "VLC is licensed under the GNU General Public License v2 or later. See "
    "THIRD_PARTY_NOTICES for the licence text and how to obtain the source code.":
        "VLC steht unter der GNU General Public License v2 oder neuer. Den Lizenztext "
        "und Hinweise zum Bezug des Quellcodes finden Sie in THIRD_PARTY_NOTICES.",
    "VLC could not be started. Please reinstall the VLC media player.":
        "VLC konnte nicht gestartet werden. Bitte den VLC Media Player neu installieren.",
    "VLC could not be started: %s": "VLC konnte nicht gestartet werden: %s",
    "VLC is not available. Please install the VLC media player "
    "(https://www.videolan.org).":
        "VLC ist nicht verfügbar. Bitte den VLC Media Player installieren "
        "(https://www.videolan.org).",
    "Volume %d percent": "Lautstärke %d Prozent",
    "Volume down": "Leiser",
    "Volume step (percent):": "Lautstärke-Schritt (Prozent):",
    "Volume up": "Lauter",
    "Your account is not allowed to perform this action.":
        "Ihr Konto darf diese Aktion nicht ausführen.",
    "Your session has expired and could not be renewed.\n\nPlease restart Audiflix and "
    "sign in again.":
        "Ihre Sitzung ist abgelaufen und konnte nicht erneuert werden.\n\nBitte Audiflix "
        "neu starten und erneut anmelden.",
    "Your session has expired. Please sign in again.":
        "Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
    "by %s": "von %s",
    "finished": "abgeschlossen",
    "narrated by %s": "gelesen von %s",
    "not set": "nicht belegt",
    "series %s": "Reihe %s",
}

HEADER = """# German translation for Audiflix.
# Copyright (C) 2026 Felix Steindorff
# This file is distributed under the same MIT license as Audiflix.
#
msgid ""
msgstr ""
"Project-Id-Version: audiflix\\n"
"POT-Creation-Date: {date}\\n"
"PO-Revision-Date: {date}\\n"
"Last-Translator: Felix Steindorff\\n"
"Language-Team: German\\n"
"Language: de\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"
"""


def main() -> int:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M%z")
    lines = [HEADER.format(date=date)]

    for msgid, (one, many) in sorted(PLURALS.items()):
        lines.append(f"msgid {po_string(msgid)}")
        plural_id = {"%d hour": "%d hours", "%d minute": "%d minutes",
                     "%d second": "%d seconds"}[msgid]
        lines.append(f"msgid_plural {po_string(plural_id)}")
        lines.append(f"msgstr[0] {po_string(one)}")
        lines.append(f"msgstr[1] {po_string(many)}")
        lines.append("")

    for msgid, msgstr in sorted(TRANSLATIONS.items()):
        lines.append(f"msgid {po_string(msgid)}")
        lines.append(f"msgstr {po_string(msgstr)}")
        lines.append("")

    target = LOCALE_DIR / "de" / "LC_MESSAGES" / "audiflix.po"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(TRANSLATIONS) + len(PLURALS)} entries -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
