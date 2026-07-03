# Phase 25: Data Model, Book Resolver & Extraction - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn `db/core.52.db` rows into clean, canonical `ScriptureVerse` objects **in memory** — no live stack (no Weaviate, no Ollama). Pure/offline and fully unit-testable. Delivers:
- `models/scripture_data.py` — `ScriptureVerse` dataclass + a `BookVerses` per-(book, chapter, variant) container
- `config/book_resolver.py` — `canonicalize()` (build-time) + `resolve(user_input)` (query-time)
- `extractors/scripture_extraction.py` — read → decode/clean → normalize → group
- Tests: `tests/test_scripture_extraction.py`, `tests/test_book_resolver.py`
- Config additions in `config/pipeline_config.py`

Covers requirements **EXT-01…EXT-05, RES-01**. Windowing, validation, loading, and the MCP tool surface are explicitly **later phases (26–28)** — not this one.

</domain>

<decisions>
## Implementation Decisions

Nearly all of Phase 25's design is **locked by `docs/scriptures/SPEC.md` §12 "Resolved decisions"** (see canonical refs). Those are carried forward, not re-decided. The discussion resolved the SPEC's one genuinely-open item (Open Q1: HTML/encoding cleaning scope).

### Text Cleaning (EXT-03) — resolved Open Q1
- **D-01:** Add a purpose-built `clean_verse_text(raw)` helper to `extractors/html_parsing_utils.py` (per the "shared utilities live in html_parsing_utils / separate files" convention). Contract: bytes/str in → clean `str` out, **unconditional "no residual HTML tags" post-condition**, unit-testable without DB fixtures.
- **D-02:** Implementation shape: fast-path `if '<' not in text: return html.unescape(text.strip())` for the ~99% plaintext verses; fall back to BeautifulSoup `get_text()` (DOM-level, not regex) when markup is present. Keeps the no-tags guarantee strong while avoiding BS4 overhead on the common case — perf is a non-issue across ~73k rows.
- **D-03:** The helper owns the UTF-8 **decode** step too (SPEC: `Text` is stored as UTF-8 bytes), so extraction gets a single decode+clean entry point.
- **Rejected:** reusing `parse_html()` as-is (built for full talk pages, returns `None` on empty, semantically mismatched for 5-word fragments); pure `html.unescape` + regex tag-strip (weaker formal guarantee, known regex-on-HTML edge cases).

### Book-Name Mojibake Repair (EXT-04)
- **D-04:** Repair the mangled em-dash with a **targeted deterministic replacement** `'�' → '—'` (em-dash), **scoped to the `book` table fields** (`FullName`, `CiteAbbr`), run **once in `book_resolver.canonicalize()`** at resolver build time — not per verse.
- **D-05:** Document the invariant that justifies this: within the closed, enumerable 99-row `book` table, every U+FFFD in a name is a lost em-dash byte. If a future DB version introduces a different bad byte in book names, a validation/unit test should catch it.
- **Rejected — `ftfy`:** definitively the **wrong tool** for this failure mode. ftfy recovers *wrong-codec* text (e.g. `â€"` → `—`) where the original bytes survive. The mojibake here is the Unicode **replacement character (U+FFFD)** — the em-dash byte was already *lost* during a prior bad decode, so there is nothing for ftfy to re-decode; it passes U+FFFD through unchanged. Adding the dependency would give false confidence and fix nothing.
- **Rejected — closed-set hardcode by `book_id`:** zero false-positive risk but brittle to DB version bumps and more code for the same result.

