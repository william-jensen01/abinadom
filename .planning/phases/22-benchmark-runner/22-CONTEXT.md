# Phase 22: Benchmark Runner — Context

**Gathered:** 2026-04-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Creates `benchmark/runner.py` — the CLI orchestrator that sequences upsert → benchmark →
JSON report for any of the three vector DBs (ChromaDB, Weaviate, Qdrant). All 10 benchmark
dimensions (upsert speed, serial latency, filtered/unfiltered split, scalability curve,
latency-under-load, memory delta, cold/warm latency, determinism, recall@k) are measured
and emitted in one structured JSON file per DB per run.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**14 requirements are locked.** See `22-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `22-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `benchmark/runner.py` — CLI entrypoint with argparse (`--db`, `--upsert-limit`, `--query-limit`, `--workers`, `--output`)
- Talk data loaded from SQLite via `process_talk_pipeline()` + `validate_talk()` (limited by `--upsert-limit`)
- All 10 benchmark dimensions: upsert speed, serial latency, filtered/unfiltered split, scalability curve, latency-under-load, memory delta, cold/warm latency, result determinism, recall@k
- JSON report output — one file per DB per run, written to `--output` directory
- ChromaDB as ground-truth baseline for recall@k (queried read-only on single-DB runs)
- psutil added to Pipfile as a new dependency
- `benchmark/results/` directory auto-created if absent
- `ScalabilityCurveEntry` dataclass added to `benchmark/metrics.py`

**Out of scope (from SPEC.md):**
- Mixed read/write concurrency — deferred to backlog
- A written decision report naming the winning DB — Phase 23
- Full 5,838-talk benchmark run — Phase 23
- Loading talk bundles from pre-built JSON or pickle files
- Re-embedding with a different model
- A progress UI or interactive dashboard

</spec_lock>

<decisions>
## Implementation Decisions

### Runner Module Organization

- **D-01:** `benchmark/runner.py` uses a **`BenchmarkRunner` class** that holds per-DB state: the loader instance, canonical queries, config (parsed args), and `self.results` dict. Methods per benchmark dimension (e.g., `run_upsert_phase()`, `run_serial_latency()`, `run_scalability_curve()`). `run_all() -> dict` sequences all 10 dimensions and returns the assembled report dict. Consistent with Phase 21's class-per-loader pattern (same "connection state + loop over many calls" structure).
- **D-02:** `main()` iterates over resolved DB list, instantiates one `BenchmarkRunner` per DB, calls `runner.run_all()`, and passes the result to a `_write_report()` module-level function.

### DB Failure Handling

- **D-03:** When `--db all` is used and a primary benchmark target (Weaviate, Qdrant) is unreachable at connection time: log an ERROR for that DB, skip it, continue benchmarking the remaining DBs, and exit with a **non-zero exit code** to signal partial failure.
- **D-04:** ChromaDB is always attempted first (SPEC Req 14 ordering: chroma → weaviate → qdrant), so the recall@k baseline is established before Weaviate/Qdrant runs — the skip-and-continue behavior does not break recall@k for surviving DBs.
- **D-05:** The existing SPEC-locked behavior for ChromaDB recall@k baseline unreachability remains unchanged: `recall: null` + WARNING, no crash, exit 0 for that report.

### Memory Peak Measurement

- **D-06:** Peak RSS "during concurrent query phase" (SPEC Req 9) is captured by a **background daemon thread** that polls `psutil.Process().memory_info().rss` at ~150ms intervals during the `ThreadPoolExecutor` concurrent phase. `peak_mb = max(all samples)` / 1024² . Daemon thread — no explicit cleanup needed; it stops when the phase completes.
- **D-07:** Upsert memory (`memory_upsert`) uses before/after snapshots only: RSS before upsert loop starts and after all bundles are loaded. No polling thread needed — upsert is single-threaded and sequential.

### JSON Serialization

- **D-08:** All metric dataclasses are serialized with **`dataclasses.asdict()`** — consistent with the project's existing `asdict()` usage in `shared_transforms.py`. The report dict is written with `json.dump(report, f, indent=2)`.
- **D-09:** A new **`ScalabilityCurveEntry` dataclass** is added to `benchmark/metrics.py` (alongside the Phase 20 dataclasses) to hold the per-level scalability data: `workers: int`, `throughput_qps: float`, `p50_ms: float`, `p95_ms: float`, `p99_ms: float`. The `scalability_curve` report key holds `[dataclasses.asdict(entry) for entry in curve]`.

### Claude's Discretion

- Exact polling interval for memory peak thread (100–200ms range is acceptable)
- Exact logging format for benchmark progress (INFO level lines per SPEC; "plain log lines" is the requirement)
- Internal helper method names within `BenchmarkRunner`
- Whether `BenchmarkRunner` exposes a `reset()` method or is simply re-instantiated per DB

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and Specification
- `.planning/phases/22-benchmark-runner/22-SPEC.md` — Locked requirements (14), boundaries, constraints, acceptance criteria — MUST read first
- `.planning/REQUIREMENTS.md` — v4.0 requirement IDs: BENCH-07 (Phase 22 runner)

