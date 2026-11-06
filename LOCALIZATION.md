# English-First UI and Localization Guide

## Current Policy

English (US, `en_US`) is the source language and the only shipping UI language.
`app/i18n.py` applies that locale and left-to-right layout immediately after
`QApplication` is created, before any widgets. The operating system language does
not select the application language. Qt's own standard buttons use their English
source text; application copy falls back to English without a translation file.

The implementation covers navigation, composer hints, suggestions, chat role and
timing labels, demo content, Settings, About, window controls, update dialogs,
application-owned service errors, provider preset copy, and the MSI downgrade error.
No new runtime dependency or custom translation engine is needed.

This is translation-ready English standardization, not a multilingual release.
There is no language picker, live switching, or runtime catalog loader yet.
Do not add empty English JSON files or duplicate English strings in a dictionary:
the literal source messages are the authoritative English catalog.

## Ownership Boundaries

| Content | Policy |
| --- | --- |
| Application labels, actions, help, validation, errors, tooltips, accessibility text | Write in English and mark for Qt extraction. |
| Application-provided suggestions and demo messages | English, extractable; suggestions become a prompt only when selected. |
| User messages, saved titles, profile names, system instructions | Preserve exactly; never translate or rewrite existing data. |
| Provider responses, release notes, OS/network error details | Preserve original content; translate the application-owned wrapper only. |
| Model/provider IDs, URLs, JSON/QSettings keys, credential references, object names | Stable technical values, never translation keys. |
| Provider preset labels used as initial stored names | Canonical English defaults; do not translate at import or rewrite stored names. |
| Bundled license text, copyright names, product names | Preserve verbatim; translate explanatory headings separately. |
| Installer copy | English in WiX; independent of Qt catalogs. |

`Conversation.title == "New chat"` is an existing persisted sentinel used for
automatic title generation. Keep that model value stable. Translate the fallback
only at the presentation boundary. Do not migrate historical conversations just
to change their language. Newly generated connection names may use presentation
copy, but saved names must not change when a future locale changes.

## Message Architecture

Use Qt's native context-and-source identity, not a second key-value framework.
A widget or QObject owns its messages through `self.tr()`. Non-QObject helpers
use a stable, explicit `QCoreApplication.translate()` context.

```python
button = QPushButton(self.tr("Save changes"))
button.setAccessibleName(self.tr("Save changes"))

message = self.tr("Version {version} is available.").format(version=release.version)

raise ValueError(QCoreApplication.translate(
    "ConnectionProfile", "Use a valid http:// or https:// base URL."
))
```

- Translate a literal complete message before interpolation. Never use
  `self.tr(f"Version {version}")`, `self.tr(variable)`, or translate fragments
  such as a verb inserted into a longer sentence.
- Use named placeholders, preserving names, conversions, and format specs in
  translations. Translators may reorder `{version}` and `{detail}`, not rename them.
- Resolve messages when constructing a view or displaying/emitting an error.
  Module-level translated dictionaries freeze the language at import time.
- Reuse a context for the same feature, but do not force unrelated messages into
  a global "Common" namespace. Different meanings of the same English word may
  require different contexts or Qt disambiguation comments.
- Keep context names stable. Renaming a QObject class changes translation identity;
  review the catalog diff and carry translations forward during that refactor.
- Service errors are translated at their producer today because signals deliver
  text. If the application gains a non-Qt backend or multiple frontends, introduce
  stable error codes plus parameters and translate at each frontend boundary.
  Never branch business logic on translated exception text.

### Plurals and Formatting

Use Qt numerus support (`self.tr(source, None, count)` and `%n`), not concatenated
suffixes or an English-only plural rule for every language. This English-only
build uses distinct **complete** singular and plural source messages for counts:

```python
message = (
    self.tr("%n model found. Changes have not been saved.", None, count)
    if count == 1 else
    self.tr("%n models found. Changes have not been saved.", None, count)
)
```

Qt replaces `%n` without a catalog but cannot inflect an English plural source.
When translating these two entries, supply every plural form for both entries;
Qt chooses the target-language form for the actual count. Zero, one, two, and
larger counts must be tested. Avoid inventing a generic plural engine.

Keep wire formats and persisted data locale-neutral. For future locale-aware
display of dates, numbers, and units, use `QLocale` explicitly; Python's `.format`
precision does not automatically adopt Qt locale rules. Existing timing labels
intentionally keep a one-decimal English format. Set `PlainText` for dynamic
errors, names, and external data. For intentional rich text, translate the whole
template, preserve tags and safe URLs, and HTML-escape substituted untrusted text.

### English Style

Use sentence case for actions and descriptions, concise active verbs, and the
same term for the same concept: **chat**, **connection**, **model**, **API key**,
**Settings**, **Save changes**, and **Fetch models**. Explain recovery in errors
where possible. Describe destructive operations explicitly. Preserve intentional
uppercase role and history headings. Localize tooltips and accessible names as
carefully as visible labels. Keyboard shortcuts and technical identifiers must
still match the real behavior.

## Translation Files at Scale

When another language is actually approved, create this structure:

```text
app/resources/i18n/
  playgrounds_fr_FR.ts   # reviewed, version-controlled translator source
  playgrounds_fr_FR.qm   # compiled runtime artifact
  playgrounds_ja_JP.ts
  playgrounds_ja_JP.qm
```

Start with one `.ts` file per supported locale. Qt contexts partition it by
feature, avoiding dozens of hand-maintained files or duplicated English keys.
Feature owners review their context; a language reviewer approves terminology
and plural forms. For much larger products, split catalogs by independently
released feature, while preserving contexts and installing all required catalogs.

