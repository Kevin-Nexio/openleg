# SPDX-License-Identifier: AGPL-3.0-or-later
"""Advisory review/publication and private owner actions through real HTTP/PostgreSQL."""

import pytest

from tests import test_equipment, test_interest_postgres
from tests.test_advisories_domain import entry

app_module = test_equipment.app_module
interest_database = test_interest_postgres.interest_database
equipment_client = test_equipment.equipment_client
pytestmark = pytest.mark.integration
ADMIN = "/api/admin/advisories/v1"
ADMIN_HEADERS = {"X-Admin-Token": "advisory-admin-test"}
OWNER_HEADERS = {"X-CSRF-Token": "csrf-secret"}


@pytest.fixture
def client(equipment_client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "advisory-admin-test")
    return equipment_client


def test_catalog_starts_empty_and_draft_creation_is_header_authenticated(client):
    assert client.get(ADMIN + "/catalog", headers=ADMIN_HEADERS).json == {"entries": []}
    assert client.post(ADMIN + "/catalog", json=entry()).status_code == 403
    assert (
        client.post(
            ADMIN + "/catalog?token=advisory-admin-test", json=entry()
        ).status_code
        == 403
    )
    response = client.post(ADMIN + "/catalog", json=entry(), headers=ADMIN_HEADERS)
    assert response.status_code == 201, response.text
    draft = response.json
    assert draft["revision"] == 1
    assert draft["state"] == "draft"
    assert draft["review"] is None
    assert len(draft["digest"]) == 64
    assert draft["entry"]["source_revision"] == "1.0"
    assert client.get(ADMIN + "/catalog", headers=ADMIN_HEADERS).json["entries"] == [
        draft
    ]
    assert response.headers["Cache-Control"] == "no-store"


def review(draft, **changes):
    from datetime import UTC, datetime

    return {
        "digest": draft["digest"],
        "reviewer_id": "PRIVATE-MAINTAINER",
        "reviewed_on": datetime.now(UTC).date().isoformat(),
        "approve": True,
        **changes,
    }


def test_exact_revision_review_keeps_corrections_superseded_and_withdrawn_sources(
    client,
):
    draft = client.post(ADMIN + "/catalog", json=entry(), headers=ADMIN_HEADERS).json
    path = ADMIN + "/catalog/" + draft["advisory_id"]
    publish = path + "/revisions/1/publish"
    assert (
        client.post(
            publish, json=review(draft, digest="0" * 64), headers=ADMIN_HEADERS
        ).status_code
        == 409
    )
    assert (
        client.post(
            publish, json=review(draft, approve=False), headers=ADMIN_HEADERS
        ).status_code
        == 400
    )
    assert (
        client.post(
            publish, json=review(draft, reviewed_on="2024-01-01"), headers=ADMIN_HEADERS
        ).status_code
        == 400
    )
    assert (
        client.post(
            publish, json=review(draft, reviewed_on="9999-01-01"), headers=ADMIN_HEADERS
        ).status_code
        == 400
    )
    assert (
        client.post(publish, json=review(draft), headers=ADMIN_HEADERS).status_code
        == 200
    )
    corrected = client.post(
        path + "/revisions",
        json=entry(
            source_revision="2.0",
            summary="Corrected source text",
            change_note="Publisher correction",
        ),
        headers=ADMIN_HEADERS,
    )
    assert corrected.status_code == 201, corrected.text
    corrected = corrected.json
    assert corrected["revision"] == 2
    history = client.get(path, headers=ADMIN_HEADERS).json["revisions"]
    assert (
        history[0]["entry"]["summary"]
        == "Synthetic test evidence, not a published finding."
    )
    assert history[0]["state"] == "active"
    assert history[1]["state"] == "draft"
    assert (
        client.post(publish, json=review(draft), headers=ADMIN_HEADERS).status_code
        == 409
    )
    assert (
        client.post(
            path + "/revisions/2/publish", json=review(corrected), headers=ADMIN_HEADERS
        ).status_code
        == 200
    )
    history = client.get(path, headers=ADMIN_HEADERS).json["revisions"]
    assert [item["state"] for item in history] == ["superseded", "active"]
    withdrawn = client.post(
        path + "/revisions",
        json=entry(
            source_revision="3.0",
            status="withdrawn",
            change_note="Publisher withdrew this advisory",
        ),
        headers=ADMIN_HEADERS,
    ).json
    assert (
        client.post(
            path + "/revisions/3/publish", json=review(withdrawn), headers=ADMIN_HEADERS
        ).status_code
        == 200
    )
    history = client.get(path, headers=ADMIN_HEADERS).json["revisions"]
    assert [item["state"] for item in history] == [
        "superseded",
        "superseded",
        "withdrawn",
    ]
    assert history[0]["review"]["reviewer_id"] == "PRIVATE-MAINTAINER"
    assert history[1]["entry"]["summary"] == "Corrected source text"


