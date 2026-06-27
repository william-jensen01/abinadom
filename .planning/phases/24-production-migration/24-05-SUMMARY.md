---
phase: 24-production-migration
plan: "05"
subsystem: tests
tags: [weaviate, testing, migration, phase6]
status: complete

dependency_graph:
  requires:
    - 24-01  # WeaviateLoader / ProductionWeaviateLoader defined
    - 24-02  # run_pipeline.py migrated to Weaviate
  provides:
    - clean-test-suite-for-phase6
    - weaviate-loader-test-coverage
  affects:
    - tests/test_phase6.py
    - tests/test_phase6_orchestrator.py
    - tests/test_shared_transforms.py

tech_stack:
  added: []
  patterns:
    - "Platform-conditional fixture (EMBEDDED_AVAILABLE flag for Windows vs Linux CI)"
    - "MagicMock fallback for weaviate-embedded on Windows"
    - "Session-scoped fixtures with autouse reset for test isolation"

key_files:
  created: []
  modified:
    - tests/test_phase6.py
    - tests/test_phase6_orchestrator.py
    - tests/test_shared_transforms.py
    - loaders/weaviate_loader.py
    - loaders/chromadb_loader.py

decisions:
  - "Windows-conditional fixture: connect_to_embedded() not supported on Windows (gh#3315) — MagicMock fallback used so suite passes on all platforms"
  - "WeaviateLoader.load() collection_map changed from hardcoded strings to self.COLLECTIONS[i] — fixes ProductionWeaviateLoader routing without re-implementing load()"
  - "test_ensure_schema_creates_pascal_case_collections marked skipif on Windows — requires live embedded Weaviate"

metrics:
  duration: "~25 minutes"
  completed: "2026-06-27T22:28:40Z"
  tasks: 3
  files_changed: 5
---

# Phase 24 Plan 05: Fix Test Suite Imports (Weaviate) Summary

**One-liner:** Rewrote test_phase6.py for Weaviate with platform-conditional embedded fixture; patched test_phase6_orchestrator.py from ChromaDB to ProductionWeaviateLoader mocks; fixed two blocking import regressions.

## Tasks Completed

| # | Task | Status | Commit |
|---|------|--------|--------|
| 0 | Verify test_shared_transforms.py transformation coverage | Done | 04274da |
| 1 | Rewrite tests/test_phase6.py for Weaviate | Done | 2f7cab4 |
| 2 | Minimal patch test_phase6_orchestrator.py + verify full suite | Done | 39209c0 |

## Results

### test_phase6.py
- **Before:** `ModuleNotFoundError: No module named 'config.chromadb_client'` (blocked all test collection)
- **After:** 8 passed, 1 skipped (schema creation test skipped on Windows — embedded Weaviate requires Linux/macOS)
- No chromadb imports. Uses `weaviate.connect_to_embedded()` on Linux/macOS CI; MagicMock fallback on Windows.
- Tests: `TestLoadTalkBundles` (4), `TestTalkExists` (2), `TestCollectionNames` (3)

### test_phase6_orchestrator.py
- **Before:** 11 tests passing (chromadb patches against old run_pipeline)
- **After:** 11 tests passing with ProductionWeaviateLoader mocks
- Replaced 9 `get_chromadb_client` patches with `ProductionWeaviateLoader` context manager mocks
- Replaced `CHROMADB_BATCH_SIZE` patches with `WEAVIATE_BATCH_SIZE`
- Added `talk_exists.side_effect` for resume/skip tests

### test_shared_transforms.py
- **Before:** 14 tests (flatten_metadata, rich_metadata, prepare_talk_bundle)
- **After:** 38 tests — added `TestPrepareTalkRecord` (8), `TestPrepareParagraphRecords` (7), `TestPrepareCitationRecords` (5), `TestPrepareFootnoteRecords` (4)
- Added `make_citation` and `make_footnote` factory helpers
- Coverage verified before rewriting test_phase6.py (plan pre-rewrite requirement)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] WeaviateLoader.load() used hardcoded collection names**
- **Found during:** Task 1 test execution
- **Issue:** `WeaviateLoader.load()` hardcoded `collection_map = {"talks": "Talk", ...}` — `ProductionWeaviateLoader` subclass overrides `COLLECTIONS` but inherits `load()`, so inserts went to benchmark collection names (`Talk`) instead of production names (`ConferenceTalks`)
- **Fix:** Changed `collection_map` to use `self.COLLECTIONS[i]` — both base class and subclass now route correctly
- **Files modified:** `loaders/weaviate_loader.py`
- **Commit:** 2f7cab4

**2. [Rule 3 - Blocking] weaviate.connect_to_embedded() not supported on Windows**
- **Found during:** Task 1 test execution
- **Issue:** `WeaviateStartUpError: Windows is not supported with EmbeddedDB` — plan's fixture design requires Linux/macOS
- **Fix:** Added `EMBEDDED_AVAILABLE = platform.system() != "Windows"` flag; fixtures use `connect_to_embedded()` on Linux/macOS and MagicMock fallback on Windows. Test `test_ensure_schema_creates_pascal_case_collections` marked `skipif(not EMBEDDED_AVAILABLE)`.
- **Files modified:** `tests/test_phase6.py`
- **Commit:** 2f7cab4

**3. [Rule 3 - Blocking] loaders/chromadb_loader.py imported removed constant**
- **Found during:** Task 2 full-suite run
- **Issue:** `loaders/chromadb_loader.py` imported `CHROMADB_COLLECTION_NAMES` from `config.pipeline_config`, which was removed in Plan 24-04 (renamed to `WEAVIATE_COLLECTION_NAMES`). Caused `test_loaders_chromadb.py` to fail with `ImportError` when the benchmark ChromaDB port was reachable.
- **Fix:** Defined `CHROMADB_COLLECTION_NAMES` locally in `loaders/chromadb_loader.py` with the original values
- **Files modified:** `loaders/chromadb_loader.py`
- **Commit:** 39209c0

### Plan Annotation Corrections

**Citation count in test_load_multiple_talks_returns_correct_counts:**
The plan template said `citations_inserted == 3  # 1 + 2` but `_make_full_bundle` adds 1 annotation-paragraph citation per bundle (so b1=2, b2=3, total=5). Used correct value 5 in test.

## Full Suite Status

Pre-existing failures (NOT introduced by this plan):
- `test_loaders_chromadb.py::TestChromaDBLoader::test_round_trip_paragraph` — benchmark integration test; passes import after Rule 3 fix but assertion fails because remote ChromaDB instance at 10.0.0.231:8763 has no data (benchmark stack down)
- `test_server.py` (32 tests) — pre-existing failures from prior phases (likely server.py Weaviate migration breaking server mock tests)

Suite delta: 415 passing before Plan 24-05 → 426 passing after.

## Self-Check

- [x] `tests/test_phase6.py` exists and passes (8 passed, 1 skipped)
- [x] `tests/test_phase6_orchestrator.py` exists and passes (11 passed)
- [x] `tests/test_shared_transforms.py` passes (38 passed)
- [x] `grep "chromadb" tests/test_phase6.py` → 0 matches
- [x] `grep "get_chromadb_client" tests/test_phase6_orchestrator.py` → 0 matches
- [x] All 3 task commits exist (04274da, 2f7cab4, 39209c0)
