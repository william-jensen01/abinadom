---
phase: 04-test-coverage
plan: 02
subsystem: testing
tags: [sqlite, schema-validation, edge-cases, in-memory, pytest]

requires:
  - phase: 03-bug-audit-fixes
    provides: Working pipeline extractors and db module for validation layer

provides:
  - SchemaError exception and validate_schema() function in db/__init__.py
  - EXPECTED_CORE_TABLES and EXPECTED_CONTENT_TABLES schema constants
  - Lazy schema validation on first DB connection per Database instance
  - TestSchemaValidation: 4 tests for SQLite schema gate (QUAL-06)
  - TestPhase1EdgeCases: 3 in-memory fixture tests for Phase 1 edge cases (QUAL-05)

affects: [04-test-coverage, phase-6-chromadb]

tech-stack:
  added: []
  patterns:
    - "Lazy schema validation: set_expected_schema() + _schema_validated flag; validation fires on first _connect() not import"
    - "In-memory SQLite fixture pattern: _build_in_memory_db() helper + InMemoryDatabase wrapper replaces real DB dependency in edge-case tests"

key-files:
  created: []
  modified:
    - db/__init__.py
    - tests/test_phase1.py

key-decisions:
  - "Schema validation is lazy (runs on first _connect per instance) to avoid breaking tests that use in-memory or mock DBs"
  - "SchemaError is a hard fail (exception raised) per D-09 — pipeline halts with a clear message on schema mismatch"
  - "Missing speaker test documents INNER JOIN behavior: fetch_talk_by_id returns None when speaker row is absent — no crash"

patterns-established:
  - "validate_schema(conn, expected_tables, db_name): PRAGMA table_info check; raises SchemaError on missing table or column"
  - "InMemoryDatabase wrapper: minimal Database-like class that holds a sqlite3.Connection for fixture-based tests"

requirements-completed: [QUAL-05, QUAL-06]

duration: 5min
completed: 2026-03-24
---

# Phase 04 Plan 02: Schema Validation and Phase 1 Edge Case Tests Summary

**SQLite schema gate added to db/__init__.py with hard-fail SchemaError, plus 7 in-memory fixture tests covering schema mismatches and Phase 1 real-world edge cases (missing speaker, welfare session, no-URL talk).**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-24T08:29:10Z
- **Completed:** 2026-03-24T08:34:00Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments

### Task 1: Schema validation in db/__init__.py

- Added `SchemaError(Exception)` class for clear hard-fail messages on schema mismatch
- Added `EXPECTED_CORE_TABLES` (8 tables, key columns each) and `EXPECTED_CONTENT_TABLES` (talkbody) constants
- Added `validate_schema(conn, expected_tables, db_name)` using `PRAGMA table_info` — raises SchemaError on missing table or column
- Added `set_expected_schema()` method and `_schema_validated` flag to `Database` — validation fires lazily on first `_connect()` per instance
- Applied schema expectations to global `core_db` and `content_db` instances
- Removed debug `print(f"CURRENT_DIR: ...")` statement that was polluting test output

### Task 2: Phase 1 edge case tests and schema validation tests

- Added `_build_in_memory_db()` helper: creates an in-memory SQLite with all 6 tables Phase 1 queries (talk, speaker, conference, conf_session, conference_talk, talk_metadata) with matching column sets
- Added `InMemoryDatabase` wrapper: minimal `select()`/`select_one()` adapter over a sqlite3 connection
- Added `TestSchemaValidation` (4 tests): correct schema accepted, missing table raises SchemaError, missing column raises SchemaError, content DB validated
- Added `TestPhase1EdgeCases` (3 tests): missing speaker (INNER JOIN returns None — no crash), welfare session type, NULL URL talk
- No regressions: 264 pass, 3 pre-existing TestTalkMetadataDDL failures unchanged (require real DB with talk_metadata table)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all test data is fully wired to in-memory fixtures; no placeholder values used in assertions.

## Self-Check: PASSED

- `db/__init__.py` contains `class SchemaError`, `validate_schema`, `EXPECTED_CORE_TABLES`, `EXPECTED_CONTENT_TABLES`, `_schema_validated`, `set_expected_schema`
- `db/__init__.py` does NOT contain `print(f"CURRENT_DIR`
- `tests/test_phase1.py` contains `class TestSchemaValidation`, `class TestPhase1EdgeCases`, all 7 required test methods
- Commit a57abd3: feat(04-02): add schema validation to db/__init__.py
- Commit 85a07b4: feat(04-02): add schema validation tests and Phase 1 edge case tests
- Full suite: 264 passed, 3 pre-existing failures (unrelated to this plan), 9 skipped
