# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request-local presentation languages; domain values remain language-neutral."""

import re
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from babel.dates import format_date
from flask import current_app, has_app_context, has_request_context, request, session
from flask_babel import Babel, get_locale
from flask_babel import gettext as babel_gettext
from flask_babel import ngettext as babel_ngettext

SUPPORTED_LOCALES = {"de_CH": "Deutsch", "fr_CH": "Français"}


def format_period_label(value):
    """Localize display month names without changing frozen invoice values."""
    months = (
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    )
    match = re.fullmatch(r"([A-Za-zä]+) ([0-9]{4})", str(value))
    if not match or match[1] not in months:
        return value
    locale = (
        str(get_locale())
        if has_app_context() and "babel" in current_app.extensions
        else "de_CH"
    )
    # Preserve existing German casing and formatting byte for byte.
    if locale == "de_CH":
        return value
    return format_date(
        date(int(match[2]), months.index(match[1]) + 1, 1),
        format="MMMM yyyy",
        locale=locale,
    )


def gettext(message, **variables):
    """Keep domain helpers usable without a configured Flask application."""
    if not has_app_context() or "babel" not in current_app.extensions:
        return message % variables if variables else message
    return babel_gettext(message, **variables)


def ngettext(singular, plural, number, **variables):
    """Use the catalog's plural rules when available, German otherwise."""
    if not has_app_context() or "babel" not in current_app.extensions:
        message = singular if number == 1 else plural
        return message % {"num": number, **variables}
    return babel_ngettext(singular, plural, number, **variables)


def normalize_locale(value):
    """Resolve only the shipped catalogs, never an arbitrary catalog path."""
    aliases = {
        "de": "de_CH",
        "de-CH": "de_CH",
        "de_CH": "de_CH",
        "fr": "fr_CH",
        "fr-CH": "fr_CH",
        "fr_CH": "fr_CH",
    }
    return aliases.get(value) if isinstance(value, str) else None


def select_locale():
    """An explicit choice wins, then the signed session, then instance default.

    Keep German as the existing default instead of silently switching existing
    installations based on a browser's Accept-Language header.
    """
    default = (
        normalize_locale(current_app.config.get("BABEL_DEFAULT_LOCALE")) or "de_CH"
    )
    if not has_request_context():
        return default
    return (
        normalize_locale(request.args.get("lang"))
        or normalize_locale(session.get("locale"))
        or default
    )


def language_switch_url(locale):
    """Retain page/filter context without accepting a redirect destination."""
    selected = normalize_locale(locale)
    if selected is None:
        raise ValueError("Unsupported display language")
    if not has_request_context():
        return "/?" + urlencode({"lang": selected.replace("_", "-")})
    arguments = [
        (key, value) for key, value in request.args.items(multi=True) if key != "lang"
    ]
    arguments.append(("lang", selected.replace("_", "-")))
    return "/" + request.path.lstrip("/") + "?" + urlencode(arguments)


def localized_url(url, locale=None):
    """Carry a French display choice into generated invitation/access links."""
    selected = normalize_locale(locale)
    if selected is None:
        selected = (
            str(get_locale())
            if has_app_context() and "babel" in current_app.extensions
            else select_locale()
            if has_app_context()
            else "de_CH"
        )
    if selected == "de_CH":
        return url
    parts = urlsplit(url)
    arguments = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "lang"
    ]
    arguments.append(("lang", selected.replace("_", "-")))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(arguments), parts.fragment)
    )


def init_app(app):
    """Install gettext in Python/Jinja and publish presentation-only metadata."""
    app.config.setdefault("BABEL_DEFAULT_LOCALE", "de_CH")
    app.config.setdefault("BABEL_DEFAULT_TIMEZONE", "Europe/Zurich")
    default = normalize_locale(app.config["BABEL_DEFAULT_LOCALE"])
    if not default:
        raise ValueError("BABEL_DEFAULT_LOCALE must be de_CH or fr_CH")
    app.config["BABEL_DEFAULT_LOCALE"] = default
    Babel(app, configure_jinja=False, locale_selector=select_locale)
    app.jinja_env.add_extension("jinja2.ext.i18n")
    # Old-style Jinja preserves literal '%' in German source text. Flask-Babel's
    # gettext still supports named interpolation when kwargs are supplied.
    app.jinja_env.install_gettext_callables(gettext, ngettext, newstyle=False)
    app.jinja_env.filters["periodlabel"] = format_period_label
    app.jinja_env.filters["localized_url"] = localized_url

    @app.before_request
    def remember_language():
        selected = normalize_locale(request.args.get("lang"))
        if request.method == "GET" and selected and request.endpoint != "static":
            session["locale"] = selected

    @app.context_processor
    def language_context():
        return {
            "current_locale": str(get_locale()).replace("_", "-"),
            "supported_locales": SUPPORTED_LOCALES,
            "language_switch_url": language_switch_url,
        }

    @app.after_request
    def language_headers(response):
        if response.mimetype == "text/html":
            response.headers["Content-Language"] = str(get_locale()).replace("_", "-")
            response.vary.add("Cookie")
        return response