def policy(**changes):
    return {
        "enabled": True,
        "review_owner": "PRIVATE-SOURCE-OWNER",
        "cadence_days": 14,
        "coverage": "Synthetic vendor source only; incomplete coverage.",
        "source_urls": ["https://example.com/advisory"],
        **changes,
    }


def source_review(policy_revision, **changes):
    from datetime import UTC, datetime

    return {
        "policy_revision": policy_revision,
        "review_owner": "PRIVATE-SOURCE-OWNER",
        "reviewed_on": datetime.now(UTC).date().isoformat(),
        "outcome": "success",
        "source_urls": ["https://example.com/advisory"],
        "failure_code": None,
        **changes,
    }


def test_named_source_review_cadence_and_failures_control_notice_readiness(client):
    path = ADMIN + "/source-policy"
    assert (
        client.get(path, headers=ADMIN_HEADERS).json["health"]["status"] == "disabled"
    )
    assert (
        client.post(
            path, json=policy(review_owner=""), headers=ADMIN_HEADERS
        ).status_code
        == 400
    )
    configured = client.post(path, json=policy(), headers=ADMIN_HEADERS)
    assert configured.status_code == 201, configured.text
    revision = configured.json["policy"]["revision"]
    assert configured.json["health"]["status"] == "unreviewed"
    source_path = ADMIN + "/source-reviews"
    assert (
        client.post(
            source_path,
            json=source_review(revision, review_owner="Wrong owner"),
            headers=ADMIN_HEADERS,
        ).status_code
        == 409
    )
    assert (
        client.post(
            source_path,
            json=source_review(revision, source_urls=[]),
            headers=ADMIN_HEADERS,
        ).status_code
        == 400
    )
    assert (
        client.post(
            source_path, json=source_review(revision), headers=ADMIN_HEADERS
        ).status_code
        == 201
    )
    health = client.get(path, headers=ADMIN_HEADERS).json["health"]
    assert health["status"] == "current"
    assert health["last_successful_review"] == source_review(revision)["reviewed_on"]
    assert "PRIVATE-SOURCE-OWNER" not in str(health)
    assert (
        client.post(
            source_path,
            json=source_review(
                revision, outcome="failure", failure_code="fetch_failed"
            ),
            headers=ADMIN_HEADERS,
        ).status_code
        == 201
    )
    health = client.get(path, headers=ADMIN_HEADERS).json["health"]
    assert health["status"] == "failed"
    assert health["last_successful_review"] is not None
    assert (
        client.post(
            source_path,
            json=source_review(revision, reviewed_on="2025-01-01"),
            headers=ADMIN_HEADERS,
        ).status_code
        == 201
    )
    assert client.get(path, headers=ADMIN_HEADERS).json["health"]["status"] == "stale"
    changed = client.post(path, json=policy(cadence_days=7), headers=ADMIN_HEADERS).json
    assert changed["health"]["status"] == "unreviewed"
    assert (
        client.post(
            source_path, json=source_review(revision), headers=ADMIN_HEADERS
        ).status_code
        == 409
    )
