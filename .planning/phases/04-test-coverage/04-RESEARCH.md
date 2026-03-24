# Phase 4: Test Coverage - Research

**Researched:** 2026-03-23
**Domain:** Python testing (pytest), SQLite schema validation, pipeline integration testing
**Confidence:** HIGH

## Summary

This phase adds three independent test tracks: (1) end-to-end integration tests running real talks through the full Phase 1-5 pipeline against the actual database, (2) Phase 1 edge-case tests using in-memory SQLite fixtures, and (3) adversarial tests for Phase 5 validation. No new extraction capabilities are added.

The project already has a mature test suite (269 tests across 6 files) using pytest with well-established patterns: factory functions for data models, in-memory SQLite for DB-dependent tests, and co-located tests per phase. The existing `extractors/pipeline.py::process_talk_pipeline()` orchestrator handles Phases 1-4 in a single call, and `extractors/phase5_validation.py::validate_talk()` handles Phase 5 -- making integration test composition straightforward.

**Primary recommendation:** Use `process_talk_pipeline()` + `validate_talk()` for integration tests; build in-memory SQLite fixtures for Phase 1 edge cases matching the established pattern; extend existing `tests/test_phase5.py` with adversarial factory data for Phase 5.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Connect to the real DB read-only (`db/core.52.db` + `db/content.52.db`). No fixtures or copied DB -- tests run against actual data to catch real-world shape issues.
- **D-02:** Hardcode 3-5 specific `talk_id` values chosen during planning (one old/new era, one footnote-heavy, one citation-rich). Stable and explicit -- Claude selects these during planning by querying the DB.
- **D-03:** Assert schema + non-empty at each phase boundary: required fields present with correct types, at least one record per phase. Catches contract breaks without being brittle to data changes.
- **D-04:** Run all phases 1-5 end-to-end. Include Phase 1 DB query -- full integration path including the DB->Phase 1 boundary.
- **D-05:** New file: `tests/test_pipeline_integration.py` (exception to Phase 3 D-08 co-location pattern -- integration test warrants its own file per QUAL-04 spec).
- **D-06:** Use in-memory SQLite fixtures (not real DB talk_ids, not mocked DB layer). Build minimal SQLite DBs with only the rows needed per test -- consistent with existing Phase 2-4 approach of HTML fixture strings.
- **D-07:** All three edge cases are required: missing speaker, unusual session type (e.g., welfare/sustaining session), talk with no URL.
- **D-08:** Schema validation lives in `db/__init__.py` -- runs when the DB module is first used, natural home since DB module already owns connection setup and is imported by every phase.
- **D-09:** Hard fail on mismatch -- raise an exception that halts the pipeline immediately with a clear error message. No warn-and-continue.
- **D-10:** All four adversarial categories required: Missing/None fields, Wrong ID formulas, Empty collections, Extreme counts.
- **D-11:** Adversarial tests extend the existing `tests/test_phase5.py` -- consistent with Phase 3 D-08 co-location pattern.

### Claude's Discretion
- Specific `talk_id` values to hardcode for integration tests (Claude queries DB during planning to find representative talks)
- Exact threshold values for "extreme counts" adversarial tests
- Which expected tables/columns to validate in schema check

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUAL-04 | End-to-end integration test: `tests/test_pipeline_integration.py` runs 3-5 real talks through all phases and verifies phase-to-phase data contracts | DB research identified 5 candidate talk_ids covering all eras and characteristics; `process_talk_pipeline()` + `validate_talk()` provide the orchestration API |
| QUAL-05 | Phase 1 edge case tests: missing speaker, unusual session types, talks with no URL | In-memory SQLite fixture pattern established; DB research confirmed real examples of each edge case exist in the data |
| QUAL-06 | SQLite schema validation at startup: verify `core.52.db` schema matches expected structure | Full schema inventory of both DBs completed; `db/__init__.py` is the natural home per D-08 |
| QUAL-10 | Phase 5 adversarial test cases: malformed inputs, boundary conditions, unexpected data shapes | Existing `test_phase5.py` factory functions (`make_metadata`, `make_paragraph`, etc.) support all four adversarial categories |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | (latest via Pipfile) | Test framework | Already in use across all 269 existing tests |
| sqlite3 | stdlib | In-memory DB fixtures, schema validation | Already used in test_phase1.py for DDL tests |
| unittest.mock | stdlib | MagicMock for DB in adversarial tests | Already used in test_phase5.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | Factory helpers for test data | Extend existing factory pattern in test_phase5.py |

