---
phase: 20-benchmark-infrastructure-framework
plan: "03"
subsystem: benchmark
tags: [benchmark, metrics, dataclasses, recall, canonical-queries]
dependency_graph:
  requires: ["20-01"]
  provides: ["benchmark.metrics", "benchmark.queries", "recall_at_k", "CANONICAL_QUERIES"]
  affects: ["Phase 22 runner", "benchmark loaders"]
tech_stack:
  added: []
  patterns: ["@dataclass with default-last field ordering", "set-intersection recall formula"]
key_files:
  created:
    - benchmark/metrics.py
    - benchmark/queries.py
  modified:
    - tests/test_metrics.py
decisions:
  - "recall_at_k uses set intersection / k — matches SPEC proof and handles k=0 with guard clause"
  - "CANONICAL_QUERIES uses 8 entries (6 paragraph, 2 citation) — exceeds minimum of 7"
  - "filter=None entries use explicit None value (not omitted key) for consistent schema"
metrics:
  duration_seconds: 345
  completed_date: "2026-04-20"
  tasks_completed: 2
  files_created: 2
  files_modified: 1
requirements:
  - BENCH-05
  - BENCH-06
---

# Phase 20 Plan 03: Benchmark Metrics and Canonical Queries Summary

**One-liner:** Four typed metric dataclasses (Upsert/Query/Concurrency/Memory) plus recall_at_k and an 8-entry CANONICAL_QUERIES workload covering all required doctrinal themes and citation filters.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Create benchmark/metrics.py | 0ce78ce | benchmark/metrics.py, tests/test_metrics.py |
| 2 | Create benchmark/queries.py | eb9291a | benchmark/queries.py |

## Verification Results

All 5 plan verification steps passed:

1. `from benchmark.metrics import UpsertMetrics, QueryMetrics, ConcurrencyMetrics, MemoryMetrics, recall_at_k` — OK
2. `recall_at_k(["a","b","c"], ["a","c","d"], k=3)` — `0.6666666666666666` (matches SPEC)
3. `len(CANONICAL_QUERIES)` — `8` (exceeds minimum of 7)
4. `pipenv run py -m pytest tests/test_metrics.py -x -q` — 17 passed
5. `grep '"book_name": "John"' benchmark/queries.py` — match found (D-10 satisfied)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed AttributeError in test_has_john_filter**

- **Found during:** Task 2 verification (test run)
- **Issue:** `q.get("filter", {}).get("book_name")` raises `AttributeError: 'NoneType' has no attribute 'get'` when a CANONICAL_QUERIES entry has `"filter": None`. The key is present in the dict with value `None`, so `.get("filter", {})` returns the actual `None` value (not the `{}` default), then `.get("book_name")` fails on `None`.
- **Fix:** Changed to `(q.get("filter") or {}).get("book_name")` — the `or {}` handles `None` correctly.
- **Files modified:** `tests/test_metrics.py` (line 176)
- **Commit:** `0ce78ce` (bundled with Task 1 metrics implementation)

## Threat Model Coverage

| Threat ID | Status | Notes |
|-----------|--------|-------|
| T-20-03-01 | Mitigated | `if k == 0: return 0.0` guard clause present; covered by `TestRecallAtK.test_k_zero_returns_zero` |
| T-20-03-02 | Accepted | Static local dev data; no PII or secrets |

## Known Stubs

None — both modules are fully implemented with no placeholder values or hardcoded empty data that flows to rendering.

## Self-Check: PASSED

- `benchmark/metrics.py` exists: FOUND
- `benchmark/queries.py` exists: FOUND
- Commit `0ce78ce` exists: FOUND
- Commit `eb9291a` exists: FOUND
- 17 tests GREEN: CONFIRMED
