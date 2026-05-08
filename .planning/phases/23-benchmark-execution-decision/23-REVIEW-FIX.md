---
phase: 23-benchmark-execution-decision
fixed_at: 2026-05-08T00:00:00Z
review_path: .planning/phases/23-benchmark-execution-decision/23-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 23: Code Review Fix Report

**Fixed at:** 2026-05-08T00:00:00Z
**Source review:** .planning/phases/23-benchmark-execution-decision/23-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: chromadb_loader reset() selective exception handling

**Files modified:** `loaders/chromadb_loader.py`
**Commit:** 10ba7ff
**Applied fix:** The inner `except Exception` in the `for name in CHROMADB_COLLECTION_NAMES.values()` loop now inspects the error string before deciding to swallow it. Errors whose string representation contains "not found", "does not exist", or "404" are treated as NotFound and logged at DEBUG. All other exceptions (connection errors, auth failures, etc.) are re-raised so the outer `except` in `main()` can abort the DB rather than silently proceeding with a stale collection.

Note: WR-02 (the `finally: client.close()` bare pass) was addressed in the same commit since it is in the same method.

---

### WR-01: runner.py --workers default changed to 10

**Files modified:** `benchmark/runner.py`
**Commit:** 9398132
**Applied fix:** Changed `default=4` to `default=10` and updated the help string from "Default 4." to "Default 10." in the `--workers` argument definition. This aligns the default with the scalability curve levels `[1, 5, 10, 20]` so that the default run computes `latency_degradation_ratio` against the 10-worker curve entry rather than falling back to the 20-worker entry.

---

### WR-02: chromadb_loader reset() finally block logs close failure

**Files modified:** `loaders/chromadb_loader.py`
**Commit:** 10ba7ff (same commit as CR-01)
**Applied fix:** Changed the `finally` block from bare `except Exception: pass` to `except Exception as e: logger.warning("ChromaDB reset: failed to close client: %s", e)`. This mirrors the pattern used in the `close()` instance method and ensures resource-warning-level errors from chromadb HTTP sessions are visible during benchmark reset.

---

### WR-03: _collect_chroma_baseline() guards against all-empty results

**Files modified:** `benchmark/runner.py`
**Commit:** 4f12fe8
**Applied fix:** After all per-query baseline IDs are collected, `sum(len(ids) for ids in baseline.values())` counts total results. If the total is 0, a WARNING is logged ("ChromaDB baseline returned 0 results across all queries — collection may be empty. Recall will be null.") and the function returns `None`. This prevents Weaviate/Qdrant recall scores from being reported as 0.0 with no diagnostic context when the ChromaDB collection was silently recreated empty between the benchmark run and baseline collection.

---

_Fixed: 2026-05-08T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
