"""Tests that keep the translation catalogs honest.

The German catalog is the original wording of the application, so a missing
entry is a regression, not a cosmetic issue. These tests read the .po/.pot
sources, so they also pass on a fresh checkout where no .mo has been compiled
yet.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

i18n_tool = pytest.importorskip("i18n_tool")

LOCALE_DIR = ROOT / "src" / "audiflix" / "locale"
POT = LOCALE_DIR / "audiflix.pot"
GERMAN_PO = LOCALE_DIR / "de" / "LC_MESSAGES" / "audiflix.po"


def _pot_message_ids() -> set[str]:
    messages: dict = {}
    for path in sorted((ROOT / "src" / "audiflix").rglob("*.py")):
        i18n_tool.extract_file(path, messages)
    return {message.msgid for message in messages.values()}


def test_pot_file_exists():
    assert POT.is_file(), "run: python tools/i18n_tool.py extract"


def test_pot_is_up_to_date():
    """The committed template must match what the sources contain."""
    extracted = _pot_message_ids()
    committed = {key.split("\x00")[0] for key in i18n_tool.parse_po(POT)} | _pot_ids_from_file()
    missing = extracted - committed
    assert not missing, f"run: python tools/i18n_tool.py extract (missing: {sorted(missing)[:5]})"


def _pot_ids_from_file() -> set[str]:
    """msgids of the template (its msgstrs are empty, so parse_po skips them)."""
    import ast

    ids: set[str] = set()
    current = None
    for raw in POT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("msgid "):
            current = ast.literal_eval(line[6:])
        elif line.startswith('"') and current is not None:
            current += ast.literal_eval(line)
        elif current is not None:
            if current:
                ids.add(current)
            current = None
    if current:
        ids.add(current)
    return ids


def test_german_catalog_covers_every_message():
    translated = {key.split("\x04")[-1].split("\x00")[0] for key in i18n_tool.parse_po(GERMAN_PO)}
    missing = sorted(_pot_message_ids() - translated - {""})
    assert not missing, f"German translation missing for: {missing[:10]}"


def test_german_catalog_keeps_format_placeholders():
    """A translated string must keep the same %-placeholders as the original."""
    import re

    pattern = re.compile(r"%(?:\([^)]+\))?[sd]")
    problems = []
    for key, values in i18n_tool.parse_po(GERMAN_PO).items():
        if not key:
            continue
        source = key.split("\x04")[-1].split("\x00")[0]
        for value in values:
            if sorted(pattern.findall(source)) != sorted(pattern.findall(value)):
                problems.append((source, value))
    assert not problems, f"placeholder mismatch: {problems[:3]}"


def test_german_catalog_declares_plural_forms():
    header = i18n_tool.parse_po(GERMAN_PO).get("", [""])[0]
    assert "Plural-Forms" in header
    assert "charset=UTF-8" in header


def test_compiled_catalog_is_readable_when_present():
    mo = GERMAN_PO.with_suffix(".mo")
    if not mo.is_file():
        pytest.skip("no compiled catalog (run: python tools/i18n_tool.py compile)")
    import gettext

    translation = gettext.translation("audiflix", str(LOCALE_DIR), languages=["de"])
    assert translation.gettext("All books") == "Alle Bücher"
    assert translation.ngettext("%d hour", "%d hours", 2) % 2 == "2 Stunden"
