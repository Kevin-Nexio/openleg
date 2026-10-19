# SPDX-License-Identifier: AGPL-3.0-or-later
"""Translation validation fails on missing text, stale builds or placeholders."""

import subprocess
import sys
from pathlib import Path

import pytest
from babel.messages.catalog import Catalog

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
