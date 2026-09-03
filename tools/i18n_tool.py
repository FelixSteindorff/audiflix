#!/usr/bin/env python3
"""Extract translatable strings and compile translation catalogs.

Two commands, no third-party dependencies (so CI and a fresh checkout need
nothing beyond the standard library):

    python tools/i18n_tool.py extract    # rebuild locale/audiflix.pot
    python tools/i18n_tool.py compile    # locale/*/LC_MESSAGES/*.po -> *.mo

``extract`` parses the sources with :mod:`ast` and collects every call to
``_()``, ``N_()``, ``ngettext()`` and ``pgettext()`` with literal arguments.
``compile`` writes GNU MO files, which is what :mod:`gettext` reads at runtime.
"""

from __future__ import annotations

import argparse
import ast
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "src" / "audiflix"
LOCALE_DIR = SOURCE_DIR / "locale"
DOMAIN = "audiflix"

SINGULAR_FUNCTIONS = {"_", "N_", "gettext"}
PLURAL_FUNCTIONS = {"ngettext"}
CONTEXT_FUNCTIONS = {"pgettext"}


# --- Extraction ------------------------------------------------------------

class Message:
    __slots__ = ("context", "locations", "msgid", "plural")

    def __init__(self, msgid: str, plural: str | None = None, context: str | None = None):
        self.msgid = msgid
        self.plural = plural
        self.context = context
        self.locations: list[str] = []

    @property
    def key(self) -> tuple[str | None, str]:
        return (self.context, self.msgid)


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_file(path: Path, messages: dict[tuple[str | None, str], Message]) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = path.relative_to(ROOT).as_posix()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None
        )
        if not name or not node.args:
            continue

        message: Message | None = None
        if name in SINGULAR_FUNCTIONS:
            text = _literal(node.args[0])
            if text:
                message = Message(text)
        elif name in PLURAL_FUNCTIONS and len(node.args) >= 2:
            singular, plural = _literal(node.args[0]), _literal(node.args[1])
            if singular and plural:
                message = Message(singular, plural=plural)
        elif name in CONTEXT_FUNCTIONS and len(node.args) >= 2:
            context, text = _literal(node.args[0]), _literal(node.args[1])
            if context and text:
                message = Message(text, context=context)

        if message is None:
            continue
        existing = messages.get(message.key)
        if existing is None:
            messages[message.key] = message
            existing = message
        elif message.plural and not existing.plural:
            existing.plural = message.plural
        existing.locations.append(f"{relative}:{node.lineno}")


def po_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\t", "\\t")
        .replace("\n", "\\n")
    )


def po_string(text: str) -> str:
    """Render a string as one or more PO string literals."""
    if "\n" not in text:
        return f'"{po_escape(text)}"'
    parts = text.split("\n")
    lines = ['""']
    for index, part in enumerate(parts):
        suffix = "\\n" if index < len(parts) - 1 else ""
        if part or suffix:
            lines.append(f'"{po_escape(part)}{suffix}"')
    return "\n".join(lines)


