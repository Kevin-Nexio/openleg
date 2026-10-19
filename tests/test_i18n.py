# SPDX-License-Identifier: AGPL-3.0-or-later
"""Language selection through the real application and safe gettext output."""

import gettext
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, render_template_string
from flask_babel import force_locale, ngettext
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


def test_real_catalog_compiles_with_french_plural_rules(web):
    root = Path(__file__).resolve().parents[1]
    with (root / "translations/fr_CH/LC_MESSAGES/messages.mo").open("rb") as handle:
        catalog = gettext.GNUTranslations(handle)
    assert catalog.gettext("Sprache") == "Langue"
    with web.test_request_context("/?lang=fr"):
        assert (
            ngettext("%(num)s Interessierte", "%(num)s Interessierte", 1)
            == "1 personne intéressée"
        )
        assert (
            ngettext("%(num)s Interessierte", "%(num)s Interessierte", 2)
            == "2 personnes intéressées"
        )


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
