---
phase: 24-production-migration
plan: "08"
subsystem: testing
tags: [weaviate, pytest, mocking, server, mcp]

# Dependency graph
requires:
  - phase: 24-production-migration
    provides: "Weaviate-migrated server.py (Plan 24-03), _validate_collections extraction (Plan 24-07), config/weaviate_client.py (Plan 24-01)"
provides:
  - "Full Weaviate-based test suite for server.py — 44 tests all passing"
  - "TestValidateCollections: 4 tests for _validate_collections startup guard"
  - "TestBuildWeaviateFilters: 5 tests for native Weaviate filter builder"
  - "Health endpoint tests asserting data['weaviate'] key"
  - "Search/get_talk tool tests using collections.use() mock interface"
affects: [24-production-migration, UAT-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_make_mock_ctx() uses AppContext(client=MagicMock()) — no collections dict; matches D-02"
    - "Search test mocks use mock_col.query.near_vector.return_value.objects pattern"
    - "get_talk test mocks use fetch_object_by_id / fetch_objects interface"
    - "collections.use() side_effect dispatches by collection name in TestGetTalkTool"

key-files:
  created: []
  modified:
    - "tests/test_server.py — full rewrite: 341 lines removed, 288 lines added; 44 tests pass"

key-decisions:
  - "Removed test_search_speaker_post_filter (ChromaDB post-filter) — replaced with test_search_speaker_filter_not_none (native Weaviate filter)"
  - "Removed 3 OllamaEmbeddingFunction tests (config.ollama.OllamaEmbeddingFunction class no longer exists after Plan 24-07 rewrite)"
  - "_mock_startup() uses AppContext(client=MagicMock()) — no collections parameter per D-02"
  - "Health tests patch server.http_requests.get to mock Weaviate /v1/.well-known/ready endpoint (D-19 pattern)"

patterns-established:
  - "Weaviate collection mock: mock_col.query.near_vector.return_value.objects = [obj_with_properties]"
  - "Talk collection mock: fetch_object_by_id returns MagicMock with .properties dict or None for not-found"
  - "Multi-collection routing: mock_client.collections.use.side_effect dispatches by name string"

requirements-completed:
  - MIGR-03

# Metrics
duration: 15min
completed: 2026-06-27
status: complete
---

# Phase 24 Plan 08: Test Suite Migration Summary

**Rewrote tests/test_server.py from 34-failing ChromaDB tests to 44 all-passing Weaviate tests, covering _validate_collections, _build_weaviate_filters, search/get_talk Weaviate interfaces, and health endpoint with data["weaviate"] key**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-27T00:00:00Z
- **Completed:** 2026-06-27T00:15:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Eliminated all 34 failing tests caused by ChromaDB interface assumptions
- Added TestValidateCollections (4 tests) and TestBuildWeaviateFilters (5 tests) as new test classes
- Updated _make_mock_ctx() to use AppContext(client=MagicMock()) with no collections dict (D-02)
- Updated TestSearchTool to mock near_vector interface instead of col.query ChromaDB interface
- Updated TestGetTalkTool to mock fetch_object_by_id and fetch_objects instead of col.get ChromaDB interface
- Updated health tests to assert data["weaviate"] instead of data["chromadb"]
- Replaced test_search_speaker_post_filter with test_search_speaker_filter_not_none (native filter)
- Removed 3 OllamaEmbeddingFunction tests obsoleted by Plan 24-07 ollama.py rewrite
- Net result: 44 passing tests (up from 16) with zero chromadb references

## Task Commits

1. **Task 1: Rewrite tests/test_server.py for Weaviate** - `377a9ac` (feat)

## Files Created/Modified

- `tests/test_server.py` — Full rewrite: replaced all ChromaDB-specific test groups with Weaviate equivalents; 44 tests now pass

## Decisions Made

- Removed test_chromadb_client_default_host and test_chromadb_client_env_override; replaced with test_weaviate_client_default_host and test_weaviate_client_env_override patching weaviate.connect_to_local
- Removed TestBuildWhereFilter and TestMatchesSpeaker (functions deleted from server.py); replaced with TestBuildWeaviateFilters
- Removed test_chromadb_missing_collection_exits and test_all_collections_warmed; replaced with TestValidateCollections (4 tests)
- Removed test_health_chromadb_down (no chromadb key in health response); two remaining health tests assert data["weaviate"]
- _make_mock_ctx() now returns (ctx, mock_client) tuple for flexibility in search/talk tests
- Kept all OAuth/auth tests unchanged (they use _mock_startup() which now uses no-collections AppContext)

## Deviations from Plan

None — plan executed exactly as written. All required test groups added, all removed groups removed, all preserved tests kept.

## Issues Encountered

None — the mock interface for Weaviate (near_vector, fetch_object_by_id, fetch_objects, aggregate.over_all) was straightforward to implement with MagicMock.

## Known Stubs

None — test_server.py is a test file with no UI or data stubs.

## Threat Flags

None — no new network endpoints, auth paths, or security-relevant surface introduced. Tests use MagicMock for all clients; no real credentials needed. monkeypatch resets env after each test.

## Self-Check

- [x] tests/test_server.py exists with 44 passing tests
- [x] Commit 377a9ac exists (feat(24-08): rewrite test_server.py for Weaviate-migrated server)
- [x] chromadb refs: 0
- [x] Old function refs (_load_collections, _build_where_filter, _matches_speaker): 0
- [x] TestValidateCollections and TestBuildWeaviateFilters present
- [x] data["weaviate"] in health tests
- [x] AppContext(client= in _make_mock_ctx

## Next Phase Readiness

- test_server.py is green — REQ10 in UAT pre-flight gate (Plan 24-06 Task 1) unblocked
- All 44 tests pass against the Weaviate server implementation from Plans 24-03 and 24-07
- Full test suite regressions: only 2 pre-existing failures in test_loaders_chromadb.py and test_metrics.py (unrelated to this plan)

---
*Phase: 24-production-migration*
*Completed: 2026-06-27*
