---
phase: 22-benchmark-runner
plan: "02"
subsystem: benchmark
tags: [benchmark, runner, measurement, psutil, threading, concurrency]
dependency_graph:
  requires:
    - psutil installed (Plan 01)
    - ScalabilityCurveEntry in benchmark/metrics.py (Plan 01)
    - loaders/chromadb_loader.py (Phase 21)
    - loaders/weaviate_loader.py (Phase 21)
    - loaders/qdrant_loader.py (Phase 21)
    - benchmark/queries.py (Phase 20)
    - benchmark/metrics.py (Phase 20 + Plan 01)
  provides:
    - BenchmarkRunner class in benchmark/runner.py
    - query() method on ChromaDBLoader
    - query() method on WeaviateLoader
    - query() method on QdrantLoader
  affects:
    - benchmark/runner.py (Plan 03 — run_all() sequences these methods)
tech_stack:
  added: []
  patterns:
    - "ThreadPoolExecutor with as_completed() for concurrent query phases"
    - "Background daemon thread polling psutil.Process().rss every 150ms"
    - "Jaccard set similarity (intersection/union) for determinism scoring"
    - "dataclasses.asdict() for all metric serialization"
    - "sys.path.insert(0, ...) bootstrap for benchmark/ subpackage scripts"
key_files:
  created:
    - benchmark/runner.py
  modified:
    - loaders/chromadb_loader.py
    - loaders/weaviate_loader.py
    - loaders/qdrant_loader.py
decisions:
  - "query() methods added to all 3 loaders as Rule 3 auto-fix (blocking — runner cannot call without them)"
  - "PARAGRAPH_CONFIG imported from config.schemas (not config.pipeline_config as plan stated — it only exists in schemas.py)"
  - "Collection name map added to WeaviateLoader.query() to translate snake_case to PascalCase class names"
  - "Qdrant query() uses query_points() API with with_payload=['_doc_id'] to retrieve original string IDs"
metrics:
  duration_seconds: 391
  completed: "2026-04-24T09:25:35Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 4
requirements_satisfied:
  - BENCH-07
---

# Phase 22 Plan 02: BenchmarkRunner Class Summary

**One-liner:** BenchmarkRunner class with all 10 measurement methods (upsert, cold/warm, serial latency, filtered/unfiltered, scalability curve, memory, latency-under-load, determinism, recall@k) implemented in benchmark/runner.py using ThreadPoolExecutor, psutil daemon-thread polling, and Jaccard set similarity.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create benchmark/runner.py — imports, helpers, BenchmarkRunner.__init__ | 2c9622e | benchmark/runner.py, loaders/chromadb_loader.py, loaders/weaviate_loader.py, loaders/qdrant_loader.py |
| 2 | Implement all 10 BenchmarkRunner measurement methods (docstring addition) | 48c9a72 | benchmark/runner.py |

## What Was Built

**benchmark/runner.py** (new file, ~320 lines):

- Module-level helpers: `_get_all_gc_talk_ids()`, `_compute_query_metrics()`, `_poll_memory()`
- `BenchmarkRunner.__init__(loader, queries, config, db_name)` — stores loader, queries, config, db_name; initializes `self.results` dict with `db` and `timestamp`
- 10 measurement methods in plan-specified call order:
  1. `run_memory_upsert()` — captures RSS baseline before upsert; `_finalize_memory_upsert()` records delta after
  2. `run_upsert_phase()` — load gate: processes each talk via `process_talk_pipeline()` + `validate_talk()`, calls `self._loader.load(bundle)`, records `UpsertMetrics`
  3. `run_cold_warm()` — first canonical query (cold), then 9 more (warm); MUST be first query-issuing call after upsert
  4. `run_serial_latency()` — cycles `--query-limit` queries through CANONICAL_QUERIES at 1 thread; records `QueryMetrics`
  5. `run_filtered_unfiltered()` — splits queries by `filter is None` (6 unfiltered, 2 filtered); separate `QueryMetrics` per group
  6. `run_scalability_curve()` — issues `--query-limit` queries at [1, 5, 10, 20] workers via `ThreadPoolExecutor`; records `list[ScalabilityCurveEntry]`
  7. `run_memory_query()` — background daemon thread polls RSS at 150ms during ThreadPoolExecutor phase; records peak `MemoryMetrics`
  8. `run_latency_under_load()` — reads scalability_curve to compute `latency_degradation_ratio = p50_at_N / p50_serial`; records `ConcurrencyMetrics`
  9. `run_determinism()` — 10 runs per canonical query; Jaccard = `|intersection| / |union|`; records per-query stability scores
  10. `run_recall()` — accepts optional `chroma_baseline` dict; computes `mean_k10` and `mean_k50` via `recall_at_k()`; sets `recall: null` when baseline is None

