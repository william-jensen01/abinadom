# Phase 23: Benchmark Execution & Decision - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Run the full benchmark against all three vector DBs (ChromaDB, Weaviate, Qdrant), load all
5,838 GC talks into each DB, collect all 10 metric dimensions, and write a decision report
naming the winning DB with rationale. The decision report is the last artifact produced —
it is written only after real benchmark data is in hand.

Out of scope: embedding model evaluation (benchmarking different embedding models for
retrieval quality requires a separate phase with ground-truth labeling or LLM-as-judge
evaluation — a different project from benchmarking DB operational performance).

</domain>

<decisions>
## Implementation Decisions

### DB Reset (new --reset flag)
- **D-01:** Add a `--reset` flag to `benchmark/runner.py`. When `--reset` is passed, each
  targeted loader deletes and recreates its collections before the upsert phase starts.
  Reset scope matches the `--db` flag — if `--db all`, all three DBs are reset; if
  `--db weaviate`, only Weaviate is reset.
- **D-02:** Reset implementation: **delete then recreate** — call each DB's collection
  delete API, then let the loader's existing `__init__` / `_ensure_schema` path recreate
  collections via `get_or_create_collection` / `_ensure_schema()`. Same code path as a
  fresh stack. Do NOT attempt in-place record deletion.
- **D-03:** The official full run command is:
  `pipenv run py benchmark/runner.py --db all --reset --query-limit 500`
  (upsert-limit omitted → loads all talks; workers defaults to 4)

### Official Run Parameters
- **D-04:** Change `--upsert-limit` default from `100` to `None`. When `None`, no slice is
  applied to the talk_ids list (`all_ids[:]` or equivalent). Passing `--upsert-limit 100`
  still works for smoke tests. The runner help text should read "Load all talks if not
  specified."
- **D-05:** Official run uses `--query-limit 500` (500 timing samples per benchmark
  dimension). Provides stable p50/p95/p99 estimates — 500 samples / 8 canonical queries =
  ~62 cycles.
- **D-06:** `--workers` stays at 4 (current default, validated in smoke tests, unchanged).

