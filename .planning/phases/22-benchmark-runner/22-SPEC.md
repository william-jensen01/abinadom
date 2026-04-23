# Phase 22: Benchmark Runner — Specification

**Created:** 2026-04-23
**Ambiguity score:** 0.131 (gate: ≤ 0.20)
**Requirements:** 14 locked

## Goal

Developer can run a single CLI command that loads talks into any of the three vector DBs, measures performance across all benchmark dimensions, and emits a structured JSON report per DB — providing all signal needed for the Phase 23 production decision.

## Background

Phases 20–21 produced the full benchmark infrastructure: metric dataclasses (`benchmark/metrics.py`), canonical query set (`benchmark/queries.py`), and three DB loaders (`loaders/chromadb_loader.py`, `loaders/weaviate_loader.py`, `loaders/qdrant_loader.py`) behind a shared `BaseLoader` ABC. The `recall_at_k()` function exists in `benchmark/metrics.py`. What does not exist is an orchestrator that sequences the upsert → query → concurrency → memory → recall pipeline and writes the results to disk. `benchmark/runner.py` does not exist. This phase creates it.

Talk bundles are constructed from SQLite via `process_talk_pipeline()` + `validate_talk()`, identical to `scripts/run_pipeline.py`. Ollama (nomic-embed-text) must be running to generate embeddings. All three DBs run locally via `infra/docker-compose.vector-dbs.yml`.

## Requirements

1. **CLI entrypoint**: `benchmark/runner.py` accepts all required arguments via argparse.
   - Current: `benchmark/runner.py` does not exist
   - Target: `python benchmark/runner.py` is a valid CLI with `--db`, `--upsert-limit`, `--query-limit`, `--workers`, and `--output` arguments; `--db` defaults to `all`; `--workers` defaults to 10; `--output` defaults to `benchmark/results/`
   - Acceptance: `python benchmark/runner.py --help` exits 0 and shows all five arguments with their defaults and accepted values

2. **Data source**: TalkBundles constructed from SQLite via existing pipeline extractors.
   - Current: TalkBundle construction exists only in `scripts/run_pipeline.py`
   - Target: Runner calls `process_talk_pipeline()` + `validate_talk()` per talk_id (same path as run_pipeline.py), limited to `--upsert-limit` talks drawn from `_get_all_gc_talk_ids()` order
   - Acceptance: Running `--upsert-limit 10` loads records derived from exactly 10 distinct talk_ids into the target DB(s); the runner does not read pre-built JSON or pickle files

3. **Load gate**: All talks upserted before any query benchmark executes.
   - Current: No runner; no gate exists
   - Target: Runner completes the full upsert phase (all `--upsert-limit` talks loaded and confirmed) before issuing the first canonical query against any DB
   - Acceptance: With `--upsert-limit 10` and DEBUG logging enabled, all 10 upsert completions appear in the log before any query-phase log line; no query exception caused by missing data on a cold load

4. **Upsert metrics**: Upsert speed captured inline during the load phase.
   - Current: No runner; no upsert measurement
   - Target: Runner wraps each DB's load loop with wall-clock timing and record counting; writes a `UpsertMetrics` dataclass (total_records, elapsed_seconds, records_per_second) into the report
   - Acceptance: JSON report `upsert.total_records` > 0, `upsert.elapsed_seconds` > 0, `upsert.records_per_second` = total_records / elapsed_seconds ± 1%

5. **Serial query latency**: p50/p95/p99 latency measured at 1 worker across canonical queries.
   - Current: No runner; no latency measurement
   - Target: Runner issues all `--query-limit` canonical queries sequentially (1 thread), records per-query wall-clock latency in ms, derives p50/p95/p99/mean/min/max via `QueryMetrics`
   - Acceptance: JSON report `query_latency_serial` contains p50_ms, p95_ms, p99_ms, mean_ms, min_ms, max_ms, query_count; all values > 0

6. **Filtered vs unfiltered latency**: Canonical queries split by filter presence; separate `QueryMetrics` per group.
   - Current: No runner; CANONICAL_QUERIES has 6 unfiltered and 2 filtered entries
   - Target: Runner segregates queries by `filter is None`; reports `query_latency_unfiltered` (6 queries) and `query_latency_filtered` (2 queries) as separate `QueryMetrics` blocks
   - Acceptance: JSON report contains both `query_latency_unfiltered` and `query_latency_filtered` blocks; `query_latency_unfiltered.query_count` = 6, `query_latency_filtered.query_count` = 2 (when `--query-limit` ≥ 8)

