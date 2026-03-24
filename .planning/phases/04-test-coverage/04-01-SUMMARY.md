---
phase: 04-test-coverage
plan: "01"
subsystem: tests
tags: [integration-tests, pipeline, end-to-end, phase-boundaries]
dependency_graph:
  requires: [extractors/pipeline.py, extractors/phase5_validation.py, extractors/phase3_citation_extraction.py, config/schemas.py, db/__init__.py]
  provides: [tests/test_pipeline_integration.py]
  affects: []
tech_stack:
  added: []
  patterns: [module-scoped-pytest-fixtures, parametrized-tests, skip-if-guard]
key_files:
  created: [tests/test_pipeline_integration.py]
  modified: []
decisions:
  - "Used c.book (CitationData.book field) not c.book_name — plan had incorrect field name; fixed per actual model"
  - "35 test cases: 5 talk IDs x 7 test functions — matches D-02 requirement"
  - "DB skip guard at module level via pytestmark ensures clean skip output when DBs absent"
metrics:
  duration: "4min"
  completed_date: "2026-03-24"
  tasks_completed: 2
  files_created: 1
---

# Phase 04 Plan 01: Integration Tests Summary

End-to-end integration tests for the full Phase 1-5 pipeline over 5 real talks, validating phase boundary data contracts and cross-phase foreign key integrity.

## What Was Built

`tests/test_pipeline_integration.py` — 7 parametrized test functions over 5 hardcoded talk IDs producing 35 test cases:

1. `test_pipeline_end_to_end` — full pipeline `result.success` for each talk
2. `test_phase1_boundary` — metadata: talk_id, speaker_name, conference_year, title
3. `test_phase2_boundary` — paragraphs: non-empty, correct types, talk_id linkage
4. `test_phase3_boundary` — citations: extraction_success, required fields when present
5. `test_phase4_boundary` — footnotes: extraction_success, required fields when present
6. `test_phase5_validation` — ValidationReport.is_valid passes for all talks
7. `test_cross_phase_paragraph_ids` — every citation/footnote paragraph_id resolves to an existing paragraph

Module-level `pytestmark = pytest.mark.skipif(not DB_AVAILABLE, ...)` skips all 35 tests cleanly when DB files are absent.

## Talk IDs Selected (D-02)

| talk_id | Era  | Notes                                     |
|---------|------|-------------------------------------------|
| 1       | 1942 | Earliest era, Corpus='E', URL=None        |
| 8827    | 2025 | 78 citations, Corpus='G'                  |
| 3679    | 1982 | Welfare Session, unusual session type     |
| 258     | 1946 | 72 citations, Corpus='E'                  |
| 8726    | 2024 | 75 citations, Corpus='G'                  |

## Verification Results

- `pipenv run py -m pytest tests/test_pipeline_integration.py -x -q` → 35 skipped (DB not in worktree, correct behavior)
- `pipenv run py -m pytest tests/ -q` → 257 passed, 40 skipped, 7 failed
  - 7 failures are **pre-existing** — they exist in test_phase1.py and test_phase3.py and fail because the worktree DB path contains an empty `db/` directory (no real DB files). Confirmed by running before my changes.
  - 0 regressions introduced by this plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed incorrect field name in phase3 boundary test**
- **Found during:** Task 1 implementation
- **Issue:** Plan template used `c.book_name` but `CitationData` model has `c.book` (FullName field)
- **Fix:** Used `c.book` in `test_phase3_boundary` assertion
- **Files modified:** tests/test_pipeline_integration.py
- **Commit:** 976f237

## Known Stubs

None — all test assertions are wired to real pipeline output. No hardcoded/placeholder values in test logic.

## Self-Check: PASSED
