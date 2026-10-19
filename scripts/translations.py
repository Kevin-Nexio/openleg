#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extract, validate and compile the standard gettext catalogs."""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from babel.messages.mofile import read_mo, write_mo
from babel.messages.pofile import read_po, write_po

ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "translations"
NAMED_FORMAT = re.compile(r"%\([^)]+\)[#0 +.\-0-9]*[diouxXeEfFgGcrsa]")


def extract(destination):
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from babel.messages.frontend import main; main()",
            "extract",
            "-F",
            "babel.cfg",
            "-k",
            "gettext_noop",
            "-k",
            "_l",
            "-k",
            "_N",
            "-o",
            str(destination),
            ".",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    with destination.open("rb") as handle:
        catalog = read_po(handle)
    normalize_flags(catalog)
    with destination.open("wb") as handle:
        write_po(handle, catalog, width=100, sort_output=True)
    destination.write_bytes(destination.read_bytes().rstrip() + b"\n")
    return catalog


def normalize_flags(catalog):
    for message in catalog:
        identifiers = message.id if isinstance(message.id, tuple) else (message.id,)
        # Babel mistakes literal prose such as '40% ohne' for '% o'. Our
        # interpolation convention uses named placeholders exclusively.
        if not any(NAMED_FORMAT.search(text or "") for text in identifiers):
            message.flags.discard("python-format")


def validate(catalog, expected):
    actual = {message.id for message in catalog if message.id}
    missing = {message.id for message in expected if message.id} - actual
    problems = [
        f"Missing source message: {message}" for message in sorted(missing, key=str)
    ]
    for message in catalog:
        if not message.id:
            continue
        values = (
            message.string if isinstance(message.string, tuple) else (message.string,)
        )
        if "fuzzy" in message.flags or not all(values):
            problems.append(f"Untranslated or fuzzy: {message.id}")
    problems.extend(f"{message.id}: {errors}" for message, errors in catalog.check())
    if problems:
        raise ValueError("\n".join(problems))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("extract", "check", "compile"))
    args = parser.parse_args()
    if args.command == "extract":
        catalog = extract(TRANSLATIONS / "messages.pot")
        print(f"Extracted {len(catalog)} source messages")
        return
    with TemporaryDirectory(prefix="openleg-i18n-") as directory:
        expected = extract(Path(directory) / "messages.pot")
    catalogs = sorted(TRANSLATIONS.glob("*/LC_MESSAGES/messages.po"))
    if not catalogs:
        raise ValueError("No translation catalogs found")
    for path in catalogs:
        with path.open("rb") as handle:
            catalog = read_po(handle, locale=path.parent.parent.name)
        normalize_flags(catalog)
        validate(catalog, expected)
        target = path.with_suffix(".mo")
        if args.command == "compile":
            with target.open("wb") as handle:
                write_mo(handle, catalog)
            path.write_bytes(path.read_bytes().rstrip() + b"\n")
        else:
            with target.open("rb") as handle:
                compiled = read_mo(handle)
            for message in catalog:
                if not message.id:
                    continue
                key = message.id[0] if isinstance(message.id, tuple) else message.id
                built = compiled.get(key)
                expected_value = message.string
                built_value = built.string if built is not None else None
                if isinstance(expected_value, tuple) and isinstance(built_value, list):
                    built_value = tuple(built_value)
                if built_value != expected_value:
                    raise ValueError(f"Compiled catalog is stale: {path}, {message.id}")
        print(f"{path.relative_to(ROOT)}: {len(catalog)} translated messages, OK")


if __name__ == "__main__":
    main()