### Recall@k Interpretation
- **D-07:** recall@k in the benchmark measures ANN fidelity (how closely each DB's
  approximate nearest neighbor results match ChromaDB's exact baseline), NOT retrieval
  quality. All three DBs use the same embedding model (nomic-embed-text via Ollama), so
  they compute identical vectors — recall@k differences reflect index approximation
  variation, not semantic quality differences. DECISION.md must frame recall@k honestly as
  a correctness/fidelity check, not a quality ranking.
- **D-08:** True retrieval quality evaluation would require benchmarking different embedding
  models with ground-truth labeling or LLM-as-judge evaluation. That is explicitly out of
  scope for Phase 23 and is a future phase concern.

### Winner Selection
- **D-09:** Winner is named only after the full benchmark data is in (not pre-selected from
  smoke test trends). The executor analyzes the JSON reports and names the winner.
- **D-10:** Decision framework: recall@k as a correctness gate (if a DB's ANN fidelity is
  significantly degraded, that's a disqualifier); operational performance — latency
  (p50/cold-start), upsert speed, memory delta, cold-start behavior — drives the winner
  among DBs that pass the correctness gate.
- **D-11:** Notable Qdrant cold-start anomaly from smoke tests (369ms cold query vs ~23ms
  warm, vs Weaviate's 65ms cold). The executor should investigate whether this persists in
  the full run and note it in DECISION.md if it does — a personal-use system restarts
  occasionally and first-query latency matters.

### Decision Report (benchmark/DECISION.md)
- **D-12:** Report lives at `benchmark/DECISION.md` (not `docs/benchmark/DECISION.md`).
- **D-13:** Format: **winner declared upfront** (clear recommendation at the top), followed
  by a structured comparison table (all metric dimensions × all 3 DBs, populated with real
  numbers from the JSON reports), followed by a narrative section per dimension and a
  rationale for the winner.
- **D-14:** Report is written by the **executor** after the full run completes, using real
  numbers from the JSON result files. No template or placeholder approach — the report is
  a final artifact, not a fill-in document.

### Claude's Discretion
- Exact wording of the recall@k framing in DECISION.md (as long as it honestly describes
  recall@k as a correctness check, not a quality ranking)
- Table layout and column ordering in DECISION.md
- Whether to include a "Production implications for Phase 24" section at the end of
  DECISION.md (noting any gotchas like Weaviate schema management or Qdrant cold-start)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Runner (primary target)
- `benchmark/runner.py` — CLI entrypoint; `_build_argparser()` (--upsert-limit, --workers,
  --db); `run_upsert_phase()` (upsert parallelism + load gate); `main()` (DB iteration)
- `benchmark/runner.py` lines 236–299 — `run_upsert_phase()` — where `talk_ids` slice
  happens (`all_ids[:self._config.upsert_limit]`); this is where None-handling is added
- `benchmark/runner.py` lines 689–710 — `_build_argparser()` — where `--upsert-limit`
  default changes from 100 → None

### Loaders (reset logic targets)
- `loaders/chromadb_loader.py` — `__init__` uses `get_or_create_collection`; reset means
  deleting all 4 collection names before init runs
- `loaders/weaviate_loader.py` — `_ensure_schema()` (line 72) uses `if not exists then
  create`; reset means deleting all 4 class names before `_ensure_schema` runs
- `loaders/qdrant_loader.py` — reset means deleting all 4 collection names before the
  loader's collection creation runs

### Existing benchmark results (smoke tests — for reference, not the official run)
- `benchmark/results/chroma_20260507_192533.json` — ChromaDB smoke test (100 records)
- `benchmark/results/weaviate_20260507_192606.json` — Weaviate smoke test; recall@k10=0.975
- `benchmark/results/qdrant_20260507_192657.json` — Qdrant smoke test; recall@k10=1.0,
  cold_ms=369 (anomaly to watch in full run)

### Requirements
- `.planning/REQUIREMENTS.md` — EVAL-02 through EVAL-05 are Phase 23's requirements
- `.planning/ROADMAP.md` § Phase 23 — Success criteria (4 items): single command, load
  gate, recall@k in report, written DECISION.md with winner

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `benchmark/runner.py` `_build_argparser()` — add `--reset` as a `store_true` flag
  alongside `--db`, `--upsert-limit`, etc.
- `loaders/chromadb_loader.py` `_client` — ChromaDB HttpClient; call
  `_client.delete_collection(name)` for each of the 4 CHROMADB_COLLECTION_NAMES keys
  to reset ChromaDB
- `loaders/weaviate_loader.py` `_client` — Weaviate client; call
  `_client.collections.delete(class_name)` for each of the 4 class names
- `loaders/qdrant_loader.py` `_client` — Qdrant client; call
  `_client.delete_collection(collection_name)` for each of the 4 collection names
- `main()` in runner — instantiates one `BenchmarkRunner` per DB; reset should happen
  before the loader is passed to `BenchmarkRunner`, or as a pre-flight step in `main()`

### Established Patterns
- `args.upsert_limit is None → use all_ids` (no slice) — `all_ids[:None]` works in Python
  but `None` as a default requires `type=int` to accept `None` (use `default=None` + no
  `type=int` restriction, or `type=lambda x: int(x) if x is not None else None`)
- All three loaders expose `_client` (or equivalent) as an instance variable — reset code
  can call delete methods directly on that client before `BenchmarkRunner.__init__`

### Integration Points
- Reset executes in `main()` before `BenchmarkRunner` is instantiated per DB — same place
  where loaders are built via `_build_loader(db_name, args)`
- Load gate (`run_upsert_phase` → `log "load gate cleared"`) must still fire before any
  query benchmarks; the reset doesn't change that ordering

</code_context>

<specifics>
## Specific Ideas

- Official full run command: `pipenv run py benchmark/runner.py --db all --reset --query-limit 500`
- `--upsert-limit` with `default=None`: the argparse `default=None` is already the Python
  default; just remove `default=100` and update the help string. Callers check
  `if args.upsert_limit is not None: talk_ids = all_ids[:args.upsert_limit]`
- DECISION.md winner section header: something like `## Decision: [Winner Name]` at the
  top, followed by `> **[Winner]** is selected for Phase 24 production migration.` and the
  rationale summary

</specifics>

<deferred>
## Deferred Ideas

- **Embedding model evaluation** — To measure true retrieval quality (not ANN fidelity),
  benchmark nomic-embed-text against mxbai-embed-large, all-minilm, etc. with ground-truth
  labeling or LLM-as-judge scoring. This is a separate future phase.

</deferred>

---

*Phase: 23-benchmark-execution-decision*
*Context gathered: 2026-05-07*
