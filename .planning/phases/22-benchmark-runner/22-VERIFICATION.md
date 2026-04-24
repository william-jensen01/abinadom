---
phase: 22-benchmark-runner
verified: 2026-04-24T23:00:00Z
status: human_needed
score: 12/12 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run a real single-DB smoke test against a live ChromaDB container"
    expected: "Writes exactly 1 JSON file to benchmark/results/ with all 13 top-level keys (db, timestamp, upsert, query_latency_serial, query_latency_unfiltered, query_latency_filtered, scalability_curve, concurrency, memory_upsert, memory_query, cold_warm, determinism, recall); exits 0"
    why_human: "Requires Docker + Ollama running — cannot be verified programmatically without live infrastructure"
  - test: "Run --db all against all three live containers"
    expected: "Writes exactly 3 JSON files (chroma_*.json, weaviate_*.json, qdrant_*.json); chroma timestamp is earliest; all 3 files share identical top-level key sets; exits 0"
    why_human: "Requires all three DB containers + Ollama running"
---

# Phase 22: benchmark-runner Verification Report

**Phase Goal:** Developer can run a single CLI command against any of the three DBs and receive a structured JSON report covering all metric dimensions
**Verified:** 2026-04-24T23:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | psutil is importable in the pipenv environment | VERIFIED | `import psutil` prints 7.2.2 — confirmed live |
| 2 | ScalabilityCurveEntry is importable from benchmark.metrics | VERIFIED | `from benchmark.metrics import ScalabilityCurveEntry` exits 0 — confirmed live |
| 3 | ScalabilityCurveEntry has exactly five fields: workers (int), throughput_qps (float), p50_ms (float), p95_ms (float), p99_ms (float) | VERIFIED | `dataclasses.fields(ScalabilityCurveEntry)` output confirmed all 5 fields with correct types — confirmed live |
| 4 | BenchmarkRunner class exists and is instantiable with (loader, queries, config) | VERIFIED | `from benchmark.runner import BenchmarkRunner; hasattr(BenchmarkRunner, '__init__')` — class imported with all 4-param signature confirmed in source (line 116) |
| 5 | run_upsert_phase() loads talk bundles from SQLite and records UpsertMetrics | VERIFIED | Method defined at line 200; calls `_get_all_gc_talk_ids()`, `process_talk_pipeline()`, `self._loader.load(bundle)`, stores `asdict(UpsertMetrics(...))` to `self.results["upsert"]` — fully substantive, no stubs |
| 6 | run_cold_warm() is called immediately after run_upsert_phase() — before any other query method | VERIFIED | `run_all()` at line 495-504 calls `run_memory_upsert()` → `run_upsert_phase()` → `_finalize_memory_upsert()` → `run_cold_warm()` (step 4, first query call) — ordering confirmed in source |
| 7 | run_serial_latency() measures p50/p95/p99 at 1 worker across canonical queries | VERIFIED | Method at line 267; cycles query_limit queries serially, passes latencies to `_compute_query_metrics()` which computes p50/p95/p99 via percentile(), stores to `self.results["query_latency_serial"]` |
| 8 | run_filtered_unfiltered() produces separate QueryMetrics for the 6 unfiltered and 2 filtered canonical queries | VERIFIED | Method at line 287; splits `self._queries` by `q.get("filter") is None`, runs two groups independently, stores `self.results["query_latency_unfiltered"]` and `self.results["query_latency_filtered"]` |
| 9 | run_scalability_curve() issues --query-limit queries at each of [1, 5, 10, 20] workers and returns list[ScalabilityCurveEntry] | VERIFIED | Method at line 316; `worker_levels = [1, 5, 10, 20]` (line 322); uses `ThreadPoolExecutor(max_workers=n_workers)` per level; constructs and appends `ScalabilityCurveEntry`; stores `[asdict(e) for e in curve]` |
| 10 | run_memory_upsert() captures RSS before/after upsert (before/after snapshots only) | VERIFIED | `run_memory_upsert()` at line 179 stores `proc.memory_info().rss` to `self._mem_upsert_baseline_bytes`; `_finalize_memory_upsert()` at line 189 captures post-upsert RSS and stores `MemoryMetrics` — two-snapshot design confirmed |
| 11 | run_memory_query() captures peak RSS via background daemon thread during ThreadPoolExecutor phase | VERIFIED | Method at line 351; creates `threading.Event()` (line 360), `threading.Thread(target=_poll_memory, ..., daemon=True)` (line 361), runs ThreadPoolExecutor at `self._config.workers`, stops poller, takes `max(samples)` as peak — fully wired |
| 12 | run_determinism() issues each canonical query 10 times and computes Jaccard stability score | VERIFIED | Method at line 410; loops 10 times per query building `all_id_sets`, computes `set.intersection(*all_id_sets)` / `set.union(*all_id_sets)`, stores per-query stability scores |
| 13 | run_recall() queries ChromaDB for ground-truth IDs and computes mean recall@k10 and recall@k50 | VERIFIED | Method at line 433; calls `recall_at_k(baseline_ids, candidate_ids, k=10)` and re-queries at k=50 for k50; handles `chroma_baseline=None` by setting `recall=null`; stores `{"mean_k10": ..., "mean_k50": ...}` |
| 14 | `python benchmark/runner.py --help` exits 0 and shows all 5 args with defaults | VERIFIED | Confirmed live: `--db` (default: all), `--upsert-limit` (default: 100), `--query-limit` (default: 100), `--workers` (default: 10), `--output` (default: benchmark/results/) — all shown with defaults via ArgumentDefaultsHelpFormatter |
| 15 | run_all() sequences all 10 dimensions in the correct order | VERIFIED | Source at lines 492-518: run_memory_upsert → run_upsert_phase → _finalize_memory_upsert → run_cold_warm → run_serial_latency → run_filtered_unfiltered → run_scalability_curve → run_memory_query → run_latency_under_load → run_determinism → run_recall — exact SPEC-locked order |
| 16 | --db all benchmarks ChromaDB first, then Weaviate, then Qdrant | VERIFIED | `db_list = ["chroma", "weaviate", "qdrant"]` at line 643; chroma_baseline collected before iterating; ChromaDB passed `baseline=None` as it IS the baseline |
| 17 | JSON report written with all 13 top-level keys | VERIFIED | All 13 keys set in `self.results` by respective methods: `db` + `timestamp` (init), `upsert`, `cold_warm`, `query_latency_serial`, `query_latency_unfiltered`, `query_latency_filtered`, `scalability_curve`, `memory_upsert`, `memory_query`, `concurrency`, `determinism`, `recall` — every key traced to its setter |
| 18 | WeaviateLoader.close() called in finally block | VERIFIED | `finally: if loader is not None: loader.close()` at lines 687-689 |
| 19 | output directory auto-created with mkdir -p | VERIFIED | `out.mkdir(parents=True, exist_ok=True)` in `_write_report()` at line 532 |
| 20 | ChromaDB unreachable on single-DB run: recall=null, exit 0 | VERIFIED | `_collect_chroma_baseline()` returns None on exception (line 576); `run_recall(None)` sets `self.results["recall"] = None` (line 440); single-DB run does not set `had_failure` for this case; no `sys.exit(1)` triggered |
| 21 | DB unreachable on --db all: skip that DB, continue, exit non-zero | VERIFIED | `_build_loader()` wrapped in try/except at line 666; `had_failure = True` and `continue` on exception (lines 670-671); `sys.exit(1)` if `had_failure` at line 692 |