7. **Scalability curve**: Throughput and latency measured at worker counts 1, 5, 10, and 20.
   - Current: No runner; no concurrency measurement
   - Target: Runner issues `--query-limit` queries (cycling through CANONICAL_QUERIES) at each of 1, 5, 10, 20 workers using `ThreadPoolExecutor`; records throughput_qps and query latency at each level; the same total query count is used at every level for fair comparison
   - Acceptance: JSON report `scalability_curve` is an array of exactly 4 objects, each containing `workers`, `throughput_qps`, `p50_ms`, `p95_ms`, `p99_ms`; workers values are [1, 5, 10, 20] in order

8. **Latency-under-load**: Latency degradation ratio at `--workers` N vs serial baseline.
   - Current: No runner; no degradation measurement
   - Target: Runner computes `latency_degradation_ratio = p50_ms_at_N_workers / p50_ms_serial` where N = `--workers` (default 10); reports ratio in the `concurrency` block
   - Acceptance: JSON report `concurrency.latency_degradation_ratio` ≥ 1.0 and is derived from the scalability_curve entry matching `--workers`; `concurrency.workers` = N

9. **Memory delta**: psutil RSS snapshots before/after upsert and during peak query concurrency.
   - Current: No runner; no memory measurement; psutil not in Pipfile
   - Target: Runner takes `psutil.Process().memory_info().rss` snapshots at: (a) before upsert start, (b) after upsert completes, (c) before and during peak concurrency query phase; writes `MemoryMetrics` for each phase
   - Acceptance: JSON report contains `memory_upsert` (baseline_mb, peak_mb, delta_mb) and `memory_query` (baseline_mb, peak_mb, delta_mb); all baseline_mb values > 0; psutil added to Pipfile

10. **Cold vs warm latency**: First query latency vs mean of 9 subsequent runs of the same query.
    - Current: No runner; no cold/warm measurement
    - Target: Runner issues the first canonical query once (cold read, immediately after load gate clears), then issues the same query 9 more times consecutively; records cold_ms and warm_mean_ms
    - Acceptance: JSON report `cold_warm.cold_ms` and `cold_warm.warm_mean_ms` are both > 0; query used is identified by `cold_warm.query_text`

11. **Result determinism**: Jaccard stability score across 10 repeated runs of each canonical query.
    - Current: No runner; `recall_at_k()` exists but not used for determinism
    - Target: Runner issues each canonical query 10 times; for each query computes the Jaccard similarity of the union of top-k result ID sets across all 10 runs (fraction of IDs that appear in every run); reports per-query stability score in [0.0, 1.0]
    - Acceptance: JSON report `determinism` is an array of 8 objects (one per canonical query) each with `query_text` and `stability_score`; a score of 1.0 means all 10 runs returned identical top-k IDs; array length = number of canonical queries run

12. **recall@k**: ChromaDB as ground-truth baseline; mean recall@k10 and recall@k50 computed per DB.
    - Current: `recall_at_k()` exists in `benchmark/metrics.py` but is not orchestrated
    - Target: Runner queries ChromaDB for baseline top-k result IDs; queries Weaviate/Qdrant for candidate IDs; applies `recall_at_k()` at k=10 and k=50 per canonical query; reports mean across all queries as `recall.mean_k10` and `recall.mean_k50`; ChromaDB JSON report sets `recall: null`; when ChromaDB is unreachable on a single-DB run, report sets `recall: null` and runner logs a WARNING
    - Acceptance: Weaviate and Qdrant JSON reports contain `recall.mean_k10` and `recall.mean_k50` as floats in [0.0, 1.0] (when ChromaDB reachable); ChromaDB report has `recall: null`; `--db weaviate` with ChromaDB unreachable produces a valid JSON report with `recall: null` and does not error out