def write_pot(messages: dict[tuple[str | None, str], Message], path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M%z")
    lines = [
        "# Translation template for Audiflix.",
        "# Copyright (C) 2026 Felix Steindorff",
        "# This file is distributed under the same MIT license as Audiflix.",
        "#",
        '#, fuzzy',
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: audiflix\\n"',
        f'"POT-Creation-Date: {now}\\n"',
        '"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"',
        '"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"',
        '"Language-Team: LANGUAGE <LL@li.org>\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"',
        "",
    ]
    for message in sorted(messages.values(), key=lambda m: (m.context or "", m.msgid)):
        for location in sorted(set(message.locations)):
            lines.append(f"#: {location}")
        if message.context:
            lines.append(f"msgctxt {po_string(message.context)}")
        lines.append(f"msgid {po_string(message.msgid)}")
        if message.plural:
            lines.append(f"msgid_plural {po_string(message.plural)}")
            lines.append('msgstr[0] ""')
            lines.append('msgstr[1] ""')
        else:
            lines.append('msgstr ""')
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def command_extract() -> int:
    messages: dict[tuple[str | None, str], Message] = {}
    files = sorted(SOURCE_DIR.rglob("*.py"))
    for path in files:
        extract_file(path, messages)
    target = LOCALE_DIR / f"{DOMAIN}.pot"
    write_pot(messages, target)
    print(f"Extracted {len(messages)} messages from {len(files)} files -> {target}")
    return 0


# --- PO parsing and MO compilation ----------------------------------------

def parse_po(path: Path) -> dict[str, list[str]]:
    """Return ``{msgid (or 'singular\\x00plural'): [translations]}``.

    Fuzzy and untranslated entries are skipped, exactly like ``msgfmt``.
    """
    entries: dict[str, list[str]] = {}
    context: str | None = None
    msgid = msgid_plural = None
    translations: dict[int, str] = {}
    fuzzy = False
    pending_fuzzy = False
    current: tuple[str, int] | None = None

    def flush() -> None:
        nonlocal context, msgid, msgid_plural, translations, fuzzy
        if msgid is not None and not fuzzy:
            values = [translations[index] for index in sorted(translations)]
            if any(values):
                key = msgid if msgid_plural is None else f"{msgid}\x00{msgid_plural}"
                if context is not None:
                    key = f"{context}\x04{key}"
                entries[key] = values
        context = msgid = msgid_plural = None
        translations = {}
        fuzzy = False

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("#,") and "fuzzy" in line:
                pending_fuzzy = True
            continue
        if line.startswith('"'):
            if current is None:
                continue
            kind, index = current
            value = ast.literal_eval(line)
            if kind == "msgctxt":
                context = (context or "") + value
            elif kind == "msgid":
                msgid = (msgid or "") + value
            elif kind == "msgid_plural":
                msgid_plural = (msgid_plural or "") + value
            else:
                translations[index] = translations.get(index, "") + value
            continue

        keyword, _, rest = line.partition(" ")
        value = ast.literal_eval(rest.strip()) if rest.strip() else ""
        if keyword == "msgctxt":
            flush()
            fuzzy = pending_fuzzy
            pending_fuzzy = False
            context = value
            current = ("msgctxt", 0)
        elif keyword == "msgid":
            if msgid is not None and context is None:
                flush()
            if context is None:
                fuzzy = pending_fuzzy
            pending_fuzzy = False
            msgid = value
            current = ("msgid", 0)
        elif keyword == "msgid_plural":
            msgid_plural = value
            current = ("msgid_plural", 0)
        elif keyword == "msgstr":
            translations[0] = value
            current = ("msgstr", 0)
        elif keyword.startswith("msgstr["):
            index = int(keyword[7:-1])
            translations[index] = value
            current = ("msgstr", index)
    flush()
    return entries


def write_mo(entries: dict[str, list[str]], path: Path) -> None:
    """Write a GNU MO file (little endian, no hash table)."""
    items = sorted(entries.items())
    keys = [key.encode("utf-8") for key, _ in items]
    values = ["\x00".join(value).encode("utf-8") for _, value in items]

    count = len(items)
    key_table_offset = 7 * 4
    value_table_offset = key_table_offset + count * 8
    data_offset = value_table_offset + count * 8

    key_descriptors = bytearray()
    value_descriptors = bytearray()
    payload = bytearray()
    offset = data_offset
    for key in keys:
        key_descriptors += struct.pack("<II", len(key), offset)
        payload += key + b"\x00"
        offset += len(key) + 1
    for value in values:
        value_descriptors += struct.pack("<II", len(value), offset)
        payload += value + b"\x00"
        offset += len(value) + 1

    header = struct.pack(
        "<IIIIIII",
        0x950412DE,          # magic
        0,                   # revision
        count,
        key_table_offset,
        value_table_offset,
        0,                   # hash table size
        0,                   # hash table offset
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header + key_descriptors + value_descriptors + payload))


def command_compile() -> int:
    if not LOCALE_DIR.is_dir():
        print(f"No locale directory at {LOCALE_DIR}", file=sys.stderr)
        return 1
    compiled = 0
    for po_path in sorted(LOCALE_DIR.rglob("*.po")):
        entries = parse_po(po_path)
        mo_path = po_path.with_suffix(".mo")
        write_mo(entries, mo_path)
        print(f"{po_path.relative_to(ROOT)} -> {mo_path.name} ({len(entries)} entries)")
        compiled += 1
    if not compiled:
        print("No .po files found - nothing to compile.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["extract", "compile"])
    args = parser.parse_args(argv)
    return command_extract() if args.command == "extract" else command_compile()


if __name__ == "__main__":
    raise SystemExit(main())