No new packages needed. Everything is already in Pipfile or stdlib.

## Architecture Patterns

### Recommended Test File Structure
```
tests/
  test_pipeline_integration.py    # NEW -- QUAL-04 integration tests
  test_phase1.py                  # EXTEND -- QUAL-05 edge cases, QUAL-06 schema validation tests
  test_phase5.py                  # EXTEND -- QUAL-10 adversarial tests
```

### Pattern 1: Integration Test via process_talk_pipeline + validate_talk
**What:** Use the existing pipeline orchestrator to run real talks end-to-end, then validate output with Phase 5.
**When to use:** QUAL-04 integration tests.
**Key API:**
```python
from extractors.pipeline import process_talk_pipeline, TalkPipelineResult
from extractors.phase5_validation import validate_talk
from extractors.phase3_citation_extraction import load_book_cache
from db import core_db, content_db

book_cache = load_book_cache(core_db)
config = {
    "html_parser": PARAGRAPH_HTML_PARSER,
    "min_length": MIN_PARAGRAPH_LENGTH,
    # ... from pipeline_config.py
}

result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, config)
report = validate_talk(result.metadata, result.paragraphs, result.citations, result.footnotes, db=core_db)
```

**Phase boundary assertions between each phase:**
- Phase 1 -> Phase 2: `result.metadata` is not None, has `talk_id`, `speaker_name`, `conference_year`
- Phase 2 -> Phase 3: `result.paragraphs.paragraphs` is non-empty, each has `paragraph_id`, `text`, `text_raw`
- Phase 3 -> Phase 4: `result.citations` has `extraction_success=True`, each citation has `citation_id`, `paragraph_id`
- Phase 4 -> Phase 5: `result.footnotes` has `extraction_success=True`, each footnote has `footnote_id`, `paragraph_id`
- Phase 5 output: `report.is_valid=True`, `report.errors == []`

### Pattern 2: In-Memory SQLite Fixture for Phase 1 Edge Cases
**What:** Build minimal SQLite databases in memory with only the rows needed per test.
**When to use:** QUAL-05 Phase 1 edge case tests.
**Example structure:**
```python
def _build_in_memory_core_db(talk_rows, speaker_rows, conference_rows, session_rows, conf_talk_rows, talk_metadata_rows=None):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE talk (ID INT PRIMARY KEY, Corpus TEXT, URL TEXT, Title TEXT, Date TEXT, SpeakerID INT, ...)")
    conn.execute("CREATE TABLE speaker (ID INT, GivenNames TEXT, LastNames TEXT, Abbr TEXT, ...)")
    # ... create all required tables
    # Insert provided rows
    # Return a Database-like wrapper or the connection
```

### Pattern 3: Adversarial Factories Extending Existing test_phase5.py
**What:** Use existing `make_metadata()`, `make_paragraph()`, etc. factories with deliberately malformed inputs.
**When to use:** QUAL-10 adversarial tests.
**Categories:**
1. Missing/None: Pass `None` for required fields like `paragraph_id`, `talk_id`
2. Wrong ID formulas: `paragraph_id` that does not match `talk_id * 10000 + paragraph_number`
3. Empty collections: 0 paragraphs, 0 citations, 0 footnotes
4. Extreme counts: 200+ paragraphs, very long text strings

