# SPDX-License-Identifier: AGPL-3.0-or-later
"""Header-authenticated advisory review and private owner in-app notices."""

import json

from flask import Blueprint, abort, jsonify, request

import database as db
from admin import require_admin
from advisories import MAX_BYTES, AdvisoryError

advisory_bp = Blueprint("advisories", __name__)


@advisory_bp.errorhandler(AdvisoryError)
def _error(exc):
    return jsonify(error=exc.code, field=exc.field), exc.status


@advisory_bp.before_request
def _bound_mutation():
    if request.method in ("POST", "PUT"):
        request.max_content_length = MAX_BYTES + 1
        if request.content_encoding or (request.content_length or 0) > MAX_BYTES:
            raise AdvisoryError("payload_too_large", 413)
        if (
            request.mimetype == "application/x-www-form-urlencoded"
            and len(request.get_data(cache=True)) > MAX_BYTES
        ):
            raise AdvisoryError("payload_too_large", 413)


def _admin():
    # require_admin's older endpoints accept query/form tokens. This catalog
    # admits only the explicit header, including on reads of reviewer identities.
    if not request.headers.get("X-Admin-Token"):
        abort(403)
    require_admin()


def _payload():
    if request.mimetype != "application/json":
        raise AdvisoryError("json_required", 415)
    raw = request.stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise AdvisoryError("payload_too_large", 413)
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise AdvisoryError() from None


@advisory_bp.route("/api/admin/advisories/v1/catalog", methods=["POST", "GET"])
def catalog():
    _admin()
    if request.method == "POST":
        return jsonify(db.create_advisory(_payload())), 201
    return jsonify(entries=db.list_advisory_catalog())


@advisory_bp.get("/api/admin/advisories/v1/catalog/<uuid:advisory_id>")
def history(advisory_id):
    _admin()
    return jsonify(revisions=db.get_advisory_history(str(advisory_id)))


@advisory_bp.post("/api/admin/advisories/v1/catalog/<uuid:advisory_id>/revisions")
def revise(advisory_id):
    _admin()
    return jsonify(db.append_advisory_revision(str(advisory_id), _payload())), 201


@advisory_bp.post(
    "/api/admin/advisories/v1/catalog/<uuid:advisory_id>/revisions/<int:revision>/publish"
)
def publish(advisory_id, revision):
    _admin()
    return jsonify(db.publish_advisory_revision(str(advisory_id), revision, _payload()))


@advisory_bp.route("/api/admin/advisories/v1/source-policy", methods=["GET", "POST"])
def source_policy():
    _admin()
    if request.method == "POST":
        return jsonify(db.set_advisory_source_policy(_payload())), 201
    return jsonify(db.get_advisory_source_policy())


@advisory_bp.route("/api/admin/advisories/v1/source-reviews", methods=["GET", "POST"])
def source_reviews():
    _admin()
    if request.method == "POST":
        return jsonify(db.record_advisory_source_review(_payload())), 201
    return jsonify(reviews=db.list_advisory_source_reviews())
