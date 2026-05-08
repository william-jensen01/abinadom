---
phase: 23-benchmark-execution-decision
plan: 02
subsystem: database
tags: [weaviate, chromadb, qdrant, benchmark, vector-db, ann, recall]

# Dependency graph
requires:
  - phase: 23-benchmark-execution-decision
    plan: 01
    provides: "reset() classmethods, --reset flag, --upsert-limit default None enabling full 5,838-talk run"

provides:
  - "Three full-run benchmark JSON reports in benchmark/results/ (5,838 records each)"
  - "benchmark/DECISION.md naming Weaviate as winner with full metric comparison and rationale"

affects:
  - phase-24-vector-db-migration

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Benchmark decision report: winner declared upfront, comparison table with real numbers, per-dimension narrative, rationale, Phase 24 notes"
    - "ANN fidelity framing: recall@k as correctness check vs exact kNN baseline, not retrieval quality metric"

key-files:
  created:
    - benchmark/DECISION.md
    - benchmark/results/chroma_20260508_095938.json
    - benchmark/results/weaviate_20260508_102244.json
    - benchmark/results/qdrant_20260508_104734.json
  modified: []

key-decisions:
  - "Weaviate selected for Phase 24 production migration: serial p50 42ms (vs 51ms ChromaDB, 93ms Qdrant), filtered p50 51ms (4x faster than ChromaDB/Qdrant), cold-start 34ms (lowest), memory delta 0.02 MB (near-zero), concurrency throughput 214 q/s (highest), recall@k10=0.9875 (passes ANN fidelity gate)"
  - "Qdrant cold-start anomaly resolved: 369ms smoke test dropped to 115ms in full run; still 3.4x slower than Weaviate cold-start but acceptable for personal-use; not a disqualifier"
  - "All three DBs determinism=1.0 (identical result sets on repeated queries); not a differentiator"
  - "Filtered query performance is the decisive dimension for MCP use: Weaviate 51ms vs ChromaDB 220ms vs Qdrant 234ms"

patterns-established:
  - "Decision report pattern: winner upfront, 15-row comparison table with real numbers, 8 dimension narratives, rationale stating losses, Phase 24 operational notes"

requirements-completed:
  - EVAL-02
  - EVAL-03
  - EVAL-04
  - EVAL-05

# Metrics
duration: 30min
completed: 2026-05-08
---

# Phase 23 Plan 02: Benchmark Execution & Decision Summary

**Weaviate selected for Phase 24 production migration based on full 5,838-talk benchmark: serial p50 42ms, filtered p50 51ms (4x faster than ChromaDB/Qdrant), cold-start 34ms, near-zero memory overhead, and ANN fidelity recall@k10=0.9875**

## Performance

- **Duration:** ~30 min (writing DECISION.md + commits; full benchmark run was human-initiated Task 1)
- **Started:** 2026-05-08
- **Completed:** 2026-05-08
- **Tasks:** 1 (Task 2 — Task 1 was human-gated checkpoint, completed by developer)
- **Files modified:** 4 (DECISION.md + 3 JSON result files)

## Accomplishments

- Analyzed three full-run benchmark JSON reports (5,838 records each, all dimensions)
- Wrote benchmark/DECISION.md with real numbers: 15-row comparison table, 8 dimension narratives, rationale, Phase 24 notes
- Named Weaviate as winner based on data — decisive advantages in serial latency, filtered query latency, cold-start, memory, and throughput

## Task Commits

1. **chore(23-02): add full benchmark result files** — `d435cef`
2. **feat(23-02): write benchmark/DECISION.md with full-run results** — `0ecc95c`

## Files Created/Modified

- `benchmark/DECISION.md` — Decision report: Weaviate winner, comparison table, dimension analysis, rationale, Phase 24 notes
- `benchmark/results/chroma_20260508_095938.json` — ChromaDB full-run report (5,838 records, 1.06 rec/s, exact kNN baseline)
- `benchmark/results/weaviate_20260508_102244.json` — Weaviate full-run report (5,838 records, 4.41 rec/s, recall@k10=0.9875)
- `benchmark/results/qdrant_20260508_104734.json` — Qdrant full-run report (5,838 records, 4.38 rec/s, recall@k10=0.975)

## Decisions Made

Weaviate was selected over ChromaDB and Qdrant based on the following data-driven findings:

1. **Serial latency:** Weaviate p50=42ms, p95=51ms, p99=55ms — significantly better than ChromaDB (p50=51ms, p95/p99 around 220ms) and Qdrant (p50=93ms, p95/p99 around 235-243ms). Weaviate's p95 is lower than ChromaDB's p50.

2. **Filtered query latency (decisive for MCP):** Weaviate filtered p50=51ms vs ChromaDB 220ms and Qdrant 234ms. The MCP `search` tool uses metadata filters; this dimension is operationally critical.

3. **Cold-start:** Weaviate 34ms (essentially matching warm mean of 31ms). ChromaDB 64ms. Qdrant 115ms (improved from 369ms smoke test but still 3.4x Weaviate).

4. **Memory:** Weaviate near-zero delta during upsert (0.02 MB) vs ChromaDB 116 MB and Qdrant 70 MB. Significant for a machine also running Ollama.

5. **Upsert speed:** Weaviate 4.41 rec/s vs ChromaDB 1.06 rec/s (4.2x faster for production migration).

6. **ANN fidelity:** Both Weaviate (0.9875) and Qdrant (0.975) pass the recall gate; not a differentiator. ChromaDB is the exact kNN baseline.

## Deviations from Plan

None — plan executed exactly as written. Task 2 followed the spec in 23-02-PLAN.md: read JSON files, analyze data, write DECISION.md with all required sections and real numbers.

## Issues Encountered

None. The Qdrant cold-start anomaly (369ms in smoke tests) was resolved in the full run (115ms) — this was noted and addressed in DECISION.md per D-11 requirements.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Phase 24 (Vector DB Migration) is ready to begin. Key inputs:

- Winner: **Weaviate**
- Loader: `loaders/weaviate_loader.py` — validated, 4 collections, schema defined
- Migration path documented in `benchmark/DECISION.md` Phase 24 Notes section
- Schema management note: collection recreation required for adding new properties (finalize schema before migration)
- Upsert path: `benchmark/runner.py --db weaviate --reset` against production Docker instance is the simplest migration approach
- Docker: `infra/docker-compose.vector-dbs.yml` Weaviate service definition is the starting point for `docker-compose.yml` integration

---
*Phase: 23-benchmark-execution-decision*
*Completed: 2026-05-08*
