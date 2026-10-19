# Internationalization

OpenLEG ships German (Switzerland, `de_CH`) and French (Switzerland, `fr_CH`).
German remains the default. The application uses Flask-Babel/gettext with German
source messages, one shared implementation and a French catalog. Contributions
remain under AGPL-3.0-or-later.

## Running in French

Use the Deutsch / Français links in the shared navigation, or append
`?lang=fr-CH` to an existing page. The language choice is kept in the signed Flask
session and survives dashboard and municipality login/logout. Invalid language
values are ignored. Existing route paths do not change.

To default an entire self-hosted instance to French, set:

```dotenv
BABEL_DEFAULT_LOCALE=fr_CH
```

Set a stable `SECRET_KEY` as described in the self-hosting instructions so signed
sessions work across workers and restarts. Browser `Accept-Language` does not
silently override the installation default. An explicit query choice wins over
the session choice, which wins over the instance default. The response's
`Content-Language` header describes the rendered language, and HTML responses
vary on Cookie.

## Coverage and boundaries

The French catalog covers the authored public pages, calculator, member and LEG
dashboards, billing forms, invoice detail and printable invoices, equipment and
advisory screens, municipality profiles and directories, LEG registry, utility
portal, confirmation emails and queued email templates. Metadata, accessibility
labels, inline JavaScript messages and authored JSON-LD are translated too.

Source data, participant-entered text, municipality/place names, technical API
identifiers, URLs and third-party Swagger UI controls are not translated. Existing
product screenshots are still German. French legal and contract text is a
working translation of the existing German content, not independent legal
validation; have it reviewed before using it for signatures or production.

The application preserves billing calculations, input parsing, rounding, frozen
snapshots and internal status values. Frozen CHF figures keep their existing
precision in both HTML and PDF; they are not recomputed through locale formatters.
Calculator browser display uses the selected locale. Recognized German billing
period labels are localized at the presentation boundary. Existing numeric
date formats and other preformatted backend numbers remain unchanged.

Confirmation emails capture the requesting language before their background
thread starts. Queued emails use an explicit `locale` on the queue item, then the
tenant locale, then `BABEL_DEFAULT_LOCALE`; they do not inherit the cron caller's
session. This contribution does not add a persistent per-participant language
column. A session choice alone does not change an existing recipient's queued
mail language. A French-default BIVIS instance sends those mails in French; a
mixed-language installation needs explicit recipient preferences in a later
storage contribution. Already generated/stored PDFs keep their generated language.

## Translation workflow

Activate the documented development environment first. The standard gettext
sources live in `translations/messages.pot` and
`translations/fr_CH/LC_MESSAGES/messages.po`. The compiled `.mo` is committed so
a checkout can render French immediately; the container rebuilds it from source.

```bash
python scripts/translations.py extract
pybabel update -i translations/messages.pot -d translations --no-fuzzy-matching
# Edit translations/fr_CH/LC_MESSAGES/messages.po
python scripts/translations.py compile
python scripts/translations.py check
scripts/tdd_cycle.sh gate
```

Use the project script for validation and compilation. Babel can misidentify
literal German prose such as `40% ohne` as a Python format string. The script
normalizes those false flags while still checking actual named placeholders.
It rejects missing/fuzzy translations, invalid placeholders and stale compiled
catalogs. New source messages must be translated before `check` passes. Restart
the local server after rebuilding catalogs because Babel caches translations.

Wrap complete sentences in `_()` or a Jinja `{% trans %}` block. Use named
placeholders, not a translated f-string assembled after interpolation:

```python
from i18n import gettext as _

text = _("Gemeinde: %(name)s", name=municipality_name)
```

Use `ngettext` for real counts. Preserve the municipality interest-count privacy
threshold; translating must not reveal suppressed counts. Never concatenate
sentence fragments just to avoid a placeholder.

Domain dictionaries and validation messages use
`translation_markers.gettext_noop` to mark text for extraction without changing
plain values, comparisons, serialization or stored snapshots. Translate those
values where they are displayed. Shared caches remain language-neutral; localize
copied presentation data after retrieval.

Jinja uses old-style gettext callables so literal percent signs keep their
original behavior. With named interpolation, escape a literal percent as `%%`.
Pass translated JavaScript values through `tojson`. Keep Jinja autoescaping and
the document generators' existing user-data escaping; never mark user input safe.

To add another language, create its gettext catalog and add its approved locale
to `SUPPORTED_LOCALES` and `normalize_locale` in `i18n.py`, then run the translation
and behavior checks. A locale is selectable only when explicitly supported.
