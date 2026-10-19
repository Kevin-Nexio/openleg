# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resource language remains tied to the contract content during UI translation."""

import pytest

import formation_wizard


@pytest.mark.parametrize("language", ["de-CH", "fr-CH"])
def test_template_language_describes_the_document_content(client, language):
    response = client.get(f"/api/v1/leg/templates?lang={language}")
    assert response.status_code == 200
    contracts = {item["name"]: item for item in response.get_json()["contracts"]}
    sources = formation_wizard.get_contract_templates()
    assert set(contracts) == set(sources)
    for name, source in sources.items():
        assert contracts[name]["language"] == source.get("language", "de")
        assert contracts[name]["sections"] == source["sections"]
