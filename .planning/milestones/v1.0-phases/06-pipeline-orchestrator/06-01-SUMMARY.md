---
phase: 06-pipeline-orchestrator
plan: 01
subsystem: pipeline-orchestrator
tags: [orchestrator, pipeline, tqdm, chromadb, resume, batch]
dependency_graph:
  requires:
    - extractors/pipeline.py (process_talk_pipeline)
    - extractors/phase5_validation.py (validate_talk)
    - extractors/phase6_chromadb_loader.py (load_talk_bundles, get_chromadb_client, get_embedding_function, TalkBundle)
    - extractors/phase3_citation_extraction.py (fetch_all_books)
    - config/schemas.py (PARAGRAPH_CONFIG)
    - config/pipeline_config.py (CHROMADB_BATCH_SIZE, CHROMADB_COLLECTION_NAMES)
    - db (content_db, core_db)
  provides:
    - scripts/run_pipeline.py (full pipeline orchestrator)
    - tests/test_phase6_orchestrator.py (orchestrator unit tests)
  affects:
    - data/failed_talks.json (created at runtime when failures occur)
tech_stack:
  added: []
  patterns:
    - tqdm progress bar with tqdm.write for mid-run output
    - Buffer-and-flush batch insert (CHROMADB_BATCH_SIZE threshold)
    - Incremental JSON failure log (survives mid-run kill)
    - ChromaDB skip check for idempotent resume (no include=["ids"] param)
key_files:
  created:
    - scripts/run_pipeline.py
    - tests/test_phase6_orchestrator.py
  modified: []
decisions:
  - "INNER JOIN conference_talk for GC-only talk IDs (~5,838 vs 7,659 total)"
  - "logging.WARNING level so tqdm progress bar is uncluttered by INFO lines"
  - "talks_col.get(ids=[f'talk_{talk_id}']) without include=[] param (raises ValueError)"
  - "Validation failures logged as separate counter, not as pipeline errors"
metrics:
  duration: "6min"
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_modified: 2
---

# Phase 6 Plan 01: Pipeline Orchestrator Summary

Full pipeline orchestrator and unit test suite for running Phases 1-6 over all General Conference talks with resume, error handling, and progress tracking.

## What Was Built

**scripts/run_pipeline.py** — Production orchestrator implementing all 9 locked decisions (D-01 through D-09):

- `_get_all_gc_talk_ids()`: queries `talk INNER JOIN conference_talk` to get only GC talks (~5,838), not all 7,659 talks
- `_record_failure()`: appends to in-memory list and writes entire JSON to disk after each failure (survives kill)
- `main()`: per-talk loop with tqdm progress bar, ChromaDB skip check for resume, process_talk_pipeline (Phases 1-4), validate_talk (Phase 5), buffer-and-flush batch loading (Phase 6), final summary

**tests/test_phase6_orchestrator.py** — 7 unit tests covering all key behaviors, all mocking external dependencies.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create orchestrator script | f446eac | scripts/run_pipeline.py |
| 2 | Create unit tests (TDD) | 84e221c | tests/test_phase6_orchestrator.py |

## Verification Results

- `pipenv run py -c "import ast; ast.parse(...); print('OK')"` — syntax OK
- `pipenv run py -m pytest tests/test_phase6_orchestrator.py -x -q` — 7 passed, 1 warning
- `INNER JOIN conference_talk` present in SQL query (line 59)
- No `include=["ids"]` parameter in ChromaDB skip check (Research Pitfall 4 avoided)

## Deviations from Plan

**1. [Rule 3 - Blocking] pytest not installed in isolated worktree virtualenv**

- **Found during:** Task 2 TDD RED phase
- **Issue:** New pipenv virtualenv created for worktree had no pytest installed
- **Fix:** Ran `pipenv run py -m pip install pytest` before running tests
- **Files modified:** None (runtime environment only)
- **Commit:** N/A (no code change)

**2. [Cosmetic] INNER JOIN count is 2 not 1**

- The plan's verification check `grep -c "INNER JOIN conference_talk"` expected 1, but the docstring also contains the phrase (line 55: "Uses INNER JOIN conference_talk..."). The SQL query itself is correct. Both occurrences are intentional.

## Known Stubs

None. The orchestrator wires all real dependencies. Counters (processed, skipped, failed, validation_failed) are computed from actual loop state, not hardcoded.

## Self-Check: PASSED