### Phase 22 Dependencies (Phase 20 + 21 deliverables)
- `benchmark/metrics.py` — UpsertMetrics, QueryMetrics, ConcurrencyMetrics, MemoryMetrics, recall_at_k; ScalabilityCurveEntry to be added here
- `benchmark/queries.py` — CANONICAL_QUERIES list (8 entries: 6 paragraph, 2 citation; 6 unfiltered, 2 filtered)
- `loaders/__init__.py` — BaseLoader ABC with `load(bundle: TalkBundle) -> None`
- `loaders/chromadb_loader.py` — ChromaDBLoader(host, port, embed_fn, batch_size)
- `loaders/weaviate_loader.py` — WeaviateLoader(host, port, embed_fn, batch_size)
- `loaders/qdrant_loader.py` — QdrantLoader(host, port, embed_fn, batch_size)
- `loaders/embeddings.py` — embed(text, model, url) -> list[float]
- `loaders/shared_transforms.py` — TalkBundle type alias

### Data Source (SQLite pipeline)
- `scripts/run_pipeline.py` — Source of `_get_all_gc_talk_ids()`, `process_talk_pipeline()`, `validate_talk()` — runner reuses these directly
- `extractors/pipeline.py` — `process_talk_pipeline()` implementation

### Prior Phase Context
- `.planning/phases/20-benchmark-infrastructure-framework/20-CONTEXT.md` — Metric dataclass field schemas (D-04 through D-07), canonical query design decisions
- `.planning/phases/21-db-loaders/21-CONTEXT.md` — Loader class design (D-01 through D-07), BaseLoader ABC, embedding helper location

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `loaders/__init__.py` `BaseLoader` ABC: Phase 22 runner type-hints `list[BaseLoader]` and iterates uniformly — `for loader in loaders: BenchmarkRunner(loader, ...).run_all()`
- `loaders/embeddings.py` `embed()`: Injected as `embed_fn` at `ChromaDBLoader(embed_fn=embed)` etc. — same pattern as Phase 21 loader tests
- `scripts/run_pipeline.py` `_get_all_gc_talk_ids()`: Returns list of int talk_ids ordered by SQLite primary key; runner slices to `--upsert-limit`
- `scripts/run_pipeline.py` `process_talk_pipeline()` + `validate_talk()`: Produces TalkBundle from SQLite per talk_id — exact same path runner uses
- `benchmark/queries.py` `CANONICAL_QUERIES`: 8 dicts with `query_text`, `k`, `collection`, `filter`; 6 have `filter: None` (unfiltered), 2 have non-None filter; runner segregates on `q["filter"] is None`

### Established Patterns
- **Loader constructor pattern**: `XLoader(host="localhost", port=N, embed_fn=embed, batch_size=100)` — runner instantiates all 3 with same signature
- **`dataclasses.asdict()`**: Used in `shared_transforms.py` for record preparation; Phase 22 uses same stdlib import for report serialization
- **`sys.path.append(str(Path(__file__).parent.parent))`**: Standard project import pattern — runner.py in `benchmark/` needs this
- **`pipenv run py`**: All Python commands use Python Launcher — test and run commands follow this
- **Docker ports**: ChromaDB :8000, Weaviate :8080, Qdrant :6333 (from `infra/docker-compose.vector-dbs.yml`)

### Integration Points
- Runner imports `BaseLoader` from `loaders` (for type hints) and each concrete loader by name
- Runner imports `CANONICAL_QUERIES` from `benchmark.queries`
- Runner imports all metric dataclasses from `benchmark.metrics` (including new `ScalabilityCurveEntry`)
- Runner imports `recall_at_k` from `benchmark.metrics`
- Runner imports `embed` from `loaders.embeddings`
- Runner calls `_get_all_gc_talk_ids()` from `scripts/run_pipeline` (or extracts to a shared util)
- `benchmark/results/` created with `mkdir -p` via `Path(args.output).mkdir(parents=True, exist_ok=True)`
- psutil added to Pipfile before runner can be executed

</code_context>

<specifics>
## Specific Ideas

- `BenchmarkRunner.__init__` signature: `(self, loader: BaseLoader, queries: list[dict], config: argparse.Namespace)`
- Report filename: `f"{db}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"` written to `args.output`
- `ScalabilityCurveEntry` location: `benchmark/metrics.py` alongside UpsertMetrics, QueryMetrics, etc.
- Memory polling thread: `threading.Thread(target=_poll_memory, args=(samples,), daemon=True)` — appends to a shared `samples: list[float]`; started before `ThreadPoolExecutor` submit loop, stopped (via event or join) after all futures resolve
- cold_warm ordering: SPEC Req 10 requires the cold query to be issued immediately after the load gate clears — `run_cold_warm()` must be the first method called after `run_upsert_phase()`, before any other query-issuing method

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 22-benchmark-runner*
*Context gathered: 2026-04-23*