**Score:** 12/12 required plan must-haves verified (21 observable truths checked total)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `Pipfile` | psutil dependency declaration | VERIFIED | `psutil = "*"` present at line 17 |
| `benchmark/metrics.py` | ScalabilityCurveEntry dataclass (5 fields) | VERIFIED | Class at lines 54-62; all 5 fields confirmed live via dataclasses.fields() |
| `benchmark/runner.py` | BenchmarkRunner class with all 10 dimension measurement methods + run_all() + main() CLI | VERIFIED | File is 697 lines; all 10 methods + run_all + 5 module-level functions confirmed live; not a stub |
| `benchmark/results/` | Default output directory (auto-created at runtime) | VERIFIED | `_write_report()` calls `Path(output_dir).mkdir(parents=True, exist_ok=True)` — will be created on first run |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `benchmark/runner.py` | `benchmark/metrics.py` | `from benchmark.metrics import ScalabilityCurveEntry` | VERIFIED | Line 35 of runner.py; confirmed importable live |
| `BenchmarkRunner.run_upsert_phase` | `loader.load(bundle)` | `self._loader.load(bundle)` in talk loop | VERIFIED | Line 228 of runner.py |
| `BenchmarkRunner.run_scalability_curve` | `ThreadPoolExecutor` | `concurrent.futures.ThreadPoolExecutor(max_workers=N)` | VERIFIED | Lines 329, 365 of runner.py |
| `BenchmarkRunner.run_memory_query` | `psutil.Process().memory_info().rss` | background daemon thread polling at 150ms | VERIFIED | Lines 360-361, `_poll_memory()` at line 93 |
| `main()` | `BenchmarkRunner.run_all()` | `runner = BenchmarkRunner(...); runner.run_all()` | VERIFIED | Lines 676-682 of runner.py |
| `_write_report()` | `benchmark/results/{db}_{YYYYMMDD_HHMMSS}.json` | `json.dump(report, f, indent=2)` | VERIFIED | Lines 532-537 of runner.py |
| `run_all()` | `run_cold_warm()` | first query method called after `run_upsert_phase()` | VERIFIED | Lines 498-504 of runner.py confirm ordering |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `run_upsert_phase` | `UpsertMetrics` | `process_talk_pipeline()` + `self._loader.load()` — reads from SQLite | Yes — real DB pipeline call, not static | FLOWING |
| `run_scalability_curve` | `list[ScalabilityCurveEntry]` | `ThreadPoolExecutor` submitting `self._timed_query()` | Yes — real query latency measurements | FLOWING |
| `run_memory_query` | `MemoryMetrics` | `psutil.Process().memory_info().rss` sampled in background thread | Yes — real RSS readings from OS | FLOWING |
| `run_recall` | `{"mean_k10", "mean_k50"}` | `recall_at_k()` on actual query result IDs vs baseline | Yes — real computation on real query outputs | FLOWING |
| `_write_report` | JSON file | `self.results` dict populated by all methods | Yes — all 13 keys traced to real computation | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CLI exits 0 with all 5 args | `pipenv run py benchmark/runner.py --help` | Exits 0; shows --db (all), --upsert-limit (100), --query-limit (100), --workers (10), --output (benchmark/results/) | PASS |
| Module import | `from benchmark.runner import BenchmarkRunner; print('OK')` | Prints OK, exits 0 | PASS |
| All 11 BenchmarkRunner methods | `hasattr` check on all 10 + run_all | All present | PASS |
| All module-level functions | `hasattr` check on _write_report, _build_loader, etc. | All present | PASS |
| psutil importable | `import psutil; print(psutil.__version__)` | 7.2.2 | PASS |
| ScalabilityCurveEntry importable | `from benchmark.metrics import ScalabilityCurveEntry` | Exits 0, 5 fields confirmed | PASS |
| Full smoke run (single DB) | Requires Docker + Ollama | SKIPPED — infrastructure not available | SKIP |
| Full smoke run (--db all) | Requires Docker + Ollama + 3 DB containers | SKIPPED — infrastructure not available | SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| BENCH-07 | 22-01, 22-02, 22-03 | User can run the full benchmark from CLI (benchmark/runner.py) and receive a structured JSON report | SATISFIED | CLI entrypoint works (--help exits 0), BenchmarkRunner with all 10 dimensions implemented, JSON report wiring complete; blocked only on live infrastructure smoke test |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `benchmark/runner.py` | 158 | `return []` in `_query_db` exception handler | Info | Intentional failure fallback — `failed` counter tracks these; not a stub. Query data still flows when no exception |

