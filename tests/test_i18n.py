# SPDX-License-Identifier: AGPL-3.0-or-later
"""Language selection through the real application and safe gettext output."""

from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, render_template_string
from flask_babel import force_locale
from flask_babel import gettext as _

import app


@pytest.fixture
def web(monkeypatch):
    # App configuration is explicit: no production environment or services.
    for name in (
        "DATABASE_URL",
        "ADMIN_TOKEN",
        "INTERNAL_TOKEN",
        "CRON_SECRET",
        "REDIS_URL",
        "MATOMO_SITE_ID",
        "SESSION_COOKIE_SECURE",
    ):
        monkeypatch.setenv(name, "")
    return app.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "i18n-test-only",
            "APP_BASE_URL": "http://localhost",
            "PUBLIC_SITE_URL": "https://openleg.ch",
            "RATELIMIT_STORAGE_URI": "memory://",
            "SESSION_COOKIE_SECURE": False,
            "BABEL_DEFAULT_LOCALE": "de_CH",
        },
        load_environment=False,
        check_database=False,
    )


def test_default_language_remains_german(web):
    response = web.test_client().get("/login", headers={"Accept-Language": "fr-CH"})
    assert response.status_code == 200
    assert '<html lang="de-CH">' in response.text
    assert response.headers["Content-Language"] == "de-CH"


def test_french_switch_persists_across_navigation_and_can_be_reset(web):
    client = web.test_client()
    french = client.get("/login?lang=fr-CH")
    assert french.status_code == 200
    assert '<html lang="fr-CH">' in french.text
    assert french.headers["Content-Language"] == "fr-CH"
    assert "Cookie" in french.vary
    assert client.get("/login").headers["Content-Language"] == "fr-CH"
    assert client.get("/login?lang=de").headers["Content-Language"] == "de-CH"


@pytest.mark.parametrize(
    "language", ["../../fr", "it", "fr<script>", "https://evil.invalid"]
)
def test_unsupported_language_cannot_select_a_catalog_or_redirect(web, language):
    response = web.test_client().get("/login", query_string={"lang": language})
    assert response.status_code == 200
    assert response.headers["Content-Language"] == "de-CH"
    assert not response.headers.get("Location")


def test_switch_links_preserve_repeated_query_values_and_stay_local(web):
    from i18n import language_switch_url

    with web.test_request_context("/login?ref=a%26b&filter=x&filter=y&lang=de"):
        target = urlsplit(language_switch_url("fr-CH"))
    assert not target.netloc and not target.scheme
    assert target.path == "/login"
    assert parse_qs(target.query) == {
        "ref": ["a&b"],
        "filter": ["x", "y"],
        "lang": ["fr-CH"],
    }


def test_french_catalog_and_fallback_are_used_and_interpolation_is_escaped(web):
    with web.test_request_context("/?lang=fr"):
        assert _("Sprache") == "Langue"
        assert _("Untranslated sentinel") == "Untranslated sentinel"
        rendered = render_template_string(
            "{{ _('Hallo %(name)s', name=name) }}", name="<script>x</script>"
        )
        assert "<script>" not in rendered
        assert "&lt;script&gt;" in rendered


def test_locale_is_scoped_to_the_app_and_request(web):
    with web.test_request_context("/?lang=fr"):
        assert _("Sprache") == "Langue"
    with web.test_request_context("/"):
        assert _("Sprache") == "Sprache"
    with web.app_context(), force_locale("fr_CH"):
        assert _("Sprache") == "Langue"
    assert _("Sprache") == "Sprache"


def test_i18n_initialization_does_not_require_an_application_factory():
    from i18n import init_app

    standalone = Flask(__name__)
    standalone.secret_key = "isolated-test"
    init_app(standalone)
    with standalone.test_request_context("/"):
        assert _("Sprache") == "Sprache"


def test_localized_links_preserve_tokens_filters_fragments_and_german_defaults(web):
    from i18n import localized_url

    original = "https://example.ch/dashboard/access/opaque?ref=a%26b&filter=x#content"
    with web.test_request_context("/?lang=fr"):
        french = urlsplit(localized_url(original))
    assert french.scheme == "https" and french.netloc == "example.ch"
    assert french.path == "/dashboard/access/opaque" and french.fragment == "content"
    assert parse_qs(french.query) == {
        "ref": ["a&b"],
        "filter": ["x"],
        "lang": ["fr-CH"],
    }
    with web.test_request_context("/"):
        assert localized_url(original) == original


