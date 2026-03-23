---
phase: quick
plan: 260323-0jy
subsystem: database
tags: [sqlite, schema-migration, sql-fix, talk-metadata]

requires:
  - phase: 01-db-enrichment
    provides: talk_metadata table with uri_l, uri_gc, data_aid, speaker_role_id columns
provides:
  - All SQL queries reference talk_metadata for URI/data_aid/speaker_role_id columns
affects: []

tech-stack:
  added: []
  patterns: [JOIN talk_metadata for column lookups, upsert_talk_metadata helper]

key-files:
  created: []
  modified:
    - extractors/phase1_talk_metadata.py
    - scripts/UPDATE.py
    - scripts/generate_uri_variants.py
    - scripts/build_database.py

decisions:
  - Removed COALESCE fallbacks entirely (talk table columns gone, no fallback needed)
  - Converted generate_uri_variants.py from raw sqlite3 to Database class for upsert compatibility
  - Kept dry_run/verbose logging branches intact in UPDATE.py

metrics:
  duration: 6min
  completed: "2026-03-23"
  tasks: 3
  files: 4
---

# Quick Task 260323-0jy: Fix sqlite3.OperationalError no such column Summary

Eliminated all SQL references to URI_L, URI_GC, data_aid, and speaker_role_id on the talk table across 4 Python files, redirecting queries to talk_metadata via JOINs and the upsert_talk_metadata helper.

## Changes Made

### Task 1: Fix phase1_talk_metadata.py COALESCE fallbacks
**Commit:** 3d90799

Replaced four COALESCE expressions that fell back to non-existent talk table columns with direct reads from talk_metadata (tm alias). The LEFT JOIN to talk_metadata already existed, so nullable results for non-GC talks are correct behavior.

**Files:** `extractors/phase1_talk_metadata.py`

### Task 2: Fix scripts/UPDATE.py SELECT and UPDATE queries
**Commit:** 9cf36e7

- URI matching query (`SELECT ID FROM talk WHERE URI_GC = ?`) replaced with JOIN to talk_metadata
- data_aid fallback query similarly updated
- `UPDATE talk SET speaker_role_id, URI_GC, URI_L, data_aid` replaced with `upsert_talk_metadata()` call
- Added import of `upsert_talk_metadata` from `create_talk_metadata_table`

**Files:** `scripts/UPDATE.py`

### Task 3: Fix scripts/generate_uri_variants.py
**Commit:** 7b863df

- Removed `ensure_columns()` function that tried to ALTER TABLE talk to add URI_L/URI_GC/URI_Success
- Replaced `UPDATE talk SET URI_L, URI_GC` with `upsert_talk_metadata()`
- Converted from raw sqlite3.connect to Database class
- Added imports for Database and upsert_talk_metadata

**Files:** `scripts/generate_uri_variants.py`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed build_database.py URI_GC lookup**
- **Found during:** Final verification grep
- **Issue:** `scripts/build_database.py` line 139 had `SELECT ID FROM talk WHERE URI_GC = ?` -- same root cause
- **Fix:** Changed to `SELECT t.ID FROM talk t JOIN talk_metadata tm ON t.ID = tm.talk_id WHERE tm.uri_gc = ?`
- **Files modified:** `scripts/build_database.py`
- **Commit:** e7d5889

## Verification Results

- Grep for `t.URI_L`, `t.URI_GC`, `talk SET.*URI_L`, `talk WHERE.*URI_GC`, `t.speaker_role_id`, `t.data_aid` in extractors/ and scripts/: **0 matches**
- Phase 1 tests (excluding pre-existing DDL failures): **39 passed, 2 skipped**
- All modified files import successfully

## Known Stubs

None.

## Pre-existing Issues (Not Fixed)

- `tests/test_phase1.py::TestTalkMetadataDDL` -- 2 test failures related to talk_metadata DDL in test fixtures (pre-existing, not caused by this change)
- `examples/pipeline_example.py` smoke test fails on missing `book` table (unrelated to URI columns)

## Self-Check: PASSED