Extraction is available in the existing PyQt6 dependency. From the repository
root, after creating `app/resources/i18n`, an example workflow is:

```powershell
python -X utf8 -m PyQt6.lupdate.pylupdate app --ts app/resources/i18n/playgrounds_fr_FR.ts
linguist app/resources/i18n/playgrounds_fr_FR.ts
lrelease -nounfinished app/resources/i18n/playgrounds_fr_FR.ts -qm app/resources/i18n/playgrounds_fr_FR.qm
```

`linguist` and `lrelease` come from a compatible Qt Linguist Tools installation;
they are not guaranteed by the Python dependency. Pin their versions in the
release environment when languages are added. Keep catalogs on the same drive
as the source on Windows: the extractor records relative source locations.
`-X utf8` avoids Windows console-encoding failures. Set the TS source language to
`en_US` and target language to its filename locale in Linguist.

Commit reviewed `.ts` files. Produce `.qm` files deterministically during release
builds before PyInstaller; do not hand-edit them. Review newly extracted messages,
obsolete entries, and changed English copy in the same pull request as the code.
Only remove obsolete translations after review, not automatically during normal
extraction. Treat a source wording change as a translation-key change.

`build/playgrounds.spec` already includes `playgrounds_*.qm` from this directory.
The following steps are still required before shipping a non-English locale:

1. Extend `app/i18n.py` with an explicit supported-locale allowlist and locale
   resolution: exact supported locale, approved language fallback, then English.
   Never load an arbitrary filesystem path from a setting.
2. Load `QTranslator` objects before constructing widgets. Retain them for the
   QApplication lifetime. Load application catalogs and matching Qt standard-widget
   catalogs; missing/unfinished entries must safely use English source text.
3. Update the spec's current Qt `/translations/` trimming to retain only the
   approved `qtbase` catalogs. Application catalogs alone do not translate Qt's
   standard dialog buttons.
4. Add compilation, placeholder/plural validation, translation-completeness policy,
   and packaged-catalog smoke tests to `build/build.ps1` before enabling a locale.
   Keep incomplete entries unfinished so `-nounfinished` leaves English fallback.
5. Prefer restart-required locale selection initially. Live switching requires
   `LanguageChange` handling for every existing view and dynamically generated
   status, menu, model, and cached label, not just loading a new translator.
6. Support right-to-left layout and locale-specific fonts when such locales ship.
   Do not retain the current English-only left-to-right policy for those releases.

WiX requires a separate `.wxl` localization/build strategy if localized installers
are added. Qt catalogs do not cover installer messages.

## Repeatable UI Audit

Record each surface with its owner, source/context, trigger/state, visible copy,
accessibility copy, and verification result. Audit states, not just files.

| Surface | States to exercise |
| --- | --- |
| Sidebar and title bar | Empty history, long/user-defined titles, context menu, hide/show, maximize/restore |
| Composer and empty state | Suggestions, no connection, no model, ready, sending, stop, keyboard hints |
| Chat view | User/assistant roles, waiting, streaming, timing, stopped/failed response, reopening |
| Connections | Presets, blank/invalid URL, saved/revealed/removed key, fetch cancel/error/empty/success, filter, singular/plural counts |
| Save/discard | Unsaved drafts, destructive confirmation, validation, credential failure/rollback, settings persistence failure |
| Appearance and About | Both themes, every tab, links, accessible descriptions, expanded license, narrow/small window |
| Updates | Checking, current/new/skipped version, source-build restriction, download/progress/retry, verification and installation failure |
| Packaging | Fresh install, upgrade/downgrade copy, offline launch, standard Qt controls |

1. Inventory widgets, menu actions, message boxes, helper functions, service error
   producers, static message tables, accessibility metadata, and installer copy.
   Follow signals back to error producers; a widget-only audit misses those strings.
2. Classify each string using the ownership table. Normalize app copy to English
   without changing behavior, user data, legal content, or technical identifiers.
3. Mark every application-owned message for extraction. Verify dynamic paths and
   complete templates, including streaming headings and validation failures.
4. Run the automated gates below. Extend `TEXT_ARGUMENTS` in `tests/test_i18n.py`
   whenever adding a new presentation helper. Keep exceptions narrow and documented.
5. Exercise the matrix manually at the minimum supported window size and high DPI,
   with both themes, long strings, keyboard navigation, and a screen reader.
   Use pseudo-expanded copy to expose clipping before accepting a real locale.
6. Attach audit results to the change review. A locale is release-ready only when
   its translated and packaged UI passes the same matrix, including missing-entry
   English fallback and unmodified user/provider text.

```powershell
python -m pytest tests/test_i18n.py
python -m pytest
python -m ruff check .
python -m app --smoke --demo
```

The localization tests cover common literal-bearing Qt/project sinks, literal
translation sources, real native extraction, source template parsing, English
locale/layout, singular/plural fallback, synthetic expanded translation dispatch,
user-text preservation, service errors, and installer copy. The existing build
runs pytest and Ruff, so these checks participate in its gates automatically.

Static analysis is deliberately not a proof that every visible string is English.
It cannot infer the language of prose or follow arbitrary values through variables,
new helper APIs, HTML builders, or third-party code. The synthetic test exercises
selected surfaces, not full visual/accessibility approval. Human copy review and
the state matrix remain mandatory; an ASCII check or keyword blacklist is not a
substitute for either.
