# SPDX-License-Identifier: AGPL-3.0-or-later
"""Presentation language and explicit background-email locale regressions."""

from pathlib import Path

import pytest
from flask import Flask, render_template

import email_automation
from i18n import init_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    app = Flask(__name__, template_folder=str(ROOT / "templates"))
    app.config.update(
        SECRET_KEY="i18n-community-tests",
        BABEL_TRANSLATION_DIRECTORIES=str(ROOT / "translations"),
    )
    init_app(app)
    return app


def render(app, template, lang="de-CH", **context):
    with app.test_request_context("/?lang=" + lang):
        return render_template(template, **context)


def test_welcome_email_translates_full_sentences_and_escapes_variables(app):
    context = {
        "platform_name": "OpenLEG",
        "city_name": "Vully <script>",
        "neighbor_count": 4,
        "dashboard_url": "https://example.ch/dashboard",
        "referral_link": "",
        "unsubscribe_url": "https://example.ch/unsubscribe",
        "site_url": "https://example.ch",
        "primary_color": "#c7021a",
    }
    french = render(app, "emails/day_0_welcome.html", "fr-CH", **context)
    german = render(app, "emails/day_0_welcome.html", **context)
    assert '<html lang="fr-CH">' in french
    assert "Bienvenue sur OpenLEG" in french
    assert "communauté électrique locale (CEL)" in french
    assert "Vully &lt;script&gt;" in french
    assert "Vully <script>" not in french
    assert "4 autres ménages" in french
    assert "Willkommen bei OpenLEG" in german
    assert "4 weitere Haushalte" in german
    assert '<html lang="de-CH">' in german


def test_utility_login_translates_html_and_javascript_errors(app):
    french = render(app, "utility/login.html", "fr-CH")
    german = render(app, "utility/login.html")
    assert "E-mail professionnel" in french
    assert "Envoyer le lien de connexion" in french
    assert '"Erreur de connexion."' in french
    assert "Geschäftliche E-Mail" in german
    assert "Login-Link senden" in german
    assert '"Fehler beim Login."' in german
    assert "fetch('/utility/login'" in french


def test_email_subjects_follow_explicit_locale_not_mutable_global_defaults(app):
    from flask_babel import force_locale

    with app.app_context(), force_locale("fr_CH"):
        sequence = email_automation.get_email_sequence("OpenLEG")
        assert sequence["day_0_welcome"]["subject"].startswith("Bienvenue sur OpenLEG")
    with app.app_context(), force_locale("de_CH"):
        assert email_automation.get_email_sequence()["day_0_welcome"]["subject"] == (
            "Willkommen bei OpenLEG! Ihre Nachbarn warten"
        )


def test_interest_notification_does_not_inherit_request_language(app, monkeypatch):
    delivered = []
    monkeypatch.setattr(
        email_automation.db,
        "get_verified_interest_recipients",
        lambda *a, **k: ["member@example.ch"],
    )
    monkeypatch.setattr(email_automation.db, "get_interest_count", lambda *a: 4)
    monkeypatch.setattr(
        email_automation, "_send_email", lambda *args: delivered.append(args) or True
    )
    with app.test_request_context("/?lang=fr-CH"):
        email_automation.notify_new_municipality_interest(
            bfs_number=1, municipality_name="Vully", newcomer_email="other@example.ch"
        )
        email_automation.notify_new_municipality_interest(
            bfs_number=1,
            municipality_name="Vully",
            newcomer_email="other@example.ch",
            locale="fr_CH",
        )
    assert delivered[0][1] == "Neue LEG-Interessenmeldung in Vully"
    assert delivered[1][1] == "Nouvelle manifestation d’intérêt pour une CEL à Vully"
    assert "4 personnes" in delivered[1][2]
    assert "https://openleg.ch/unsubscribe" in delivered[1][2]


def test_interest_counts_keep_privacy_threshold_in_both_languages(app):
    from flask_babel import force_locale

    from municipality import _public_interest_label

    with app.app_context(), force_locale("fr_CH"):
        assert _public_interest_label(0) == "0 personne intéressée"
        assert _public_interest_label(1) == "< 3 personnes intéressées"
        assert _public_interest_label(2, confirmed=True) == (
            "< 3 personnes ayant confirmé leur intérêt"
        )
        assert _public_interest_label(4) == "4 personnes intéressées"
        assert _public_interest_label(None) == "Indisponible"
    with app.app_context(), force_locale("de_CH"):
        assert _public_interest_label(0) == "0 Interessierte"
        assert _public_interest_label(2) == "< 3 Interessierte"
        assert _public_interest_label(4, confirmed=True) == "4 bestätigte Interessierte"


