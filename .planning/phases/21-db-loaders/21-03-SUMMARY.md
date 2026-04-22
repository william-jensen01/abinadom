---
phase: 21-db-loaders
plan: "03"
subsystem: database
tags: [vector-db, chromadb, embeddings, benchmark, loaders]

# Dependency graph
requires:
  - phase: 21-02
    provides: "BaseLoader ABC in loaders/__init__.py, prepare_talk_bundle_rich() in loaders/shared_transforms.py, CHROMADB_COLLECTION_NAMES in config/pipeline_config.py"
provides:
  - "loaders/chromadb_loader.py: ChromaDBLoader(BaseLoader) — benchmark ChromaDB loader accepting pre-computed vectors"
  - "ChromaDBLoader.load(bundle) upserts to 4 CHROMADB_COLLECTION_NAMES collections via get_or_create_collection"
  - "Batch error skip-and-log per D-07 (WARNING + continue)"
  - "No embedding_function on collection create (Pitfall 4 avoided)"
affects:
  - 22 (benchmark runner instantiates ChromaDBLoader as one of list[BaseLoader])
  - 23 (full dataset load uses ChromaDBLoader)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "get_or_create_collection(name=coll_name) — no embedding_function arg — collections accept pre-computed vectors only"
    - "prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn) as the standard call pattern for rich-metadata loaders"
    - "Batch chunk helper _chunks(lst, n) yielding n-sized slices with try/except per-batch WARNING logging"

key-files:
  created:
    - loaders/chromadb_loader.py
  modified: []

key-decisions:
  - "Use prepare_talk_bundle_rich (not plain prepare_talk_bundle) — rich metadata preserves list fields for Weaviate/Qdrant comparison; ChromaDB flatten happens via flatten_metadata inside prepare_talk_bundle_rich"
  - "No embedding_function on ChromaDB collection create — avoids Pitfall 4 (double embedding); pre-computed vectors passed exclusively via upsert(embeddings=...)"
  - "Same CHROMADB_COLLECTION_NAMES as production — benchmark uses isolated Docker port 8000, no naming collision"

patterns-established:
  - "ChromaDB benchmark loader is independent from extractors/phase6_chromadb_loader.py — zero imports from production loader"

requirements-completed:
  - BENCH-02

# Metrics
duration: 12min
completed: 2026-04-22
---

# Phase 21 Plan 03: ChromaDB Benchmark Loader Summary

**ChromaDBLoader(BaseLoader) in loaders/chromadb_loader.py — upserts pre-computed vectors to 4 production-named collections via get_or_create_collection, with batch-level skip-and-log error handling and no production loader imports.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-22T22:06:00Z
- **Completed:** 2026-04-22T22:18:00Z
- **Tasks:** 1 (TDD)
- **Files modified:** 1 (chromadb_loader.py new)

## Accomplishments
- `ChromaDBLoader` class inheriting `BaseLoader` created in `loaders/chromadb_loader.py`
- `load(bundle)` calls `prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)` and upserts to all 4 collections using `CHROMADB_COLLECTION_NAMES` keys
- Collection created with `get_or_create_collection(name=coll_name)` — no `embedding_function` argument (Pitfall 4 avoided)
- Per-batch exception handling logs `WARNING` with collection name and continues (D-07)
- All backward compat tests green (73 passed: test_shared_transforms.py + test_phase6.py)
- `tests/test_loaders_chromadb.py` skips cleanly when Docker is not running (per D-08)

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement loaders/chromadb_loader.py** - `20fd195` (feat)

**Plan metadata:** (see final commit below)

## Files Created/Modified
- `loaders/chromadb_loader.py` — ChromaDBLoader(BaseLoader) with load(), _chunks() helper, imports from config.pipeline_config and loaders.shared_transforms only

## Decisions Made
- Used `prepare_talk_bundle_rich` over plain `prepare_talk_bundle` — rich metadata preserves list types (topics, verse_list) for consistent record shape across all 3 loader implementations
- No `embedding_function` on `get_or_create_collection` — pre-computed vectors passed exclusively through `col.upsert(embeddings=vecs)` per Pitfall 4 avoidance

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Worktree virtualenv had no pytest installed (new virtualenv created for this worktree). Resolved by running `pipenv run pip install pytest` directly. The `pipenv install` command installed packages but did not install dev-packages in the worktree context. Not a code deviation — environment setup only.

## User Setup Required

None - no external service configuration required. Integration test auto-skips when ChromaDB Docker is not running.

## Next Phase Readiness
- `ChromaDBLoader` is fully implemented and ready for Phase 22 benchmark runner to instantiate
- Parallel Wave 3 loaders (Plans 04/05 — Weaviate and Qdrant) can proceed independently
- `from loaders.chromadb_loader import ChromaDBLoader` imports cleanly with `(<class 'loaders.BaseLoader'>,)` base

## Known Stubs
None — implementation is fully wired. The integration test round-trip (`test_round_trip_paragraph`) will execute when ChromaDB Docker is running on port 8000.

## Threat Surface Scan

No new network endpoints introduced. `ChromaDBLoader` calls the ChromaDB HTTP API at `localhost:8000` only (benchmark Docker instance). T-21-03-01 mitigation confirmed: metadata flows through `prepare_talk_bundle_rich()` which calls `flatten_metadata()` enforcing scalar types; no raw user input reaches `collection.upsert()`. T-21-03-03 documented in loader docstring (same collection names as production; isolation via separate Docker port).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| loaders/chromadb_loader.py exists | FOUND |
| `class ChromaDBLoader(BaseLoader)` | FOUND |
| `from extractors` imports | NONE (correct) |
| `prepare_talk_bundle_rich` usage | FOUND |
| `CHROMADB_COLLECTION_NAMES` usage | FOUND |
| `embedding_function` | NONE (correct — Pitfall 4) |
| Import check exits 0 + shows BaseLoader | PASSED |
| tests/test_loaders_chromadb.py: 1 skipped (Docker not running) | PASSED |
| test_shared_transforms.py + test_phase6.py: 73 passed | PASSED |
| Commit 20fd195 (ChromaDBLoader implementation) | FOUND |