No stubs, placeholders, TODOs, FIXMEs, or hardcoded empty returns that affect the goal. The `return []` at line 158 is a legitimate exception-path fallback inside `_query_db`, correctly tracked by `failed_queries` counters in callers.

### Human Verification Required

#### 1. Single-DB Smoke Test

**Test:** With ChromaDB container and Ollama running:
```
pipenv run py benchmark/runner.py --db chroma --upsert-limit 3 --query-limit 8 --output benchmark/results/
```
**Expected:** Exits 0; writes exactly 1 JSON file named `chroma_YYYYMMDD_HHMMSS.json` to `benchmark/results/`; file contains all 13 top-level keys: `db, timestamp, upsert, query_latency_serial, query_latency_unfiltered, query_latency_filtered, scalability_curve, concurrency, memory_upsert, memory_query, cold_warm, determinism, recall`
**Why human:** Requires live Docker containers (ChromaDB at localhost:8000) and Ollama with nomic-embed-text model loaded

#### 2. Multi-DB Ordering Test

**Test:** With all three DB containers and Ollama running:
```
pipenv run py benchmark/runner.py --db all --upsert-limit 3 --query-limit 8 --output benchmark/results/
```
**Expected:** Writes exactly 3 JSON files (`chroma_*.json`, `weaviate_*.json`, `qdrant_*.json`); ChromaDB file timestamp is earliest (benchmarked first); all 3 files share identical top-level key sets; `weaviate` and `qdrant` files have non-null `recall` key; `chroma` file has `recall: null`; exits 0
**Why human:** Requires all three DB containers (ports 8000, 8080, 6333) and Ollama running simultaneously

### Gaps Summary

No code gaps found. All must-have truths are verified at the implementation level. The phase is blocked solely on human verification of live infrastructure behavior, which cannot be automated without running Docker containers.

The implementation is complete and correct:
- All 10 measurement methods are substantive (real computation, real data flow)
- CLI entrypoint works (--help passes)
- Ordering constraints are enforced (cold/warm first, scalability before memory_query)
- Error handling is wired (recall=null for chroma, skip+exit-nonzero for DB unreachable on --db all)
- All 13 JSON report keys are populated by the run_all() sequence

---

_Verified: 2026-04-24T23:00:00Z_
_Verifier: Claude (gsd-verifier)_