def test_default_locale_alias_is_normalized_before_babel_parses_it():
    from i18n import init_app

    standalone = Flask(__name__)
    standalone.config.update(SECRET_KEY="test-only", BABEL_DEFAULT_LOCALE="fr-CH")
    init_app(standalone)
    assert standalone.config["BABEL_DEFAULT_LOCALE"] == "fr_CH"


def test_links_to_the_public_site_carry_the_selected_language(web):
    public_site_url = web.jinja_env.globals["public_site_url"]
    with web.test_request_context("/?lang=fr"):
        assert (
            public_site_url("/how-it-works")
            == "https://openleg.ch/how-it-works?lang=fr-CH"
        )
    with web.test_request_context("/"):
        assert public_site_url("/how-it-works") == "https://openleg.ch/how-it-works"


@pytest.mark.parametrize("default", ["de_CH", "fr_CH"])
@pytest.mark.parametrize("selected", ["de_CH", "fr_CH"])
def test_durable_links_keep_an_explicit_recipient_locale(web, default, selected):
    from i18n import localized_url

    web.config["BABEL_DEFAULT_LOCALE"] = default
    original = "https://example.ch/dashboard/access/opaque?filter=x&filter=y#detail"
    with web.app_context():
        target = localized_url(original, locale=selected)
    parsed = urlsplit(target)
    assert parsed.path == "/dashboard/access/opaque"
    assert parsed.fragment == "detail"
    assert parse_qs(parsed.query) == {
        "filter": ["x", "y"],
        "lang": [selected.replace("_", "-")],
    }
    fresh = web.test_client().get("/login?" + parsed.query)
    assert fresh.headers["Content-Language"] == selected.replace("_", "-")


def test_german_choice_on_french_default_is_kept_in_generated_link(web):
    from i18n import localized_url

    web.config["BABEL_DEFAULT_LOCALE"] = "fr_CH"
    with web.test_request_context("/?lang=de-CH"):
        assert localized_url("https://example.ch/login") == (
            "https://example.ch/login?lang=de-CH"
        )


def test_generated_link_replaces_a_stale_language_with_current_choice(web):
    from i18n import localized_url

    with web.test_request_context("/?lang=de-CH"):
        assert localized_url("https://example.ch/login?lang=fr-CH") == (
            "https://example.ch/login?lang=de-CH"
        )


@pytest.mark.parametrize(
    "locale,expected", [("de-CH", "50’000"), ("fr-CH", "50\u202f000")]
)
def test_display_counts_use_swiss_locale_without_changing_the_value(
    web, locale, expected
):
    from decimal import Decimal

    from i18n import format_number_label

    value = Decimal(50000)
    with web.test_request_context("/?lang=" + locale):
        assert format_number_label(value) == expected
        assert "12345" in format_number_label(Decimal("50000.12345"))
    assert value == Decimal(50000)


@pytest.mark.parametrize(
    "sequence", [("de-CH", "fr-CH", "de-CH"), ("fr-CH", "de-CH", "fr-CH")]
)
def test_cached_templates_keep_locale_dependent_filters_request_local(web, sequence):
    from flask import render_template
    from jinja2 import ChoiceLoader, DictLoader

    web.jinja_loader = ChoiceLoader(
        [
            DictLoader(
                {
                    "locale-cache.html": "{{ '/static/images/product/resident-dashboard.gif'|localized_asset }}|{{ 4500|numberlabel }}|{{ 'Juli 2026'|periodlabel }}|{{ '15.00 Rp./kWh'|ratelabel }}|{{ '/dashboard'|localized_url }}"
                }
            ),
            web.jinja_loader,
        ]
    )
    for language in sequence:
        with web.test_request_context("/?lang=" + language):
            rendered = render_template("locale-cache.html")
        asset, count, period, rate, url = rendered.split("|")
        french = language == "fr-CH"
        assert ("/fr-CH/" in asset) == french
        assert count == ("4\u202f500" if french else "4’500")
        assert period == ("juillet 2026" if french else "Juli 2026")
        assert rate == ("15.00 ct./kWh" if french else "15.00 Rp./kWh")
        assert url == ("/dashboard?lang=fr-CH" if french else "/dashboard")
