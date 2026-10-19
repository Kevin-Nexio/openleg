# SPDX-License-Identifier: AGPL-3.0-or-later
"""Translation validation fails on missing text, stale builds or placeholders."""

import subprocess
import sys
from pathlib import Path

import pytest
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.messages.pofile import write_po

from scripts.translations import normalize_flags, validate


def test_shipped_catalog_matches_current_sources_and_compiled_output():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/translations.py", "check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_catalog_validation_rejects_missing_source_messages_and_fuzzy_text():
    source = Catalog()
    source.add("Neue Nachricht")
    french = Catalog(locale="fr_CH")
    with pytest.raises(ValueError, match="Missing source message"):
        validate(french, source)
    french.add("Neue Nachricht", "Nouveau message", flags={"fuzzy"})
    with pytest.raises(ValueError, match="fuzzy"):
        validate(french, source)


def test_catalog_validation_keeps_named_placeholder_checks():
    source = Catalog()
    source.add("Hallo %(name)s")
    french = Catalog(locale="fr_CH")
    french.add("Hallo %(name)s", "Bonjour %(wrong)s")
    normalize_flags(french)
    with pytest.raises(ValueError, match="name|wrong"):
        validate(french, source)


def test_literal_percent_prose_is_not_mistaken_for_python_interpolation():
    source = Catalog()
    source.add("40% ohne Transformation")
    french = Catalog(locale="fr_CH")
    french.add("40% ohne Transformation", "40% sans transformation")
    normalize_flags(french)
    validate(french, source)


def test_translation_cannot_introduce_a_placeholder_into_plain_source():
    source = Catalog()
    source.add("Speichern")
    french = Catalog(locale="fr_CH")
    french.add("Speichern", "Enregistrer %(unexpected)s")
    normalize_flags(french)
    with pytest.raises(ValueError, match="unexpected|placeholder"):
        validate(french, source)


def test_compiled_plural_rule_must_match_the_po(tmp_path, monkeypatch):
    from scripts import translations

    source = Catalog()
    source.add(("Ein Haushalt", "Haushalte"))
    french = Catalog(locale="fr_CH")
    french.add(("Ein Haushalt", "Haushalte"), ("Un ménage", "Des ménages"))
    directory = tmp_path / "translations/fr_CH/LC_MESSAGES"
    directory.mkdir(parents=True)
    with (directory / "messages.po").open("wb") as handle:
        write_po(handle, french)
    french._plural_expr = "(n != 1)"
    with (directory / "messages.mo").open("wb") as handle:
        write_mo(handle, french)
    monkeypatch.setattr(translations, "ROOT", tmp_path)
    monkeypatch.setattr(translations, "TRANSLATIONS", tmp_path / "translations")
    monkeypatch.setattr(translations, "extract", lambda path: source)
    monkeypatch.setattr(sys, "argv", ["translations.py", "check"])
    with pytest.raises(ValueError, match="plural|Plural"):
        translations.main()


def test_contextual_messages_cannot_be_satisfied_by_another_context():
    source = Catalog()
    source.add("Open", context="navigation")
    french = Catalog(locale="fr_CH")
    french.add("Open", "Ouvrir", context="document-action")
    with pytest.raises(ValueError, match="navigation"):
        validate(french, source)


def test_compiled_contextual_messages_are_checked_with_their_context(
    tmp_path, monkeypatch, capsys
):
    from scripts import translations

    source = Catalog()
    source.add("Open", context="navigation")
    source.add("Open", context="document-action")
    french = Catalog(locale="fr_CH")
    french.add("Open", "Ouvert", context="navigation")
    french.add("Open", "Ouvrir", context="document-action")
    directory = tmp_path / "translations/fr_CH/LC_MESSAGES"
    directory.mkdir(parents=True)
    with (directory / "messages.po").open("wb") as handle:
        write_po(handle, french)
    with (directory / "messages.mo").open("wb") as handle:
        write_mo(handle, french)
    monkeypatch.setattr(translations, "ROOT", tmp_path)
    monkeypatch.setattr(translations, "TRANSLATIONS", tmp_path / "translations")
    monkeypatch.setattr(translations, "extract", lambda path: source)
    monkeypatch.setattr(sys, "argv", ["translations.py", "check"])
    translations.main()
    assert "2 translated messages, OK" in capsys.readouterr().out
    french.get("Open", context="navigation").string = "Autre"
    with (directory / "messages.po").open("wb") as handle:
        write_po(handle, french)
    with pytest.raises(ValueError, match="stale"):
        translations.main()
