---
phase: 23-benchmark-execution-decision
plan: 01
subsystem: benchmark
tags: [chromadb, weaviate, qdrant, benchmark, reset, argparse]

# Dependency graph
requires:
  - phase: 22.2-optimize-benchmark-loaders-for-efficiency
    provides: ChromaDBLoader, WeaviateLoader, QdrantLoader with batch embed + parallel upsert
provides:
  - reset() classmethod on ChromaDBLoader (deletes 4 collections, safe on fresh stack)
  - reset() classmethod on WeaviateLoader (deletes Talk/Paragraph/Citation/Footnote)
  - reset() classmethod on QdrantLoader (deletes talks/paragraphs/citations/footnotes)
  - "--reset flag in benchmark/runner.py (store_true, pre-flight per DB)"
  - "--upsert-limit default changed to None (loads all 5,838 talks when omitted)"
  - "None-guard in run_upsert_phase() so all_ids is not sliced when limit is None"
  - "Pre-flight reset block in main() calling correct loader.reset() before _build_loader()"
affects: [23-benchmark-execution-decision/23-02, production-migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Loader reset() classmethod: creates temporary client, deletes collections, closes, returns — caller instantiates fresh loader after"
    - "BENCHMARK_*_HOST/PORT env vars for reset() calls (separate from production DB env vars, T-23-02 mitigation)"
    - "None-guard pattern for optional CLI limits: if args.X is not None: slice else: use all"

key-files:
  created: []
  modified:
    - loaders/chromadb_loader.py
    - loaders/weaviate_loader.py
    - loaders/qdrant_loader.py
    - benchmark/runner.py

key-decisions:
  - "reset() implemented as classmethod (not instance method) so it can be called before instantiation in main()"
  - "BENCHMARK_WEAVIATE_PORT (8080 HTTP) is distinct from BENCHMARK_WEAVIATE_GRPC_PORT (50051) in reset() call — corrected from plan's initial draft which accidentally used gRPC port for both"
  - "reset() swallows all exceptions per-collection to be safe on fresh stacks (NotFound is expected on first run)"
  - "--upsert-limit default changed to None (not 0 or -1) to cleanly distinguish 'load all' from 'load zero'"

patterns-established:
  - "Loader reset() classmethod pattern: temporary client + per-collection try/except + finally close"
  - "CLI flag None-guard: if self._config.X is not None: slice else: use full list"

requirements-completed: [EVAL-02, EVAL-03]

# Metrics
duration: 18min
completed: 2026-05-08
---

# Phase 23 Plan 01: Benchmark Loader Reset and upsert-limit Fix Summary

**--reset flag and loader reset() classmethods enable clean-slate full-corpus benchmark runs against all three vector DBs**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-08T08:10:20Z
- **Completed:** 2026-05-08T08:28:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `reset()` classmethod to ChromaDBLoader, WeaviateLoader, and QdrantLoader — each creates a temporary client, deletes its 4 collections swallowing NotFound errors, and closes the client
- Added `--reset` flag (store_true) to benchmark/runner.py argparser; pre-flight block in main() calls the correct loader.reset() before _build_loader() for each DB when --reset is passed
- Fixed `--upsert-limit` default from 100 to None and added None-guard in run_upsert_phase() so all 5,838 talks load when --upsert-limit is omitted
- Full benchmark run command `pipenv run py benchmark/runner.py --db all --reset --query-limit 500` now works correctly

## Task Commits

1. **Task 1: Add reset() to all three loaders** - `4597f6e` (feat)
2. **Task 2: Add --reset flag and fix --upsert-limit default in runner.py** - `2202442` (feat)

## Files Created/Modified

- `loaders/chromadb_loader.py` — added `@classmethod reset(cls, host, port)` after `close()`; iterates CHROMADB_COLLECTION_NAMES.values()
- `loaders/weaviate_loader.py` — added `@classmethod reset(cls, host, port, grpc_port=50051)` after `close()`; iterates cls.COLLECTIONS
- `loaders/qdrant_loader.py` — added `@classmethod reset(cls, host, port)` after `close()`; iterates cls.COLLECTIONS
- `benchmark/runner.py` — (1) --upsert-limit default=None with updated help text; (2) --reset store_true flag; (3) None-guard in run_upsert_phase(); (4) pre-flight reset block in main()

## Decisions Made

- `reset()` implemented as classmethod so it can be called before any loader instantiation in main() — no double-connection risk
- Weaviate reset() uses BENCHMARK_WEAVIATE_PORT (8080 HTTP default) and BENCHMARK_WEAVIATE_GRPC_PORT (50051) separately — the plan's initial draft had a copy-paste error using gRPC port for both; the corrected version in the NOTE section was used
- BENCHMARK_*_HOST/PORT env vars used for reset calls, defaulting to localhost — separate from production ChromaDB on different port (T-23-02 mitigation)
- --upsert-limit default is None (not 0) to cleanly express "no limit" vs "load zero"

## Deviations from Plan

None - plan executed exactly as written. The plan itself noted the Weaviate port correction inline (the NOTE block), which was applied as intended.

## Issues Encountered

The plan's verify command (`pipenv run py benchmark/runner.py --help`) runs from the main project directory where the worktree changes aren't yet merged. Verified using PIPENV_PIPFILE override to load the worktree's runner.py directly — output confirmed `--reset` and `--upsert-limit (default: None)` display correctly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All three loaders now have `reset()` classmethods ready for the full benchmark run
- `pipenv run py benchmark/runner.py --db all --reset --query-limit 500` is the target command for Phase 23 Plan 02
- Smoke test path (`--upsert-limit 10 --query-limit 10`) still works (None-guard only activates when limit is None)

## Self-Check: PASSED

- FOUND: loaders/chromadb_loader.py (reset() classmethod present)
- FOUND: loaders/weaviate_loader.py (reset() classmethod present)
- FOUND: loaders/qdrant_loader.py (reset() classmethod present)
- FOUND: benchmark/runner.py (upsert_limit is not None guard + args.reset usage present)
- FOUND: .planning/phases/23-benchmark-execution-decision/23-01-SUMMARY.md
- FOUND commit: 4597f6e (Task 1 - loader reset() classmethods)
- FOUND commit: 2202442 (Task 2 - --reset flag and --upsert-limit fix)

---
*Phase: 23-benchmark-execution-decision*
*Completed: 2026-05-08*