### Anti-Patterns to Avoid
- **Mocking the DB layer for integration tests:** D-01 explicitly requires real DB. Integration tests must hit actual `core.52.db` and `content.52.db`.
- **Brittle value assertions in integration tests:** D-03 says assert schema + non-empty, not exact values. Talk content can change between DB versions.
- **Creating a new file for adversarial tests:** D-11 says extend `tests/test_phase5.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pipeline orchestration in tests | Manual phase-by-phase calls | `process_talk_pipeline()` | Already handles error propagation, shared HTML contexts, book cache |
| Book cache loading | Manual SQL + dict building | `load_book_cache(core_db)` | Already exists, returns `{book_id: row}` dict |
| Config dict construction | Hardcoded values | Import from `config/pipeline_config.py` | D-02 of Phase 2 code-quality centralized all constants there |
| Test data factories | New factory functions | Existing `make_metadata()`, `make_paragraph()`, etc. in test_phase5.py | Already battle-tested with correct field defaults |

## Common Pitfalls

### Pitfall 1: Windows Path / Encoding Issues
**What goes wrong:** Tests fail on Windows due to cp1252 encoding when reading files or DB paths with special characters.
**Why it happens:** Previous phases discovered this (Phase 03 decision: replace literal curly-quote bytes with `\u201c`/`\u201d` ASCII-safe escapes).
**How to avoid:** Use `encoding='utf-8'` on all file I/O. Use `os.path` or `pathlib` for paths. The DB module already handles this.
**Warning signs:** `UnicodeDecodeError` in test output.

### Pitfall 2: Database Print Statement in db/__init__.py
**What goes wrong:** `db/__init__.py` line 12 has `print(f"CURRENT_DIR: {CURRENT_DIR}")` which will print during every test import.
**Why it happens:** Debug statement left in module-level code.
**How to avoid:** This is existing behavior -- don't let it interfere with test output assertions. Consider removing it as part of schema validation changes to `db/__init__.py`.

### Pitfall 3: Schema Validation Breaking Existing Tests
**What goes wrong:** Adding schema validation to `db/__init__.py` that runs on import could break tests that use in-memory SQLite or mock DBs.
**Why it happens:** Module-level code in `db/__init__.py` creates `core_db` and `content_db` globals at import time.
**How to avoid:** Schema validation should run lazily (on first `_connect()` call) or be callable explicitly, not at import time. The global `core_db = Database(CORE_DB_PATH)` just creates the object -- validation should happen on first actual DB access.
**Warning signs:** Tests that don't need the real DB start failing because they import something that transitively imports `db`.

### Pitfall 4: Integration Test Assumes DB Files Exist
**What goes wrong:** `test_pipeline_integration.py` will fail if `db/core.52.db` or `db/content.52.db` are not present.
**Why it happens:** D-01 requires real DB access -- these are not committed to git.
**How to avoid:** Use `pytest.mark.skipif` or check DB existence in a fixture. Skip gracefully with a clear message if DBs are not available.
**Warning signs:** `FileNotFoundError` in CI or on a fresh clone.

### Pitfall 5: Config Dict Missing Keys
**What goes wrong:** `process_talk_pipeline()` expects a `config` dict with specific keys like `html_parser`, `min_length`. Missing keys cause KeyError or incorrect defaults.
**Why it happens:** The config dict is built ad-hoc in test code without referencing `pipeline_config.py`.
**How to avoid:** Build config from `pipeline_config.py` constants. Reference existing test patterns (e.g., `test_phase3.py` or `scripts/run_audit.py`) for the correct config shape.

## Code Examples

### Integration Test Config Building
```python
from config.pipeline_config import (
    PARAGRAPH_HTML_PARSER,
    MIN_PARAGRAPH_LENGTH,
    NORMALIZE_WHITESPACE,
    STRIP_FOOTNOTE_MARKERS,
    DECODE_ENTITIES,
    CONTEXT_BEFORE_CHARS,
    CONTEXT_AFTER_CHARS,
    CONTEXT_WINDOW_MODE,
)

