# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render the shipped public templates through the production language extension."""

import json
import re
from pathlib import Path

import pytest
from flask import Flask, render_template

from i18n import init_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def public_language_app():
    app = Flask(__name__, template_folder=str(ROOT / "templates"))
    app.config.update(
        TESTING=True,
        SECRET_KEY="public-language-test",
        BABEL_TRANSLATION_DIRECTORIES=str(ROOT / "translations"),
    )
    init_app(app)
    return app


def render_public(app, name, language="fr-CH", **values):
    context = {
        "site_url": "https://openleg.example",
        "platform_name": "OpenLEG",
        "city_name": "Vully-les-Lacs",
        "contact_email": "contact@example.invalid",
        "legal_entity": None,
        "canonical_path": "/api/v1/docs",
        "matomo_site_id": "",
        "ga4_id": "",
        "user_count": 2,
        "ranking_best": [],
        "ranking_worst": [],
        "ranking_total": 0,
        "map_center_lat": 46.95,
        "map_center_lon": 7.44,
        "map_zoom": 10,
    }
    context.update(values)
    with app.test_request_context("/?lang=" + language):
        return render_template(name + ".html", **context)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("index", "Créez une"),
        ("fuer_bewohner", "Vérifiez si une CEL vaut la peine chez vous"),
        ("fuer_gemeinden", "Votre commune voit les prochaines étapes"),
        ("how-it-works", "Comment fonctionne une communauté électrique"),
        ("open_source", "Une infrastructure énergétique libre"),
        ("pricing", "Gratuit. Open source. Pour toujours."),
        ("self_host", "Installer OpenLEG sur votre propre infrastructure."),
        ("api_docs", "Exemples à copier-coller"),
        ("datenschutz", "Protection des données"),
        ("impressum", "Mentions légales"),
        ("leg_kalkulator", "Calculateur CEL"),
    ],
)
def test_public_pages_render_in_french(public_language_app, name, expected):
    rendered = render_public(public_language_app, name)
    assert expected in rendered
    assert "{{" not in rendered
    assert "{%" not in rendered


def test_default_german_preserves_percentage_and_metadata(public_language_app):
    rendered = render_public(public_language_app, "index", language="de-CH")
    assert "Gründen Sie eine" in rendered
    assert "Bis zu 40% Rabatt" in rendered
    assert "Lokale Elektrizitätsgemeinschaft gründen | OpenLEG" in rendered
    assert '"inLanguage": "de-CH"' in rendered


def test_home_registered_count_uses_actual_plural_rules(public_language_app):
    single = render_public(public_language_app, "index", user_count=1)
    several = render_public(public_language_app, "index", user_count=3)
    assert 'Déjà <strong class="text-ink">1</strong> ménage inscrit' in single
    assert 'Déjà <strong class="text-ink">3</strong> ménages inscrits' in several


def test_structured_data_is_valid_json_and_french(public_language_app):
    rendered = render_public(public_language_app, "how-it-works")
    objects = [
        json.loads(payload)
        for payload in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', rendered, re.DOTALL
        )
    ]
    breadcrumb = next(item for item in objects if item["@type"] == "BreadcrumbList")
    faq = next(item for item in objects if item["@type"] == "FAQPage")
    assert breadcrumb["itemListElement"][1]["name"] == "Comment ça marche"
    assert faq["mainEntity"][0]["name"].startswith("Quelle est la différence")
    assert "RCP virtuel" in faq["mainEntity"][0]["acceptedAnswer"]["text"]


def test_legal_dynamic_names_are_escaped(public_language_app):
    platform = '<script>alert("name")</script>'
    rendered = render_public(public_language_app, "datenschutz", platform_name=platform)
    assert platform not in rendered
    assert "&lt;script&gt;" in rendered
    assert "Cette déclaration explique quelles données personnelles" in rendered
    assert (
        "Nous transmettons des données personnelles à des tiers uniquement" in rendered
    )


def test_install_console_supplies_translated_clipboard_feedback(public_language_app):
    rendered = render_public(public_language_app, "self_host")
    assert 'data-copy-success="Commande copiée."' in rendered
    assert 'aria-label="Copier la commande"' in rendered
    assert "curl -fsSL https://openleg.ch/install.sh | bash" in rendered


def test_calculator_messages_and_sources_use_french(public_language_app):
    rendered = render_public(public_language_app, "leg_kalkulator")
    assert "Aucun tarif disponible pour cette commune." in rendered
    assert "OFS : " in rendered
    assert "Art. 19h OApEl" in rendered
    assert "Données actuelles de l’API" in rendered
    assert 'toLocaleString("fr-CH")' in rendered
    assert "%(annual)s" in rendered
    assert "%(total)s" in rendered
