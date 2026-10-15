# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewed advisory identity and firmware interpretation at the domain API."""

import pytest

pytestmark = pytest.mark.unit


def entry(**changes):
    return {
        "reference": "SYNTHETIC-1",
        "publisher": "Example vendor",
        "source_url": "https://example.com/advisory",
        "source_revision": "1.0",
        "publication_date": "2025-08-27",
        "title": "Synthetic advisory",
        "summary": "Synthetic test evidence, not a published finding.",
        "vendor": "Example Solar AG",
        "vendor_aliases": ["Example Solar"],
        "models": [
            {
                "model": "Roof 1",
                "aliases": ["Roof-1"],
                "firmware": {
                    "scheme": "dotted-numeric",
                    "lower_inclusive": "1.0.0",
                    "upper_exclusive": "2.0.0",
                    "range_text": "From 1.0.0 to before 2.0.0",
                },
            }
        ],
        "remedy": {
            "text": "Ask the responsible installer.",
            "url": "https://example.com/remedy",
        },
        "status": "active",
        "change_note": "Initial source revision",
        **changes,
    }


def test_exact_reviewed_aliases_match_without_fuzzy_vendor_or_model_guessing():
    from advisories import match_advisory, validate_entry

    advisory = validate_entry(entry())
    result = match_advisory(
        {"manufacturer": "  EXAMPLE   SOLAR  ", "model": "roof-1", "firmware": "1.5.0"},
        advisory,
    )
    assert result["classification"] == "affected"
    assert result["reason"] == "firmware_within_range"
    assert result["matched_model"] == "Roof 1"
    mismatch = match_advisory(
        {"manufacturer": "Example", "model": "Roof 1", "firmware": "1.5.0"}, advisory
    )
    assert mismatch["classification"] == "no_identity_match"