PIPELINE_CONFIG = {
    "html_parser": PARAGRAPH_HTML_PARSER,
    "min_length": MIN_PARAGRAPH_LENGTH,
    "normalize_whitespace": NORMALIZE_WHITESPACE,
    "strip_footnote_markers": STRIP_FOOTNOTE_MARKERS,
    "decode_entities": DECODE_ENTITIES,
    "context_before": CONTEXT_BEFORE_CHARS,
    "context_after": CONTEXT_AFTER_CHARS,
    "context_window_mode": CONTEXT_WINDOW_MODE,
}
```

### Schema Validation Logic (for db/__init__.py)
```python
EXPECTED_CORE_TABLES = {
    "talk": ["ID", "Corpus", "URL", "Title", "Date", "SpeakerID"],
    "speaker": ["ID", "GivenNames", "LastNames"],
    "conference": ["ID", "Description", "Year", "Annual"],
    "conf_session": ["ID", "Description", "ConferenceID"],
    "conference_talk": ["TalkID", "SessionID", "Sequence"],
    "citation": ["ID", "TalkID", "BookID", "Chapter", "Verses"],
    "book": ["ID", "Abbr", "FullName"],
    "talk_metadata": ["talk_id", "speaker_role_id", "uri_l", "uri_gc", "kicker", "talk_preview", "data_aid"],
}

EXPECTED_CONTENT_TABLES = {
    "talkbody": ["TalkID", "Text", "TextRaw"],
}

def validate_schema(conn, expected_tables, db_name):
    """Validate that expected tables and columns exist. Raises SchemaError on mismatch."""
    for table, required_cols in expected_tables.items():
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if not cols:
            raise SchemaError(f"{db_name}: table '{table}' not found")
        missing = [c for c in required_cols if c not in cols]
        if missing:
            raise SchemaError(f"{db_name}: table '{table}' missing columns: {missing}")
