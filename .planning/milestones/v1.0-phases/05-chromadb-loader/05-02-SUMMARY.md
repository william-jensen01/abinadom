---
phase: 05-chromadb-loader
plan: 02
subsystem: database
tags: [chromadb, batch-insert, upsert, ollama, nomic-embed-text]

# Dependency graph
requires:
  - phase: 05-chromadb-loader-01
    provides: "Transformation functions (prepare_talk_record, prepare_paragraph_records, prepare_citation_records, prepare_footnote_records, prepare_talk_bundle)"
provides:
  - "insert_collection() with create_batches chunking and per-batch progress logging"
  - "load_talk_bundles() orchestrator with dependency-ordered insertion"
  - "get_chromadb_client() and get_embedding_function() helpers"
  - "TalkBundle type alias"
affects: [05-chromadb-loader-03]

# Tech tracking
tech-stack:
  added: [ollama (python package, required by OllamaEmbeddingFunction)]
  patterns: [batch-insertion-with-create_batches, upsert-for-idempotency, dependency-ordered-insertion, ephemeral-client-singleton-cleanup-fixture]

key-files:
  created: []
  modified:
    - extractors/phase6_chromadb_loader.py
    - tests/test_phase6.py
    - Pipfile
    - Pipfile.lock

key-decisions:
  - "EphemeralClient is a singleton in chromadb -- added fresh_client fixture that deletes collections between tests"
  - "Installed ollama python package as runtime dependency (required by OllamaEmbeddingFunction at instantiation time)"

patterns-established:
  - "fresh_client fixture: delete all 4 named collections before each integration test to handle EphemeralClient singleton"
  - "insert_collection uses create_batches(api=client, ...) for automatic batch sizing respecting SQLite limits"
  - "load_talk_bundles accumulates all records then inserts in dependency order (talks -> paragraphs -> citations -> footnotes)"

requirements-completed: [LOAD-04, LOAD-05]

# Metrics
duration: 11min
completed: 2026-03-25
---

# Phase 05 Plan 02: ChromaDB Insertion Layer Summary

**Batch insertion with create_batches chunking, upsert idempotency, dependency-ordered load_talk_bundles orchestrator, and per-batch progress logging**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-25T17:49:28Z
- **Completed:** 2026-03-25T18:00:59Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Built insert_collection() using create_batches for automatic batch sizing and upsert for idempotent writes
- Built load_talk_bundles() orchestrating dependency-ordered insertion (talks -> paragraphs -> citations -> footnotes) with invalid talk skipping
- Added get_chromadb_client() and get_embedding_function() helpers for production and test use
- 8 new tests (4 insertion tests + 4 orchestration tests) all passing with EphemeralClient

## Task Commits

Each task was committed atomically:

1. **Task 1: Build ChromaDB client helpers and batch insertion function** - `04b375e` (feat)
2. **Task 2: Build load_talk_bundles orchestrator with dependency-ordered insertion** - `3ac1be1` (feat)

_Both tasks used TDD flow (RED -> GREEN)_

## Files Created/Modified
- `extractors/phase6_chromadb_loader.py` - Added get_embedding_function(), get_chromadb_client(), insert_collection(), TalkBundle type alias, load_talk_bundles()
- `tests/test_phase6.py` - Added 8 integration tests for insertion and orchestration layer
- `Pipfile` / `Pipfile.lock` - Added ollama dependency

## Decisions Made
- EphemeralClient is a singleton in chromadb (all instances share state). Added a fresh_client pytest fixture that deletes all 4 named collections before each test to ensure isolation.
- Installed ollama Python package as a runtime dependency because OllamaEmbeddingFunction imports it at instantiation time, even when not connecting to the Ollama server.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing ollama Python package**
- **Found during:** Task 1 (test_get_embedding_function)
- **Issue:** OllamaEmbeddingFunction requires the `ollama` Python package at instantiation time, even just to create the object
- **Fix:** `pipenv install ollama`
- **Files modified:** Pipfile, Pipfile.lock
- **Verification:** test_get_embedding_function passes
- **Committed in:** 04b375e (Task 1 commit)

**2. [Rule 1 - Bug] Fixed EphemeralClient singleton shared state between tests**
- **Found during:** Task 2 (test_load_bundles_skips_invalid failing with count=1 from prior test)
- **Issue:** chromadb.EphemeralClient() returns a singleton; collections persist across tests in the same process
- **Fix:** Added fresh_client pytest fixture that deletes all 4 collection names before each test
- **Files modified:** tests/test_phase6.py
- **Verification:** All 48 tests pass, including test_load_bundles_skips_invalid showing count=0
- **Committed in:** 3ac1be1 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered
- Worktree had no virtualenv; required `pipenv install --dev` before tests could run (environment setup, not a code issue)
- Pre-existing DB-dependent test failures in test_phase1.py (7 tests) are environment-only, documented in STATE.md

## Known Stubs

None -- all functions are fully wired with real chromadb calls.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Insertion layer complete; ready for Plan 03 (post-insertion verification report)
- All 48 phase6 tests pass
- Production use requires: `ollama serve` running + `ollama pull nomic-embed-text`

---
*Phase: 05-chromadb-loader*
*Completed: 2026-03-25*