def test_profile_cache_keeps_metadata_isolated_between_languages(app, monkeypatch):
    from flask_babel import force_locale

    import municipality_profile

    stored = {}
    neutral = {
        "profile": {"name": "Vully", "bfs_number": 1},
        "h4_tariff": {"total_rp_kwh": 27.5, "year": 2026},
        "seo_title": "neutral source",
        "seo_description": "neutral source",
        "jsonld": {
            "@graph": [
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [{"name": "Gemeindeverzeichnis"}],
                }
            ]
        },
        "league_chips": [{"label": "Kanton VD", "rank": 2}],
    }
    monkeypatch.setattr(
        municipality_profile, "_build_profile_context", lambda *a, **k: neutral
    )
    monkeypatch.setattr(
        municipality_profile.cache, "cache_get", lambda key: stored.get(key)
    )
    monkeypatch.setattr(
        municipality_profile.cache,
        "cache_set",
        lambda key, value, **k: stored.update({key: value}),
    )
    with app.app_context(), force_locale("fr_CH"):
        french = municipality_profile.profile_context(1, site_url="https://example.ch")
    with app.app_context(), force_locale("de_CH"):
        german = municipality_profile.profile_context(1, site_url="https://example.ch")
    assert french["seo_title"] == (
        "Tarif électrique de Vully 2026 : 27.5 ct./kWh, solaire et CEL | OpenLEG"
    )
    assert german["seo_title"] == (
        "Stromtarif Vully 2026: 27.5 Rp/kWh, Solar und LEG | OpenLEG"
    )
    assert (
        french["jsonld"]["@graph"][0]["itemListElement"][0]["name"]
        == "Répertoire des communes"
    )
    assert (
        german["jsonld"]["@graph"][0]["itemListElement"][0]["name"]
        == "Gemeindeverzeichnis"
    )
    assert french["league_chips"][0]["label"] == "Canton VD"
    assert german["league_chips"][0]["label"] == "Kanton VD"
    assert neutral["seo_title"] == "neutral source"
    assert len(stored) == 1


@pytest.mark.parametrize(
    "row_locale,tenant_locale,default_locale,request_locale,expected",
    [
        ("fr-CH", None, "de_CH", "de-CH", "Bienvenue sur"),
        (None, "fr_CH", "de_CH", "de-CH", "Bienvenue sur"),
        (None, None, "fr_CH", "de-CH", "Bienvenue sur"),
        (None, None, "de_CH", "fr-CH", "Willkommen bei"),
    ],
)
def test_queued_email_uses_explicit_locale_precedence(
    app,
    monkeypatch,
    row_locale,
    tenant_locale,
    default_locale,
    request_locale,
    expected,
):
    import access_token

    app.config.update(
        APP_BASE_URL="https://example.ch", BABEL_DEFAULT_LOCALE=default_locale
    )
    pending = {
        "id": 1,
        "building_id": "test-building",
        "email": "member@example.ch",
        "template_key": "day_0_welcome",
        "locale": row_locale,
    }
    tenant = {"platform_name": "OpenLEG", "city_name": "Vully", "locale": tenant_locale}
    delivered = []
    monkeypatch.setattr(email_automation, "_get_tenant_for_building", lambda *a: tenant)
    monkeypatch.setattr(email_automation.db, "cleanup_finished_emails", lambda: None)
    monkeypatch.setattr(
        email_automation.db, "get_pending_emails", lambda **k: [pending]
    )
    monkeypatch.setattr(email_automation.db, "get_referral_code", lambda *a: "")
    monkeypatch.setattr(email_automation.db, "mark_email_sent", lambda *a: None)
    monkeypatch.setattr(
        email_automation.db, "mark_email_failed", lambda *a: pytest.fail(str(a))
    )
    monkeypatch.setattr(access_token, "issue", lambda *a, **k: "a" * 43)
    monkeypatch.setattr(
        email_automation, "_send_email", lambda *a: delivered.append(a) or True
    )
    with app.test_request_context("/?lang=" + request_locale):
        result = email_automation.process_email_queue(app)
    assert result == {"sent": 1, "failed": 0, "total": 1}
    assert delivered[0][1].startswith(expected)
    assert expected + " OpenLEG" in delivered[0][2]


def test_municipality_auth_preserves_language_and_clears_authentication(
    app, monkeypatch
):
    import access_token
    from municipality import municipality_bp

    app.register_blueprint(municipality_bp)
    monkeypatch.setattr(access_token, "consume", lambda *args: 7)
    monkeypatch.setattr(
        email_automation.db, "revoke_municipality_access_tokens", lambda *args: None
    )
    client = app.test_client()
    with client.session_transaction() as stored:
        stored["locale"] = "fr_CH"
        stored["stale_auth"] = "old"
    response = client.get("/gemeinde/access/example")
    assert response.status_code == 302
    with client.session_transaction() as stored:
        assert stored["locale"] == "fr_CH"
        assert stored["municipality_id"] == 7
        assert "stale_auth" not in stored
        csrf_token = stored["municipality_csrf_token"]
    response = client.post("/gemeinde/logout", data={"csrf_token": csrf_token})
    assert response.status_code == 302
    with client.session_transaction() as stored:
        assert stored["locale"] == "fr_CH"
        assert "municipality_id" not in stored
        assert "municipality_csrf_token" not in stored
