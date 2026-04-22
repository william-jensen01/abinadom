---
phase: 21-db-loaders
plan: "01"
subsystem: test-infrastructure
tags: [dependencies, test-fixtures, tuple-compat, vector-db]
dependency_graph:
  requires: []
  provides:
    - weaviate-client==4.20.5 installed in virtualenv
    - qdrant-client==1.17.1 installed in virtualenv
    - tests/conftest.py with 5 session-scoped fixtures
    - tests/test_loaders_chromadb.py stub
    - tests/test_loaders_weaviate.py stub
    - tests/test_loaders_qdrant.py stub
    - tests/test_embeddings.py with 2 passing mock tests
    - tests/test_phase6.py pre-updated for Wave 1 4-element tuples
  affects:
    - Wave 1 (tuple extension in shared_transforms.py will not break tests)
    - Wave 2 (loader test stubs will turn GREEN when loaders are implemented)
tech_stack:
  added:
    - weaviate-client==4.20.5
    - qdrant-client==1.17.1
  patterns:
    - Port-check session fixtures via socket.create_connection (D-08)
    - Shared TalkBundle fixture with talk_id=9999 for all loader tests (D-09)
    - 4-element tuple unpack form (doc, meta, doc_id, _) for Wave 1 compatibility
key_files:
  created:
    - tests/conftest.py
    - tests/test_loaders_chromadb.py
    - tests/test_loaders_weaviate.py
    - tests/test_loaders_qdrant.py
    - tests/test_embeddings.py
  modified:
    - Pipfile
    - Pipfile.lock
    - tests/test_phase6.py
decisions:
  - "Accepted that test_phase6.py will have failing tests during Wave 0: the 4-element unpack form is pre-applied so Wave 1's tuple extension does not break the test suite"
  - "test_embed_live ImportError is explicitly acceptable per plan: Ollama is running but loaders/embeddings.py does not exist until Wave 2"
  - "Found 27 unpack sites (plan stated 26); updated all 27 — one extra in TestPrepareParagraphRecords (test_annotation_exclusion line 313)"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-22"
  tasks_completed: 3
  files_created: 5
  files_modified: 3
requirements:
  - BENCH-02
  - BENCH-03
  - BENCH-04
---

# Phase 21 Plan 01: Wave 0 Foundation (deps + test infra) Summary

**One-liner:** Pinned weaviate-client==4.20.5 and qdrant-client==1.17.1, pre-updated 27 tuple unpack sites in test_phase6.py for Wave 1 4-element tuples, and created port-check + TalkBundle fixtures with four loader test stubs.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Pin client deps in Pipfile and run pipenv install | 0ccfe98 | Pipfile, Pipfile.lock |
| 2 | Fix all 26+ three-element unpack sites in tests/test_phase6.py | 251e3f7 | tests/test_phase6.py |
| 3 | Create test infrastructure — conftest.py and four test stub files | 982ea29 | tests/conftest.py, tests/test_loaders_*.py, tests/test_embeddings.py |

## Verification Results

| Check | Result |
|-------|--------|
| `import weaviate; import qdrant_client` | PASS |
| `pytest tests/test_shared_transforms.py -x -q` | PASS — 14 passed |
| `pytest tests/test_embeddings.py` | 2 passed, 1 failed (expected — `loaders/embeddings.py` not yet created) |
| `pytest tests/test_phase6.py` | FAIL (expected — Wave 1 has not yet extended shared_transforms.py to 4-tuples) |
| No 3-element unpack sites in test_phase6.py | PASS — `grep` returns 0 matches |
| conftest.py has 5 session-scoped fixtures | PASS |

## Deviations from Plan

### Plan Discrepancy: 27 Unpack Sites (Plan Stated 26)

**Found during:** Task 2
**Issue:** The plan listed 26 three-element unpack sites. Actual count was 27: the plan listed `test_annotation_exclusion` (line ~313) as having one `doc, meta, doc_id = records[0]` site, but this was correctly identified via grep and fixed. All 27 sites updated.
**Fix:** Updated all 27 sites to 4-element form.
**Impact:** None — only improves correctness.

### Plan Acceptance Criteria vs Reality: test_phase6.py Fails During Wave 0

**Found during:** Task 2 verification
**Issue:** The plan's acceptance criteria states "passes with zero failures" and the Wave 0 verification list says `pytest tests/test_phase6.py -x -q` exits 0. However, this cannot be true during Wave 0 because `shared_transforms.py` still returns 3-element tuples, and test_phase6.py now expects 4-element tuples. The plan's objective text correctly states: "Fixing them now (before the source changes) means Wave 1 can run safely" — confirming this is a pre-emptive fix.
**Resolution:** The acceptance criteria refers to the post-Wave-1 state. During Wave 0, test_phase6.py failures are expected and acceptable. This is documented here and the implementation is correct per the plan's intent.
**Impact:** Wave 1 will resolve this when it extends shared_transforms.py prepare_* functions to return 4-element tuples.

### test_embed_live ImportError: loaders/embeddings.py Missing

**Found during:** Task 3 verification
**Issue:** `test_embed_live` fails with ModuleNotFoundError because `loaders/embeddings.py` does not exist (Wave 2 deliverable). Ollama IS running locally (port 11434 open), so the `ollama_available` fixture does not skip the test.
**Resolution:** Per plan: "fail with ImportError (loaders not implemented yet) — both outcomes are acceptable at Wave 0." No action taken.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `TestChromaDBLoader.test_round_trip_paragraph` | tests/test_loaders_chromadb.py | Loader not implemented; will pass when Wave 2 creates `loaders/chromadb_loader.py` |
| `TestWeaviateLoader.test_round_trip_paragraph` | tests/test_loaders_weaviate.py | Loader not implemented; will pass when Wave 2 creates `loaders/weaviate_loader.py` |
| `TestQdrantLoader.test_round_trip_paragraph` | tests/test_loaders_qdrant.py | Loader not implemented; will pass when Wave 2 creates `loaders/qdrant_loader.py` |
| `test_embed_live` | tests/test_embeddings.py | `loaders/embeddings.py` not yet created; will pass when Wave 2 creates it |

These stubs are intentional — the plan calls them out as Wave 0 contracts that turn GREEN in Wave 2.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. All new files are test fixtures and stubs. The Pipfile additions pin exact versions per T-21-01-01 threat mitigation (SSL verification already enabled in `[[source]]` stanza).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| tests/conftest.py exists | FOUND |
| tests/test_embeddings.py exists | FOUND |
| tests/test_loaders_chromadb.py exists | FOUND |
| tests/test_loaders_weaviate.py exists | FOUND |
| tests/test_loaders_qdrant.py exists | FOUND |
| Commit 0ccfe98 (Pipfile) | FOUND |
| Commit 251e3f7 (test_phase6.py) | FOUND |
| Commit 982ea29 (test infra) | FOUND |
