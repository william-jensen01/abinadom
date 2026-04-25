---
phase: 22-benchmark-runner
fixed_at: 2026-04-25T08:07:19Z
review_path: .planning/phases/22-benchmark-runner/22-REVIEW.md
iteration: 1
fix_scope: critical_warning
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 22: Code Review Fix Report

**Fixed at:** 2026-04-25T08:07:19Z
**Source review:** `.planning/phases/22-benchmark-runner/22-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 11
- Fixed: 11
- Skipped: 0

## Fixed Issues

### CR-01: Percentile computation is systematically wrong (floor vs. ceiling)

**Files modified:** `benchmark/runner.py`
**Commit:** cec0c33
**Applied fix:** Added `import math` and replaced `int(p / 100 * n)` with `max(0, math.ceil(p / 100.0 * n) - 1)` in the inner `percentile()` function. This implements the correct nearest-rank formula: rank = ceil(p/100 * n), then subtract 1 for 0-based indexing.

---

### CR-02: Variable `k` (parameter) is shadowed inside filter list comprehension in `WeaviateLoader.query`

**Files modified:** `loaders/weaviate_loader.py`
**Commit:** 316a798
**Applied fix:** Renamed the list comprehension loop variable from `k` to `prop` (`for prop, v in filter.items()`) so it no longer shadows the outer `k` (result count) parameter.

---

### CR-03: `QdrantLoader` never closes its client connection

**Files modified:** `loaders/qdrant_loader.py`
**Commit:** bf82706
**Applied fix:** Added `close()` method override to `QdrantLoader` that calls `self._client.close()`. Also fixed a parallel `k` variable shadowing issue in `QdrantLoader.query` (loop variable renamed from `k` to `field`).

---

### CR-04: `_collect_chroma_baseline` leaks a `ChromaDBLoader` connection

**Files modified:** `benchmark/runner.py`
**Commit:** 226cff0
**Applied fix:** Wrapped the query loop in an inner `try/finally` block that calls `chroma.close()` unconditionally after all queries complete, before the outer exception handler can catch any failure from construction. Structure is: outer try (construct client) → inner try (run queries) → inner finally (close client) → outer except (log warning, return None).

---

### WR-01: `run_serial_latency` falsely inflates `failed_queries` on legitimate empty results

**Files modified:** `benchmark/runner.py`
**Commit:** 81ced59
**Applied fix:** Changed `_query_db` return type to `list[str] | None`. Now returns `None` on exception and `[]` for a valid empty result set. Updated all callers: `run_serial_latency`, `run_filtered_unfiltered._run_group` now check `if ids is None` instead of `if not ids`. `run_determinism` uses `set(ids) if ids is not None else set()`. `run_recall` uses `self._query_db(q) or []` to treat None as empty for recall computation.

---

### WR-02: `_finalize_memory_upsert` measures post-upsert RSS, not peak RSS during upsert

**Files modified:** `benchmark/runner.py`
**Commit:** ef5a05b
**Applied fix:** Refactored `run_memory_upsert()` to start a background polling thread (same pattern as `run_memory_query`) before the upsert begins. `_finalize_memory_upsert()` now stops the poller and uses `max(samples)` to report the true peak RSS observed during the upsert, rather than a point-in-time snapshot taken after OS memory may have been reclaimed.

---

### WR-03: `recall_at_k` docstring contradicts its implementation

**Files modified:** `benchmark/metrics.py`
**Commit:** 85dbc9f
**Applied fix:** Updated the docstring to accurately describe the division-by-k formula with the formal notation `|baseline_ids[:k] ∩ candidate_ids[:k]| / k`, and added a note explaining that when `baseline_ids` has fewer than k elements, the maximum achievable score is `len(baseline_ids) / k (< 1.0)`.

---

### WR-04: `run_recall` k50 baseline truncation logic is misleading

**Files modified:** `benchmark/runner.py`
**Commit:** c8ef0ab
**Applied fix:** Removed the redundant `baseline_ids[:50] if len(baseline_ids) >= 50 else baseline_ids` conditional (it was a no-op since `recall_at_k` already handles truncation internally). Replaced with a `logger.debug` call when `len(baseline_ids) < 50`, making sparse baselines visible in debug logs. The `recall_at_k` call now passes `baseline_ids` directly.

---

### WR-05: `run_filtered_unfiltered` produces a zero-count metrics block with no signal when no filtered queries exist

**Files modified:** `benchmark/runner.py`
**Commit:** 21fda0f
**Applied fix:** Added guards so `_run_group` is only called when the group is non-empty. Empty groups store `None` instead of a zeroed `QueryMetrics` dict. The log line uses conditional access (`uf_metrics.query_count if uf_metrics else 0`) to remain valid.

---

### WR-06: `BaseLoader` ABC does not declare `query()` as abstract

**Files modified:** `loaders/__init__.py`
**Commit:** 67a4192
**Applied fix:** Added `@abstractmethod` decorated `query()` method to `BaseLoader` with the correct signature matching all three concrete loader implementations: `(self, collection: str, query_text: str, k: int, filter: dict | None = None) -> list[str]`.

---

### WR-07: `_poll_memory` appends RSS bytes to a `list[float]` but RSS is in bytes (int)

**Files modified:** `benchmark/runner.py`
**Commit:** e631ae9
**Applied fix:** Changed the `_poll_memory` function signature from `samples: list[float]` to `samples: list[int]` and added a docstring note that values are RSS bytes. Updated both caller sites (`run_memory_query` and `run_memory_upsert`) to declare their sample lists as `list[int]` with an inline comment `# RSS in bytes`.

---

_Fixed: 2026-04-25T08:07:19Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
