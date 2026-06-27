---
phase: 24-production-migration
plan: 02
subsystem: database
tags: [weaviate, pipeline, migration, vector-db, run-pipeline]
status: complete

# Dependency graph
requires:
  - phase: 24-production-migration/24-01
    provides: ProductionWeaviateLoader in extractors/phase6_weaviate_loader.py; load_talk_bundles(bundles, loader); talk_exists() on WeaviateLoader
  - phase: 24-production-migration/24-04
    provides: WEAVIATE_BATCH_SIZE in config/pipeline_config.py; chromadb_client.py deleted

provides:
  - scripts/run_pipeline.py using ProductionWeaviateLoader as context manager for full pipeline run
  - Zero ChromaDB references in run_pipeline.py
  - Weaviate skip check via loader.talk_exists() replacing ChromaDB collection.get()
  - Weaviate batch flush via load_talk_bundles(bundles, loader) replacing load_talk_bundles(bundles, client, embedding_fn)

affects: [24-05, 24-06, tests/test_phase6_orchestrator.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ProductionWeaviateLoader used as context manager wrapping entire pipeline loop (D-13)"
    - "loader.talk_exists() for O(1) skip check using generate_uuid5 + fetch_object_by_id"
    - "load_talk_bundles(bundles, loader) stateless batch loader — loader carries both client and embed_fn"

key-files:
  created: []
  modified:
    - scripts/run_pipeline.py

key-decisions:
  - "ProductionWeaviateLoader (not WeaviateLoader directly) used as context manager — ensures production PascalCase collection names for schema init and all writes (D-13)"
  - "os.environ.get() used directly for WEAVIATE_HOST/PORT/GRPC_PORT — not via config factory — because WeaviateLoader bundles its own connection lifecycle (D-13 rationale)"
  - "WEAVIATE_COLLECTION_NAMES not imported in run_pipeline.py — collection names are encapsulated inside ProductionWeaviateLoader (D-15)"

patterns-established:
  - "Pattern: Pipeline loop wrapped in 'with ProductionWeaviateLoader(...) as loader:' so close() is guaranteed on exit/exception"
  - "Pattern: resolve_ollama_url() called explicitly and passed to get_embedding_function(url=...) instead of using default"

requirements-completed:
  - MIGR-01

# Metrics
duration: 8min
completed: 2026-06-27
---

# Phase 24 Plan 02: run_pipeline.py Weaviate Migration Summary

**scripts/run_pipeline.py fully migrated to Weaviate — zero ChromaDB references, ProductionWeaviateLoader context manager, loader.talk_exists() skip check, WEAVIATE_BATCH_SIZE batch flush**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-27T21:20:00Z
- **Completed:** 2026-06-27T21:28:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Replaced ChromaDB import block (get_chromadb_client, CHROMADB_BATCH_SIZE, CHROMADB_COLLECTION_NAMES, phase6_chromadb_loader) with Weaviate equivalents (ProductionWeaviateLoader, WEAVIATE_BATCH_SIZE, phase6_weaviate_loader)
- Replaced ChromaDB client init + talks_col setup with ProductionWeaviateLoader as context manager wrapping entire pipeline loop
- Replaced `talks_col.get(ids=[f"talk_{talk_id}"])` skip check with `loader.talk_exists(talk_id)` O(1) UUID lookup
- Replaced `load_talk_bundles(bundles, chroma_client, embedding_fn)` with `load_talk_bundles(bundles, loader)` at both flush points (loop flush + final flush)
- Updated --force help text from "ChromaDB existence check" to "Weaviate existence check"
- Updated module docstring from "skip-if-processed via ChromaDB" to "skip-if-processed via Weaviate"
- `pipenv run py scripts/run_pipeline.py --help` exits 0

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite scripts/run_pipeline.py imports and main() for Weaviate** - `6466e93` (feat)

## Files Created/Modified

- `scripts/run_pipeline.py` — Full ChromaDB-to-Weaviate migration; ProductionWeaviateLoader context manager wraps pipeline loop; loader.talk_exists() skip check; WEAVIATE_BATCH_SIZE batch flush; zero chromadb references

## Decisions Made

- Used `ProductionWeaviateLoader` (not `WeaviateLoader`) as the context manager so that `_ensure_schema()` initializes production PascalCase collection names on startup — consistent with D-13 intent
- `resolve_ollama_url()` called explicitly and passed to `get_embedding_function(url=...)` so the URL override is honored at pipeline time (matches server.py pattern)
- `WEAVIATE_COLLECTION_NAMES` not imported — collection names are encapsulated inside `ProductionWeaviateLoader._ensure_schema()` and `load()`, so the pipeline loop never needs to reference them directly

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `scripts/run_pipeline.py` is fully Weaviate-ready; operators can run `pipenv run py scripts/run_pipeline.py` against a live Weaviate instance
- MIGR-01 requirement complete: pipeline runs against Weaviate, all ChromaDB references removed
- Plans 24-05 (server.py) and 24-06 (tests) can proceed independently

## Threat Surface Scan

No new security surface introduced. All data flows through existing trusted path: SQLite (read-only) → extraction phases → WeaviateLoader context manager. Env var reads (WEAVIATE_HOST/PORT/GRPC_PORT) are operator-controlled, matching pattern established in existing server.py and Plan 01.

## Self-Check: PASSED

- `scripts/run_pipeline.py` — FOUND
- Commit `6466e93` — FOUND
- `grep -i chromadb scripts/run_pipeline.py` — 0 matches
- `grep "ProductionWeaviateLoader" scripts/run_pipeline.py` — 2 matches
- `grep "loader.talk_exists" scripts/run_pipeline.py` — 1 match
- `grep "load_talk_bundles(pending_bundles, loader)" scripts/run_pipeline.py` — 2 matches
- `pipenv run py scripts/run_pipeline.py --help` — exits 0

---
*Phase: 24-production-migration*
*Completed: 2026-06-27*
