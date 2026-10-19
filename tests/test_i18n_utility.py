# SPDX-License-Identifier: AGPL-3.0-or-later
"""Utility access mail and browser response use the chosen display language."""

from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask
from flask_babel import force_locale

import utility_portal
from i18n import init_app


@pytest.fixture
def web():
    web = Flask(__name__)
    web.config.update(
        SECRET_KEY="utility-language-test",
        APP_BASE_URL="https://example.ch",
        BABEL_TRANSLATION_DIRECTORIES=str(
            Path(__file__).resolve().parents[1] / "translations"
        ),
    )
    init_app(web)
    web.register_blueprint(utility_portal.utility_bp)
    return web


def test_french_magic_link_email_is_localized_and_carries_locale(web, monkeypatch):
    send = MagicMock(return_value=True)
    monkeypatch.setattr(utility_portal, "send_email", send)
    monkeypatch.setattr(utility_portal.db, "set_utility_magic_token", MagicMock())
    monkeypatch.setattr(
        utility_portal.secrets, "token_urlsafe", lambda _: "opaque-token"
    )
    with web.app_context(), force_locale("fr_CH"):
        utility_portal._send_magic_link("synthetic-client", "person@example.ch")
    recipient, subject, body = send.call_args.args
    assert recipient == "person@example.ch"
    assert subject == "OpenLEG : votre lien de connexion"
    assert "15 minutes" in body and "Cliquez sur le lien" in body
    link = next(line for line in body.splitlines() if line.startswith("https://"))
    assert parse_qs(urlsplit(link).query) == {
        "token": ["opaque-token"],
        "lang": ["fr-CH"],
    }


def test_french_utility_registration_validation_keeps_status_and_schema(web):
    response = web.test_client().post("/utility/register?lang=fr", json={})
    assert response.status_code == 400
    assert response.json == {
        "error": "Le nom de l’entreprise et l’adresse e-mail sont obligatoires."
    }
