---
phase: 22-benchmark-runner
plan: "03"
subsystem: benchmark
tags: [benchmark, runner, argparse, cli, json-report, multi-db, orchestration]

requires:
  - phase: 22-benchmark-runner plan 02
    provides: BenchmarkRunner class with all 10 measurement methods in benchmark/runner.py
  - phase: 22-benchmark-runner plan 01
    provides: psutil, ScalabilityCurveEntry, benchmark/metrics.py, benchmark/queries.py

provides:
  - run_all() method on BenchmarkRunner — sequences all 10 benchmark dimensions in SPEC-locked order
  - _write_report() — writes {db}_{YYYYMMDD_HHMMSS}.json to --output dir (mkdir -p)
  - _build_loader() — instantiates ChromaDBLoader/WeaviateLoader/QdrantLoader with Docker ports
  - _collect_chroma_baseline() — queries ChromaDB for top-50 IDs per query; None if unreachable
  - _build_argparser() — CLI with --db, --upsert-limit, --query-limit, --workers, --output
  - main() — multi-DB orchestration loop with ordering, error handling, exit codes
  - `pipenv run py benchmark/runner.py --help` exits 0

affects:
  - Phase 23 (decision report) — consumes JSON output files written to benchmark/results/
  - infra/docker-compose.vector-dbs.yml — runner targets these container ports

tech-stack:
  added: []
  patterns:
    - "argparse.ArgumentDefaultsHelpFormatter for self-documenting --help output"
    - "try/except _build_loader + try/finally loader.close() per DB in main() loop"
    - "chroma_baseline collected once before Weaviate/Qdrant runs (recall@k ground truth)"
    - "had_failure flag + sys.exit(1) for partial-failure non-zero exit on --db all"

key-files:
  created: []
  modified:
    - benchmark/runner.py

key-decisions:
  - "run_all() calls run_cold_warm() as FIRST query-issuing method after run_upsert_phase() (SPEC Req 10 ordering)"
  - "main() collects chroma_baseline once before iterating Weaviate/Qdrant (D-04 — ChromaDB first)"
  - "ChromaDB passed baseline=None in main() loop since it IS the baseline (SPEC Req 12)"
  - "loader.close() in finally block after each DB run (WeaviateLoader resource cleanup)"
  - "had_failure flag accumulates per-DB failures; sys.exit(1) only after all DBs attempted (D-03)"
  - "Ollama ping at startup before any DB work to fail-fast (T-22-03-02)"

patterns-established:
  - "_collect_chroma_baseline() returns None on any exception — no crash, WARNING log, recall=null downstream"
  - "Worktree pipenv installs fresh virtualenv — run `pipenv install` before any pipenv run commands"

requirements-completed:
  - BENCH-07

duration: 6min
completed: "2026-04-24"
---

# Phase 22 Plan 03: CLI Entrypoint and Multi-DB Orchestration Summary

**Full CLI entrypoint wiring benchmark/runner.py: argparse with 5 args, run_all() 10-step sequencer, _write_report() JSON output, multi-DB main() loop with chroma-first ordering and non-zero partial-failure exit codes.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-24T22:03:39Z
- **Completed:** 2026-04-24T22:09:38Z
- **Tasks:** 2 of 3 (Task 3 is a checkpoint:human-verify — execution paused)
- **Files modified:** 1

## Accomplishments

- Added `run_all()` method to BenchmarkRunner with SPEC-locked 10-step ordering (cold/warm is first query call after load gate, scalability before memory_query, latency_under_load reads from scalability_curve)
- Added complete CLI via `_build_argparser()` with `--db` (default all), `--upsert-limit` (100), `--query-limit` (100), `--workers` (10), `--output` (benchmark/results/); `--help` exits 0
- Added `main()` with: Ollama reachability gate at startup, chroma-first ordering for `--db all`, recall@k baseline collected once before Weaviate/Qdrant runs, try/finally loader.close(), had_failure + sys.exit(1) for partial failures
- Added `_write_report()` with mkdir -p, timestamp filename, json.dump indent=2
- Added `_build_loader()` with Docker-default ports (chroma:8000, weaviate:8080, qdrant:6333)
- Added `_collect_chroma_baseline()` with graceful None return when ChromaDB unreachable

