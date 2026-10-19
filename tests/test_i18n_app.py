# SPDX-License-Identifier: AGPL-3.0-or-later
"""French public API messages and confirmation mail through actual route seams."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import has_app_context, has_request_context

import app
import meter_data
import registration
import security_utils
import tenant
from tests import test_i18n

web = test_i18n.web


@pytest.fixture
def public_client(web, monkeypatch):
    monkeypatch.setattr(
        tenant,
        "get_tenant_config",
        lambda *args, **kwargs: {
            **tenant.DEFAULT_TENANT,
            "territory": "vully",
            "city_name": "Vully-les-Lacs",
            "platform_name": "BIVIS",
        },
    )
    monkeypatch.setattr(app, "send_email", MagicMock())
    return web.test_client()


@pytest.mark.parametrize(
    "path", ["check_potential", "register_anonymous", "register_interest"]
)
def test_empty_public_requests_return_french_error(public_client, path):
    response = public_client.post("/api/" + path + "?lang=fr-CH", json={})
    assert response.status_code == 400
    assert response.json == {"error": "Aucune donnée reçue."}


def test_registration_validation_keeps_domain_german_but_presents_french(public_client):
    response = public_client.post(
        "/api/register_anonymous?lang=fr-CH", json={"email": "not-an-email"}
    )
    assert response.status_code == 400
    assert response.json == {"error": "Adresse e-mail non valide."}
    assert (
        security_utils.validate_email_address("not-an-email")[2]
        == "Ungültige E-Mail-Adresse."
    )
    with pytest.raises(registration.RegistrationError) as error:
        registration.parse_roles(["unknown"])
    assert error.value.message == "Bitte wählen Sie gültige Rollen aus."


def test_check_potential_translates_error_but_preserves_reason(
    public_client, monkeypatch
):
    monkeypatch.setattr(
        app.data_enricher,
        "resolve_address_profile",
        lambda address: SimpleNamespace(
            source="fallback", live_status="upstream_unavailable"
        ),
    )
    response = public_client.post(
        "/api/check_potential?lang=fr-CH",
        json={"address": "Route du Lac 1, 1586 Vallamand"},
    )
    assert response.status_code == 422
    assert response.json == {
        "error": "L’adresse n’a pas pu être vérifiée avec certitude.",
        "can_register_interest": True,
        "reason": "upstream_unavailable",
    }


def test_unresolved_interest_confirmation_uses_request_language(
    public_client, monkeypatch
):
    monkeypatch.setattr(
        app.db, "search_municipality_profiles", lambda *args, **kwargs: []
    )
    save = MagicMock(return_value=True)
    monkeypatch.setattr(app.db, "save_coverage_request", save)
    response = public_client.post(
        "/api/register_interest?lang=fr-CH",
        json={
            "email": "one@example.ch",
            "plz": "1586",
            "municipality_name": "Vully-les-Lacs",
        },
    )
    assert response.status_code == 202
    assert response.json == {
        "accepted": True,
        "message": "Veuillez confirmer votre adresse e-mail.",
    }
    recipient, subject, body = app.send_email.call_args.args
    assert recipient == "one@example.ch"
    assert subject == "OpenLEG : confirmer votre intérêt"
    assert "Confirmez votre intérêt" in body
    assert save.call_args.kwargs["verification_token"] in body
    assert "/interest/confirm/" in body


def test_deferred_registration_confirmation_retains_locale_without_request(
    public_client, monkeypatch
):
    tasks = []

    class DeferredThread:
        def __init__(self, *, target, args, daemon):
            self.target, self.args = target, args
            assert daemon

        def start(self):
            tasks.append(self)

    monkeypatch.setattr(app.threading, "Thread", DeferredThread)
    saved = MagicMock(return_value=True)
    monkeypatch.setattr(app.db, "save_building", saved)
    monkeypatch.setattr(app.db, "track_event", MagicMock())
    monkeypatch.setattr(app.db, "get_referral_code", lambda *args: None)
    monkeypatch.setattr(app, "find_provisional_matches", lambda *args: None)
    monkeypatch.setattr(app, "collect_building_locations", lambda **kwargs: [])
    response = public_client.post(
        "/api/register_anonymous?lang=fr-CH",
        json={
            "email": "one@example.ch",
            "profile": {
                "building_id": "vully-1",
                "lat": 46.95,
                "lon": 7.06,
                "address": "Route du Lac 1",
            },
        },
    )
    assert response.status_code == 200
    assert response.json["verification_email_sent"] is True
    assert len(tasks) == 1
    app.send_email.assert_not_called()
    assert not has_request_context()
    assert not has_app_context()
    tasks[0].target(*tasks[0].args)
    assert not has_app_context()
    recipient, subject, body = app.send_email.call_args.args
    assert recipient == "one@example.ch"
    assert subject == "BIVIS : confirmer votre intérêt"
    assert "communauté électrique locale (CEL) à Vully-les-Lacs" in body
    token = saved.call_args.kwargs["verification_token"]
    assert "/confirm/" + token + "?lang=fr-CH" in body
    assert tasks[0].args[2:] == ("vully-1", "Route du Lac 1")


def test_meter_upload_validation_is_french(public_client, monkeypatch):
    invalid = public_client.post("/api/meter-data/upload?lang=fr-CH", json={"tier": 8})
    assert invalid.status_code == 400
    assert invalid.json == {"error": "tier doit valoir 1, 2 ou 3."}
    monkeypatch.setattr(app.db, "get_building", lambda *args: {"building_id": "one"})
    monkeypatch.setattr(app.db, "save_data_consent", MagicMock())
    response = public_client.post(
        "/api/meter-data/upload?lang=fr-CH",
        json={"building_id": "one", "csv_content": "not-a-meter-file"},
    )
    assert response.status_code == 200
    assert response.json["success"] is False
    assert response.json["errors"] == [
        "Aucune mesure trouvée dans le fichier. Veuillez utiliser l’export CSV d’EKZ."
    ]


def test_meter_parser_keeps_named_values_and_german_default(web):
    content = "Timestamp;Consumption (kWh)\nbad timestamp;1\n"
    with web.test_request_context("/?lang=fr-CH"):
        readings, errors = meter_data.parse_ekz_csv(content)
        assert readings == []
        assert errors[0] == "Ligne 2 : horodatage non valide « bad timestamp »"
    assert (
        meter_data.parse_ekz_csv(content)[1][0]
        == "Zeile 2: Ungültiger Zeitstempel 'bad timestamp'"
    )


def test_deletion_request_preserves_privacy_and_localizes_confirmation(
    public_client, monkeypatch
):
    from urllib.parse import parse_qs, urlsplit

    token = "5dc7c93b-2eae-4d13-9349-10b467667ec7"
    monkeypatch.setattr(app.security_utils, "generate_uuid", lambda: token)
    monkeypatch.setattr(app.db, "save_token", MagicMock(return_value=True))
    monkeypatch.setattr(app.db, "create_coverage_deletion_tokens", lambda email: [])
    lookup = MagicMock(return_value=[{"building_id": "vully-1"}])
    monkeypatch.setattr(app.db, "get_building_by_email", lookup)
    existing = public_client.post(
        "/unsubscribe?lang=fr-CH", data={"email": "one@example.ch"}
    )
    assert existing.status_code == 200
    assert (
        "Si une inscription existe, vous recevrez un lien de confirmation par e-mail."
        in existing.text
    )
    recipient, subject, body = app.send_email.call_args.args
    assert recipient == "one@example.ch"
    assert subject == "OpenLEG : confirmer la suppression"
    assert "Le lien est valable une heure." in body
    link = next(line for line in body.splitlines() if line.startswith("http"))
    assert urlsplit(link).path == "/unsubscribe/" + token
    assert parse_qs(urlsplit(link).query) == {"lang": ["fr-CH"]}
    app.db.save_token.assert_called_once_with(
        token, "vully-1", "unsubscribe", ttl_seconds=3600
    )
    lookup.return_value = []
    app.send_email.reset_mock()
    absent = public_client.post(
        "/unsubscribe?lang=fr-CH", data={"email": "missing@example.ch"}
    )
    assert absent.status_code == existing.status_code
    assert absent.text == existing.text
    app.send_email.assert_not_called()


def test_deletion_confirmation_translates_success_and_expiration(
    public_client, monkeypatch
):
    token = "5dc7c93b-2eae-4d13-9349-10b467667ec7"
    monkeypatch.setattr(
        app.db, "get_token", lambda value: {"token_type": "unsubscribe"}
    )
    confirm = MagicMock(return_value=False)
    monkeypatch.setattr(app.db, "confirm_profile_deletion", confirm)
    expired = public_client.post("/unsubscribe/" + token + "?lang=fr-CH")
    assert expired.status_code == 409
    assert "Vos données n’ont pas été supprimées." in expired.text
    confirm.assert_called_once_with(token)
    confirm.return_value = True
    success = public_client.post("/unsubscribe/" + token + "?lang=fr-CH")
    assert success.status_code == 200
    assert "Vos données ont été supprimées." in success.text
    app.send_email.assert_not_called()


def test_german_deletion_confirmation_link_keeps_original_url(
    public_client, monkeypatch
):
    token = "5dc7c93b-2eae-4d13-9349-10b467667ec7"
    monkeypatch.setattr(app.security_utils, "generate_uuid", lambda: token)
    monkeypatch.setattr(
        app.db, "get_building_by_email", lambda email: [{"building_id": "one"}]
    )
    monkeypatch.setattr(app.db, "save_token", lambda *args, **kwargs: True)
    monkeypatch.setattr(app.db, "create_coverage_deletion_tokens", lambda email: [])
    response = public_client.post("/unsubscribe", data={"email": "one@example.ch"})
    assert response.status_code == 200
    _, subject, body = app.send_email.call_args.args
    assert subject == "OpenLEG: Löschung bestätigen"
    link = next(line for line in body.splitlines() if line.startswith("http"))
    assert link.endswith("/unsubscribe/" + token)
    assert "?lang=" not in link