### Claude's Discretion (planner/executor)
- Exact `BookVerses` container shape and grouping-key representation.
- SQL/join structure for reading `scripture` ⋈ `book` (+parent for `volume`), using the existing `from db import CORE_DB_PATH` access pattern.
- Internal structure of the resolver alias lookup (as long as it accepts FullName / Abbr / CiteAbbr / word↔digit ordinals / "D&C" / "Doctrine and Covenants", case/period/space-insensitive, and returns the canonical digit-form `book`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scripture v1 design (authoritative)
- `docs/scriptures/SPEC.md` — the full v1 spec. **Read §3 (data source: `scripture`/`book` tables, Flag partitioning, the 10 NULL-`Verse` exclusions, D&C `Sections` flatness, Nephi word-ordinals, em-dash mojibake), §4 (`ScriptureVerse` dataclass), §7 (pipeline stages — Phase 25 is Stage 1 Extract), §9 (`book_resolver` contract), and §12 (Resolved decisions — nearly every Phase 25 choice is locked here).** §13 "Phase 1" is this phase.
- `.planning/REQUIREMENTS.md` — EXT-01…EXT-05, RES-01 (this phase's requirements) and the Out-of-Scope table (v2 study apparatus, headings, etc.).
- `.planning/ROADMAP.md` §"Phase 25" — goal + 5 success criteria the checkpoint must satisfy (exactly 41,996 canonical verses, digit-form book normalization, CiteAbbr references, resolver alias coverage, green unit tests).

### Reusable code (patterns to follow)
- `extractors/html_parsing_utils.py` — where `clean_verse_text()` will be added; existing `parse_html`, `render_span_text`, `get_text(strip=True)` usage shows the established BS4 cleaning idiom.
- `db/__init__.py` — `CORE_DB_PATH` (points at `db/core.52.db`); the DB access pattern to reuse (SPEC's "resolve like the talk pipeline" = `from db import CORE_DB_PATH`).
- `extractors/phase1_talk_metadata.py`, `models/talk_metadata.py` — data-model + extractor structure to mirror.
- `tests/test_phase1.py` (live-DB, skip-if-unavailable pattern) and `tests/conftest.py` (synthetic fixtures) — the two available test-data approaches (test strategy was surfaced but not selected for deep discussion; planner may choose).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `extractors/html_parsing_utils.py`: BeautifulSoup is already a hard dependency; `soup.get_text(strip=True)` is used across Phases 1–4. `clean_verse_text()` slots in here as a sibling helper.
- `db.CORE_DB_PATH`: DB path is already a solved import (`db/core.52.db`) — no new versioned-path resolution logic required despite the SPEC's phrasing.
- `models/*_data.py` dataclasses + `extractors/phase*_*.py` extractors: direct structural analogs for `scripture_data.py` and `scripture_extraction.py`.

### Established Patterns
- Cleaning helpers live in `html_parsing_utils.py`; config constants in `config/pipeline_config.py`; new shared logic in new files (not bolted onto existing modules).
- Tests either hit the live core DB with a skip-if-unavailable guard (`test_phase1`) or build synthetic fixtures (`conftest`).

### Integration Points
- `config/book_resolver.py` is the **shared dependency** consumed later by both the pipeline (Phase 27) and the MCP tools `get_verse`/`search` (Phase 28). Its canonical output must equal the stored `book` value exactly.

</code_context>

<specifics>
## Specific Ideas

- `clean_verse_text` fast-path: `if '<' not in text: return html.unescape(text.strip())` else BS4 `get_text()`.
- Mojibake repair one-liner (scoped to book fields, in `canonicalize()`): `name.replace('�', '—')`.
- Expected canonical count assertion: **exactly 41,996** (`S` rows minus the 10 NULL-`Verse` front-matter rows; `E` rows never appear).

</specifics>

<deferred>
## Deferred Ideas

- **Resolver failure/ambiguity contract** (raise vs return `None` on unresolvable input; alias-collision precedence) — surfaced as a candidate gray area but not selected. The SPEC's resolver contract (§9) covers the accepted input forms; the error-path detail can be settled by the planner or deferred to Phase 28 where `get_verse`/`search` consume it.
- **Test data strategy** (live `core.52.db` vs synthetic fixtures vs both for the 41,996 assertion) — surfaced but not selected. Both patterns exist in the repo; planner's call.
- Study apparatus, headings, cross-refs, late chunking, embedding-model swap — all explicitly **v2 / out of scope** per REQUIREMENTS.md.

</deferred>

---

*Phase: 25-data-model-book-resolver-extraction*
*Context gathered: 2026-07-03*
