# Phase 25: Data Model, Book Resolver & Extraction - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-03
**Phase:** 25-data-model-book-resolver-extraction
**Areas discussed:** Text cleaning strategy (verse text + book-name mojibake)

**Framing:** `docs/scriptures/SPEC.md` §12 locks nearly every Phase 25 decision (book field = digit form, D&C `Sections`→"Doctrine and Covenants", CiteAbbr references, exclude the 10 NULL-`Verse` rows → 41,996 canonical, `source_flag` kept, radius default 1). The only genuinely-open item was SPEC Open Q1 (HTML/encoding cleaning scope). Of three surfaced gray areas, the user selected only **Text cleaning strategy**; the other two (resolver failure contract, test data strategy) were noted as deferred.

---

## Verse Text Cleaning (EXT-03)

| Option | Description | Selected |
|--------|-------------|----------|
| New `clean_verse_text()` helper | Add to `html_parsing_utils.py`: fast-path `html.unescape` for plaintext, BS4 `get_text()` when `<` present. Unconditional no-tags guarantee, unit-testable without DB fixtures. | ✓ |
| Reuse `parse_html()` as-is | No new code, but built for full talk pages (body-container fallback, returns `None` on empty); mismatched for 5-word fragments, needs caller guard. | |
| `html.unescape` + regex tag strip | Fastest pure-stdlib, but regex-on-HTML edge cases and weaker "no residual tags" guarantee. | |

**User's choice:** New `clean_verse_text()` helper (recommended)
**Notes:** Helper also owns the UTF-8 bytes→str decode, giving extraction one decode+clean entry point. Fast-path skips BS4 for the ~99% plaintext verses, so perf is a non-issue across ~73k rows.

---

## Book-Name Mojibake Repair (EXT-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Targeted `�`→em-dash in `canonicalize()` | One-line scoped replacement on book-table fields, run once at resolver build. Exact for the lost-byte case, no new dep, trivially testable. | ✓ |
| `ftfy.fix_text()` | Inapplicable: ftfy recovers wrong-codec text; U+FFFD means the em-dash byte is already lost, so ftfy passes it through unchanged. | |
| Explicit closed-set hardcode | Zero false-positive risk but brittle to DB version bumps, more code for same result. | |

**User's choice:** Targeted `�`→em-dash replacement in `canonicalize()` (recommended)
**Notes:** Key nuance surfaced by research — the mojibake is the Unicode replacement character (U+FFFD), not a recoverable wrong-codec artifact. ftfy is definitively the wrong tool here. Replacement is scoped to the closed 99-row `book` table; the "U+FFFD in book names = em-dash" invariant should be documented and guarded by a unit test.

---

## Claude's Discretion

- `BookVerses` container shape and grouping-key representation.
- SQL/join structure for `scripture` ⋈ `book` (+parent for `volume`), using `from db import CORE_DB_PATH`.
- Internal structure of the resolver alias lookup (as long as it accepts all SPEC §9 input forms and returns canonical digit-form `book`).

## Deferred Ideas

- **Resolver failure/ambiguity contract** — raise vs return `None` on unresolvable input; alias-collision precedence. Not selected for discussion; settle in planning or defer to Phase 28 (where `get_verse`/`search` consume the resolver).
- **Test data strategy** — live `core.52.db` (skip-if-unavailable) vs synthetic fixtures vs both for the 41,996 assertion. Not selected; both patterns exist in-repo; planner's call.
- Study apparatus, headings, cross-refs, late chunking, embedding-model swap — all v2 / out of scope per REQUIREMENTS.md.