13. **JSON report schema**: One flat JSON file per DB per run; identical top-level schema across all DBs.
    - Current: No JSON output exists
    - Target: Runner writes `{db}_{YYYYMMDD_HHMMSS}.json` to `--output` directory (created if absent); all DB reports share identical top-level keys: `db`, `timestamp`, `upsert`, `query_latency_serial`, `query_latency_unfiltered`, `query_latency_filtered`, `scalability_curve`, `concurrency`, `memory_upsert`, `memory_query`, `cold_warm`, `determinism`, `recall`
    - Acceptance: `json.load()` succeeds on all output files; `--db all` produces exactly 3 files; `--db chroma` produces exactly 1 file; all 3 files from `--db all` have identical sets of top-level keys

14. **Multi-DB run ordering**: `--db all` benchmarks ChromaDB first, then Weaviate, then Qdrant.
    - Current: No runner; no ordering defined
    - Target: When `--db all`, runner upserts and benchmarks ChromaDB first (establishing recall@k baseline), then proceeds to Weaviate, then Qdrant; each DB is fully benchmarked (all dimensions) before the next DB begins
    - Acceptance: With `--db all`, the three output files have timestamps in order chroma → weaviate → qdrant; log output confirms sequential DB ordering

## Boundaries

**In scope:**
- `benchmark/runner.py` — CLI entrypoint with argparse
- Talk data loaded from SQLite via `process_talk_pipeline()` + `validate_talk()` (limited by `--upsert-limit`)
- All 10 benchmark dimensions: upsert speed, serial latency, filtered/unfiltered split, scalability curve, latency-under-load, memory delta, cold/warm latency, result determinism, recall@k
- JSON report output — one file per DB, written to `--output` directory
- ChromaDB as ground-truth baseline for recall@k (queried read-only on single-DB runs)
- psutil added to Pipfile as a new dependency
- `benchmark/results/` directory auto-created if absent

**Out of scope:**
- Mixed read/write concurrency (upsert and query simultaneously) — deferred to backlog; adds complexity without clear signal for DB selection at this stage
- A written decision report naming the winning DB — that is Phase 23's deliverable
- Full 5,838-talk benchmark run at production scale — Phase 23 executes the runner at full scale; Phase 22 validates correctness with small `--upsert-limit`
- Loading talk bundles from pre-built JSON or pickle files — always from SQLite via pipeline extractors
- Re-embedding with a different model — nomic-embed-text only throughout benchmark and migration
- A progress UI or interactive dashboard — runner outputs to JSON only; console output is plain log lines

## Constraints

- **psutil**: Required for RSS memory measurement; must be added to Pipfile before execution. `tracemalloc` is insufficient — it misses native library memory used by ChromaDB's C++ layer, Qdrant's Rust client, and Weaviate's gRPC buffers, making cross-DB memory comparison misleading.
- **ThreadPoolExecutor**: All concurrency uses `concurrent.futures.ThreadPoolExecutor`. All three DB clients (chromadb, weaviate-client v4, qdrant-client) expose synchronous APIs; asyncio wrapping adds complexity with no benefit.
- **Ollama must be running**: `loaders/embeddings.py` calls the local Ollama server (nomic-embed-text). Runner fails fast if Ollama is unreachable.
- **ChromaDB benchmarked first**: When `--db all`, ChromaDB must complete its full benchmark pass before Weaviate or Qdrant begin, because ChromaDB result IDs are the recall@k ground truth.
- **Same `--query-limit` at every scalability curve level**: Total queries issued is identical across worker counts (1, 5, 10, 20) to ensure QPS and latency are directly comparable.
- **Output directory**: Default `benchmark/results/`; created with `mkdir -p` if absent; runner must not error if directory already exists.

## Acceptance Criteria