## Task Commits

Each task was committed atomically:

1. **Task 1: Add run_all() method to BenchmarkRunner** - `eebfb54` (feat)
2. **Task 2: Add argparse, _write_report(), _build_loader(), _collect_chroma_baseline(), main()** - `81ebb42` (feat)

_Task 3 is a checkpoint:human-verify — awaiting user verification before continuation._

## Files Created/Modified

- `benchmark/runner.py` — Added run_all() method (50 lines) + 5 module-level functions + main() + entry point (~178 lines)

## Decisions Made

- `run_all()` uses `"dict[str, list[str]] | None"` as string annotations instead of `from __future__ import annotations` to maintain compatibility with the existing file pattern
- `chroma_baseline` type annotation in `main()` uses string form for the same reason
- Ollama ping uses `embed("hello", model="nomic-embed-text")` — simplest check that the embedding path works end-to-end before any DB work
- `_collect_chroma_baseline()` catches outer instantiation errors and inner query errors separately — outer returns None (unreachable), inner logs WARNING per query and continues (partial baseline)

## Deviations from Plan

None - plan executed exactly as written. All function signatures, logic, and ordering match the plan specification.

## Issues Encountered

**Worktree fresh virtualenv:** The worktree created a new virtualenv with no packages installed. Running `pipenv install` resolved this before verification. This is expected worktree behavior, not a code issue.

## Known Stubs

None — no placeholder values, hardcoded empty returns, or mock data. All functions are fully implemented.

## Threat Surface Scan

No new network endpoints or auth paths introduced. `main()` opens outbound connections to local Docker containers (already established in prior plans). `_write_report()` writes to a user-specified local directory (T-22-03-04: PermissionError surfaces naturally as an OS error). No new trust boundaries.

All T-22-03-xx mitigations from the plan's threat register are present:
- T-22-03-01: run_upsert_phase skips gracefully (from Plan 02)
- T-22-03-02: embed("hello") ping at main() startup before any DB work
- T-22-03-03: _build_loader() wrapped in try/except; had_failure + sys.exit(1)
- T-22-03-04: Path.mkdir(parents=True, exist_ok=True) — PermissionError surfaces as OS error
- T-22-03-06: _collect_chroma_baseline() returns None; run_recall(None) sets recall=null; exit 0

## Next Phase Readiness

- `benchmark/runner.py` is complete and runnable; `--help` passes
- Task 3 (checkpoint:human-verify) requires user to run smoke tests (help check + import checks)
- After checkpoint approval: Phase 22 plan 03 is done; Phase 23 (decision report) can begin using JSON output files

## Self-Check: PASSED

- `benchmark/runner.py` exists: confirmed
- `eebfb54` commit exists in git log: confirmed
- `81ebb42` commit exists in git log: confirmed
- `def run_all(` present in file: confirmed (line ~470)
- `def main() -> None:` present in file: confirmed (line 621)
- `def _write_report(` present in file: confirmed
- `def _build_loader(` present in file: confirmed
- `def _collect_chroma_baseline(` present in file: confirmed
- `def _build_argparser(` present in file: confirmed
- `if __name__ == "__main__":` present in file: confirmed
- `loader.close()` in finally block: confirmed (line 689)
- `mkdir(parents=True, exist_ok=True)` present: confirmed
- `["chroma", "weaviate", "qdrant"]` ordering literal: confirmed
- `json.dump(report, f, indent=2)` present: confirmed
- `sys.exit(1)` present: confirmed
- `pipenv run py benchmark/runner.py --help` exits 0: confirmed

---
*Phase: 22-benchmark-runner*
*Completed: 2026-04-24*