```

### Recommended Integration Test Talk IDs
Based on DB research:

| talk_id | Characteristics | Why Selected |
|---------|----------------|--------------|
| 1 | 1942 earliest era, Corpus='E', URL=None | Old era + no URL edge case |
| 8827 | 2025, 78 citations, Corpus='G' | Recent era + citation-rich |
| 3679 | 1982, Welfare Session, Corpus='G' | Unusual session type |
| 258 | 1946, 72 citations, Corpus='E' | Citation-heavy early era |
| 8726 | 2024, 75 citations, Corpus='G' | Recent + high citation count, different speaker |

All 5 have confirmed HTML content in `content.52.db` (TextRaw lengths: 29K-60K bytes).

**Note on talk 1:** Corpus='E' talks have no URL (URL=NULL). They are from the Ensign magazine era (1942-1970) and have a different HTML structure than 'G' (modern web) corpus talks. This is valuable for testing era-specific fallbacks in Phase 2.

## Database Schema Inventory (for QUAL-06)

### core.52.db Tables (17 tables)
Key tables the pipeline depends on:
- `talk` (7659 rows): ID, Corpus, URL, Title, Date, SpeakerID, Kicker, AudioUrl, VideoLowUrl, VideoMedUrl, VideoHighUrl
- `speaker` (643 rows): ID, GivenNames, LastNames, Abbr, Info, NameSort
- `conference` (167 rows): ID, Description, Abbr, Year, Annual, IssueDate
- `conf_session` (1082 rows): ID, Description, Abbr, Date, Sequence, ConferenceID
- `conference_talk` (5838 rows): TalkID, SessionID, StartPageNum, EndPageNum, Sequence
- `citation` (125406 rows): ID, TalkID, BookID, Chapter, Verses, Flag, MinVerse, MaxVerse
- `book` (99 rows): ID, Abbr, CiteAbbr, FullName, NumChapters, URLPath, etc.
- `talk_metadata` (5441 rows): talk_id, speaker_role_id, uri_l, uri_gc, kicker, talk_preview, data_aid

### content.52.db Tables (3 tables)
- `talkbody` (7659 rows): TalkID, Text, TextRaw, TextSimple, TextMinimal, TextEnhanced

### Minimum Columns to Validate
Schema validation (D-08, D-09) should check tables and key columns that the Phase 1 query JOINs on. If any of these are missing, the pipeline will fail with cryptic SQL errors. The validation converts these to clear, early errors.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via Pipfile dev-packages) |
| Config file | None (default pytest discovery) |
| Quick run command | `pipenv run py -m pytest tests/test_pipeline_integration.py tests/test_phase1.py tests/test_phase5.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUAL-04 | 3-5 real talks through all phases with data contract assertions | integration | `pipenv run py -m pytest tests/test_pipeline_integration.py -x` | -- Wave 0 |
| QUAL-05 | Phase 1 edge cases: missing speaker, unusual session, no URL | unit | `pipenv run py -m pytest tests/test_phase1.py -k "edge" -x` | -- Wave 0 |
| QUAL-06 | SQLite schema validation at startup with hard fail | unit + integration | `pipenv run py -m pytest tests/test_phase1.py -k "schema_validation" -x` | -- Wave 0 |
| QUAL-10 | Phase 5 adversarial: malformed inputs, boundary conditions | unit | `pipenv run py -m pytest tests/test_phase5.py -k "adversarial" -x` | -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/ -x -q` (quick: ~5s for unit tests)
- **Per wave merge:** `pipenv run py -m pytest tests/ -q` (full suite: 269+ tests)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pipeline_integration.py` -- covers QUAL-04 (file does not exist yet)
- [ ] Schema validation function in `db/__init__.py` -- covers QUAL-06 (code does not exist yet)
- [ ] Schema validation tests in `tests/test_phase1.py` -- covers QUAL-06
- [ ] Phase 1 edge case tests in `tests/test_phase1.py` -- covers QUAL-05
- [ ] Adversarial test cases in `tests/test_phase5.py` -- covers QUAL-10

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| unittest.TestCase classes | pytest classes (no TestCase inheritance) | test_phase5.py already uses this | Phase 5 tests use plain classes; Phase 1 still uses unittest.TestCase |
| Monolithic pipeline test | `process_talk_pipeline()` orchestrator | Phase 02/03 | Single function call for full Phase 1-4 |

## Open Questions

1. **Config dict exact shape for process_talk_pipeline**
   - What we know: It takes a `config: Dict[str, Any]` parameter, uses keys like `html_parser`, `min_length`
   - What's unclear: Full set of required keys (need to trace through all phase functions)
   - Recommendation: During planning, examine `scripts/run_audit.py` for the canonical config dict shape

2. **Schema validation timing**
   - What we know: D-08 says `db/__init__.py`, D-09 says hard fail
   - What's unclear: Should validation run on `Database.__init__()`, `Database._connect()`, or via a separate `validate()` call?
   - Recommendation: Run on first `_connect()` call per Database instance (lazy, avoids import-time side effects). Cache the result so it only runs once per instance.

## Sources

### Primary (HIGH confidence)
- Direct DB schema inspection via `scripts/db_schema_extractor.py` and SQL queries
- Source code reading: `db/__init__.py`, `extractors/pipeline.py`, `extractors/phase5_validation.py`, `tests/test_phase1.py`, `tests/test_phase5.py`
- `config/pipeline_config.py` for processing constants
- `docs/PIPELINE_SPEC.md` for phase-to-phase data contracts

### Secondary (MEDIUM confidence)
- Talk ID selection based on live DB queries (row counts, citation counts, corpus types verified)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in use, no new dependencies
- Architecture: HIGH - Patterns directly observed in existing test files and pipeline code
- Pitfalls: HIGH - Based on actual codebase inspection and prior phase decisions

**Research date:** 2026-03-23
**Valid until:** 2026-04-23 (stable -- testing patterns don't change rapidly)