- [ ] `python benchmark/runner.py --help` exits 0 and shows --db (default: all), --upsert-limit, --query-limit, --workers (default: 10), --output (default: benchmark/results/) with descriptions
- [ ] `python benchmark/runner.py --db chroma --upsert-limit 10 --query-limit 10` completes without error and writes exactly 1 JSON file to benchmark/results/
- [ ] `python benchmark/runner.py --db all --upsert-limit 10 --query-limit 10` writes exactly 3 JSON files; all have identical top-level key sets
- [ ] Each JSON file contains all required top-level keys: db, timestamp, upsert, query_latency_serial, query_latency_unfiltered, query_latency_filtered, scalability_curve, concurrency, memory_upsert, memory_query, cold_warm, determinism, recall
- [ ] `upsert.total_records` > 0 and `upsert.records_per_second` = total_records / elapsed_seconds ± 1%
- [ ] Load gate enforced: with DEBUG logging, all upsert completion entries precede all query-phase entries in the log
- [ ] `scalability_curve` contains exactly 4 entries with workers = [1, 5, 10, 20]; each entry has throughput_qps, p50_ms, p95_ms, p99_ms
- [ ] `determinism` array length equals the number of canonical queries run (8 when --query-limit ≥ 8); each entry has query_text and stability_score in [0.0, 1.0]
- [ ] Weaviate and Qdrant reports have `recall.mean_k10` and `recall.mean_k50` as non-null floats when ChromaDB is reachable; ChromaDB report has `recall: null`
- [ ] `python benchmark/runner.py --db weaviate --upsert-limit 10 --query-limit 10` with ChromaDB unreachable produces a valid JSON file with `recall: null` and exits 0 (no crash)
- [ ] `query_latency_unfiltered.query_count` = 6 and `query_latency_filtered.query_count` = 2 (when --query-limit ≥ 8)
- [ ] `memory_upsert.baseline_mb` > 0 and `memory_query.baseline_mb` > 0 in every report
- [ ] psutil present in Pipfile and importable in the benchmark environment

## Ambiguity Report

| Dimension           | Score | Min  | Status | Notes                                                        |
|---------------------|-------|------|--------|--------------------------------------------------------------|
| Goal Clarity        | 0.92  | 0.75 | ✓      | CLI design, data source, and all dimensions confirmed        |
| Boundary Clarity    | 0.85  | 0.70 | ✓      | Mixed read/write deferred; recall@k single-DB behavior locked|
| Constraint Clarity  | 0.85  | 0.65 | ✓      | psutil, ThreadPoolExecutor, worker defaults, ordering locked  |
| Acceptance Criteria | 0.82  | 0.70 | ✓      | 13 pass/fail checkboxes covering all requirements            |
| **Ambiguity**       | 0.131 | ≤0.20| ✓      |                                                              |

## Interview Log

| Round | Perspective      | Question summary                              | Decision locked                                                            |
|-------|------------------|-----------------------------------------------|----------------------------------------------------------------------------|
| 1     | Researcher       | Where do talk bundles come from?             | SQLite via process_talk_pipeline() + validate_talk() — same as run_pipeline.py |
| 1     | Researcher       | Load then query, or query only?              | Load then query (all-in-one); load gate enforced                           |
| 1     | Researcher       | recall@k in Phase 22 or Phase 23?            | Phase 22 — runner computes recall@k with ChromaDB as baseline              |
| 2     | Researcher       | CLI design: subcommands vs --mode flag?      | Single entrypoint; roadmap success criteria imply single command           |
| 2     | Researcher       | JSON schema: flat per-DB vs nested all-DBs?  | Flat per-DB report; one file per DB per run                                |
| 2     | Simplifier       | Which metric dimensions to include?          | All 4 roadmap dimensions + filtered/unfiltered, scalability curve, cold/warm, determinism |
| 3     | Boundary Keeper  | recall@k on single-DB runs?                  | ChromaDB queried read-only as baseline; null with warning if unreachable   |
| 3     | Boundary Keeper  | Determinism: pass/fail or score?             | 10 runs, Jaccard stability score (not hard pass/fail)                      |
| 3     | Boundary Keeper  | Scalability curve: same queries at each level?| Same --query-limit at 1/5/10/20 workers for fair comparison                |
| 4     | Failure Analyst  | Memory: tracemalloc vs psutil?               | psutil RSS — tracemalloc misses native library memory; cross-DB comparison would be misleading |
| 4     | Failure Analyst  | Concurrency: threads vs asyncio?             | ThreadPoolExecutor — all 3 DB clients are sync; asyncio adds no benefit    |
| 4     | Failure Analyst  | What does concurrency actually measure?      | Latency degradation (Option C) + scalability curve + QPS — comprehensive production-scenario simulation |
| 5     | Seed Closer      | Mixed read/write: in or out of Phase 22?     | Deferred to backlog — interesting but adds harness complexity               |

---

*Phase: 22-benchmark-runner*
*Spec created: 2026-04-23*
*Next step: /gsd-discuss-phase 22 — implementation decisions (runner architecture, JSON serialization, error handling)*
