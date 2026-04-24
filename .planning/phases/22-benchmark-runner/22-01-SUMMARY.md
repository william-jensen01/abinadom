---
phase: 22-benchmark-runner
plan: "01"
subsystem: benchmark
tags: [dependencies, dataclasses, metrics, psutil]
dependency_graph:
  requires: []
  provides:
    - psutil installed in pipenv virtualenv
    - ScalabilityCurveEntry dataclass in benchmark/metrics.py
  affects:
    - benchmark/runner.py (Plan 02 — consumes ScalabilityCurveEntry and psutil)
tech_stack:
  added:
    - psutil 7.2.2 (RSS memory measurement)
  patterns:
    - "@dataclass with typed fields matching SPEC schema (D-09)"
key_files:
  created: []
  modified:
    - Pipfile
    - Pipfile.lock
    - benchmark/metrics.py
decisions:
  - "Used wildcard psutil = \"*\" consistent with tqdm and fastmcp unpinned packages"
  - "ScalabilityCurveEntry placed after MemoryMetrics and before recall_at_k per plan spec"
metrics:
  duration_seconds: 785
  completed: "2026-04-24T08:35:53Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
requirements_satisfied:
  - BENCH-07
---

# Phase 22 Plan 01: psutil + ScalabilityCurveEntry Prerequisites Summary

**One-liner:** psutil 7.2.2 added to Pipfile and ScalabilityCurveEntry dataclass (5 fields) added to benchmark/metrics.py as hard prerequisites for benchmark/runner.py (Plan 02).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add psutil to Pipfile | f85ba42 | Pipfile, Pipfile.lock |
| 2 | Add ScalabilityCurveEntry to benchmark/metrics.py | 8ca330f | benchmark/metrics.py |

## What Was Built

**Task 1 — psutil dependency:**
- Added `psutil = "*"` to the `[packages]` block of Pipfile, immediately after the `fastmcp = "*"` line
- Ran `pipenv install` which created a fresh virtualenv for the worktree and installed all packages including psutil 7.2.2
- Verified: `pipenv run py -c "import psutil; print(psutil.__version__)"` prints `7.2.2`

**Task 2 — ScalabilityCurveEntry dataclass:**
- Inserted the new dataclass after `MemoryMetrics` and before `recall_at_k()` in `benchmark/metrics.py`
- Five typed fields exactly matching SPEC Req 7 and D-09: `workers: int`, `throughput_qps: float`, `p50_ms: float`, `p95_ms: float`, `p99_ms: float`
- Verified instantiation and field inspection
- All 17 existing `tests/test_metrics.py` tests pass with no regressions

## Verification Results

1. `pipenv run py -c "import psutil; print(psutil.__version__)"` — exits 0, printed `7.2.2`
2. `pipenv run py -c "from benchmark.metrics import ScalabilityCurveEntry; import dataclasses; print(dataclasses.fields(ScalabilityCurveEntry))"` — exits 0, printed all 5 fields
3. `pipenv run py -m pytest tests/test_metrics.py -v` — 17 passed, 0 failed

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — no placeholder values or mock data introduced.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries. The psutil package reads local process memory (RSS) only — no network I/O. No threat flags raised.

## Self-Check: PASSED

- Pipfile contains `psutil = "*"`: confirmed (line 17)
- benchmark/metrics.py contains `class ScalabilityCurveEntry:`: confirmed (line 55)
- Commit f85ba42 exists: confirmed
- Commit 8ca330f exists: confirmed
- ScalabilityCurveEntry is after MemoryMetrics (line 54) and before recall_at_k (line 65): confirmed
- All 17 metrics tests pass: confirmed
