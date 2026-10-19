# SPDX-License-Identifier: AGPL-3.0-or-later
"""Immediate private notifications use the current display language safely."""

from unittest.mock import MagicMock

import pytest

import app
import dashboard
import dashboard_routes
from i18n import localized_url
from tests.test_dashboard_access_routes import _set_session


@pytest.fixture
def notifications(monkeypatch):
    for name in (
        "DATABASE_URL",
        "ADMIN_TOKEN",
        "INTERNAL_TOKEN",
        "CRON_SECRET",
        "MATOMO_SITE_ID",
        "SESSION_COOKIE_SECURE",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("REDIS_URL", "memory://")
    sender = MagicMock(return_value=True)
    monkeypatch.setattr(app, "send_email", sender)
    web = app.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "notification-test",
            "APP_BASE_URL": "http://localhost",
            "RATELIMIT_STORAGE_URI": "memory://",
            "SESSION_COOKIE_SECURE": False,
        },
        load_environment=False,
        check_database=False,
    )
    return web, sender


def test_french_access_email_and_private_response_preserve_token(
    notifications, monkeypatch
):
    web, sender = notifications
    profiles = MagicMock(return_value=[])
    monkeypatch.setattr(app.db, "get_building_by_email", profiles)
    monkeypatch.setattr(
        dashboard_routes.access_token, "issue", lambda *args, **kwargs: "a" * 43
    )
    client = web.test_client()
    absent = client.post(
        "/dashboard/access/request?lang=fr", data={"email": "one@example.ch"}
    )
    assert absent.status_code == 200
    sender.assert_not_called()
    profiles.return_value = [{"building_id": "building-1"}]
    present = client.post(
        "/dashboard/access/request?lang=fr", data={"email": "one@example.ch"}
    )
    assert present.status_code == 200
    assert present.text == absent.text
    assert "Si un profil correspond à cette adresse e-mail" in present.text
    recipient, subject, body = sender.call_args.args
    assert recipient == "one@example.ch"
    assert subject == "Votre lien d’accès au tableau de bord"
    assert "Ouvrez votre tableau de bord" in body
    link = "http://localhost/dashboard/access/" + "a" * 43 + "?lang=fr-CH"
    assert link in body
    monkeypatch.setattr(
        app.db,
        "consume_dashboard_access_token",
        lambda *args: {"building_id": "building-1"},
    )
    fresh_browser = web.test_client()
    assert fresh_browser.get(link).status_code == 302
    with fresh_browser.session_transaction() as state:
        assert state["locale"] == "fr_CH"
        assert state["dashboard_building_id"] == "building-1"


def test_german_access_email_link_is_unchanged(notifications, monkeypatch):
    web, sender = notifications
    monkeypatch.setattr(
        app.db, "get_building_by_email", lambda *args: [{"building_id": "one"}]
    )
    monkeypatch.setattr(
        dashboard_routes.access_token, "issue", lambda *args, **kwargs: "a" * 43
    )
    assert (
        web.test_client()
        .post("/dashboard/access/request", data={"email": "one@example.ch"})
        .status_code
        == 200
    )
    assert sender.call_args.args[1] == "Ihr Dashboard-Zugangslink"
    assert (
        "http://localhost/dashboard/access/" + "a" * 43 + "\n\n"
        in sender.call_args.args[2]
    )
    assert "?lang=" not in sender.call_args.args[2]


def test_french_invoice_delivery_keeps_number_and_audit_identity(
    notifications, monkeypatch
):
    web, sender = notifications
    monkeypatch.setattr(dashboard, "_require_capability", lambda *args: True)
    prepare = MagicMock(
        return_value={
            "delivery_method": "email",
            "recipient_email": "member@example.ch",
            "invoice_number": "LEG-2026-000001",
        }
    )
    complete = MagicMock(return_value={"lifecycle_state": "delivered"})
    monkeypatch.setattr(dashboard.db, "prepare_invoice_delivery", prepare)
    monkeypatch.setattr(dashboard.db, "complete_invoice_delivery", complete)
    with web.test_request_context("/?lang=fr"):
        result = dashboard.leg_deliver_invoice(
            "community-1",
            "admin-1",
            42,
            send_email=sender,
            invoice_url="http://localhost/dashboard/invoices/42",
        )
    assert result["error"] is None
    assert sender.call_args.args == (
        "member@example.ch",
        "Votre facture LEG-2026-000001",
        "Votre nouvelle facture CEL est disponible dans votre tableau de bord OpenLEG sécurisé : http://localhost/dashboard/invoices/42?lang=fr-CH",
    )
    prepare.assert_called_once_with(42, "community-1", "admin-1")
    complete.assert_called_once_with(42, "community-1", "admin-1")


def test_french_contact_notification_preserves_privacy_and_locale(
    notifications, monkeypatch
):
    web, sender = notifications
    operation = MagicMock(return_value=["recipient@example.ch"])
    monkeypatch.setattr(dashboard_routes.contact_request, "create", operation)
    client = web.test_client()
    _set_session(client)
    response = client.post(
        "/dashboard/contacts?lang=fr",
        data={"csrf_token": "csrf-secret", "candidate": "target", "share_email": "yes"},
    )
    assert response.status_code == 302
    assert sender.call_args.args[1] == "Vos demandes de contact sur OpenLEG"
    assert "http://localhost/dashboard/contacts?lang=fr-CH" in sender.call_args.args[2]
    assert sender.call_args.kwargs == {"private": True}


def test_french_email_url_preserves_existing_query_and_fragment(notifications):
    web, _sender = notifications
    source = "https://openleg.ch/dashboard/invoices/42?filter=a%26b&lang=de#detail"
    with web.test_request_context("/?lang=fr"):
        assert (
            localized_url(source)
            == "https://openleg.ch/dashboard/invoices/42?filter=a%26b&lang=fr-CH#detail"
        )
    with web.test_request_context("/"):
        assert localized_url(source) == source