**Rule 3 auto-fixes — query() methods added to all 3 loaders:**

- `ChromaDBLoader.query()` — embeds query text, calls `col.query()` with optional `where` filter, returns `ids[0]`
- `WeaviateLoader.query()` — maps snake_case collection name to PascalCase class, calls `near_vector()` with optional `Filter`, returns `obj.properties["id"]` or UUID
- `QdrantLoader.query()` — uses `query_points()` API with `with_payload=["_doc_id"]`, builds `FieldCondition` filters, returns `payload["_doc_id"]` strings

## Verification Results

1. `from benchmark.runner import BenchmarkRunner` — exits 0, no ImportError
2. `BenchmarkRunner.__init__.__doc__` — prints "Initialize the benchmark runner for a single vector DB."
3. All 10 method names present in BenchmarkRunner
4. `threading.Thread` + `threading.Event` present (memory polling daemon)
5. `ThreadPoolExecutor` present (scalability curve and memory_query)
6. `set.intersection(` present (Jaccard stability in run_determinism)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing query() methods on all 3 loaders**
- **Found during:** Task 1 — runner needs `self._loader.query()` for all 10 measurement methods
- **Issue:** `ChromaDBLoader`, `WeaviateLoader`, and `QdrantLoader` had no `query()` method; the plan's `<interfaces>` section listed it but it was never implemented in Phase 21
- **Fix:** Added `query(collection, query_text, k, filter)` to all 3 loaders; each embeds via `self.embed_fn`, queries the DB client, and returns `list[str]` of document IDs
- **Files modified:** `loaders/chromadb_loader.py`, `loaders/weaviate_loader.py`, `loaders/qdrant_loader.py`
- **Commit:** 2c9622e

**2. [Rule 1 - Bug] PARAGRAPH_CONFIG import location mismatch**
- **Found during:** Task 1 import fix
- **Issue:** Plan stated `from config.pipeline_config import PARAGRAPH_CONFIG` but `PARAGRAPH_CONFIG` only exists in `config.schemas`
- **Fix:** Changed import to `from config.schemas import PARAGRAPH_CONFIG`
- **Files modified:** `benchmark/runner.py`
- **Commit:** 2c9622e

## Known Stubs

None — no placeholder values or mock data introduced. `run_recall(chroma_baseline=None)` sets `recall: null` when no baseline is provided, which is the correct and documented behavior per SPEC Req 12 (not a stub — it is intentional for the ChromaDB target DB case).

## Threat Surface Scan

No new network endpoints or auth paths introduced. The runner reads from SQLite (local, read-only) and writes to local Docker vector DB instances. The `query()` methods on the loaders open existing client connections already established in `__init__`. No new trust boundaries.

T-22-02-01 (ThreadPoolExecutor DoS) mitigated: workers bounded by `config.workers` (default 10, user-supplied via argparse).
T-22-02-02 (empty SQLite) mitigated: `run_upsert_phase()` logs WARNING per failed talk and returns `UpsertMetrics(total_records=0)`.
T-22-02-05 (run_recall None path) mitigated: explicit `if chroma_baseline is None` guard returns early with `recall=null`.

## Self-Check: PASSED

- `benchmark/runner.py` exists: confirmed
- `from benchmark.runner import BenchmarkRunner` succeeds: confirmed
- All 10 methods present: confirmed (verified via `hasattr` check)
- `threading.Thread`, `threading.Event`, `ThreadPoolExecutor`, `set.intersection`, `recall_at_k` all in source: confirmed
- Commit 2c9622e exists: confirmed
- Commit 48c9a72 exists: confirmed
- loaders/chromadb_loader.py has `def query(`: confirmed
- loaders/weaviate_loader.py has `def query(`: confirmed
- loaders/qdrant_loader.py has `def query(`: confirmed
