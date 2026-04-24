---
phase: 22-benchmark-runner
reviewed: 2026-04-24T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - benchmark/metrics.py
  - benchmark/runner.py
  - loaders/chromadb_loader.py
  - loaders/weaviate_loader.py
  - loaders/qdrant_loader.py
findings:
  critical: 4
  warning: 7
  info: 1
  total: 12
status: issues_found
---

# Phase 22: Code Review Report

**Reviewed:** 2026-04-24T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed five files implementing the Phase 22 benchmark runner: the metrics dataclasses/recall function, the orchestrating `BenchmarkRunner` class, and three vector-DB-specific loaders. The code is well-structured overall, with clear docstrings and a sensible layering. However, several correctness defects were found:

- The percentile function produces systematically wrong percentile values due to a floor-vs-ceiling indexing error.
- A variable-shadowing bug in `WeaviateLoader.query` silently overwrites the `k` parameter inside a list comprehension, making the code brittle and hard to debug.
- `QdrantLoader` never closes its gRPC/HTTP connection (missing `close()` override), leaking a connection per benchmark run.
- A resource leak exists in `_collect_chroma_baseline`: a `ChromaDBLoader` is constructed and never closed.
- The `run_serial_latency` failure counter is inflated by legitimate empty results, producing misleading `failed_queries` values in the JSON report.

---

## Critical Issues

### CR-01: Percentile computation is systematically wrong (floor vs. ceiling)

**File:** `benchmark/runner.py:78-79`

**Issue:** The inner `percentile()` function uses `int(p / 100 * n)` (floor) to compute the index. For standard nearest-rank percentile, the correct index for the p-th percentile over n samples is `ceil((p / 100) * n) - 1` (0-based). Using floor gives a lower element than expected:

- p50, n=2: `int(0.5 * 2) = 1` — returns the *maximum* of the two values, not the median.
- p95, n=100: `int(0.95 * 100) = 95` — returns `sorted_lat[95]`, which is actually the 96th smallest value (0-indexed), off by one.
- p99, n=100: `int(0.99 * 100) = 99` — returns the maximum, which is also only accidentally correct here.

The p50 case for small sample counts (≤2) is the most damaging: it will always report the maximum value as p50, making the serial latency metric appear worse than it is and distorting the `latency_degradation_ratio` in `run_latency_under_load`.

**Fix:**
```python
import math

def percentile(p: float) -> float:
    # Nearest-rank (1-based): rank = ceil(p/100 * n), then convert to 0-based index
    idx = max(0, math.ceil(p / 100.0 * n) - 1)
    return sorted_lat[idx]
```

---

### CR-02: Variable `k` (parameter) is shadowed inside filter list comprehension in `WeaviateLoader.query`

**File:** `loaders/weaviate_loader.py:288`

**Issue:** The method signature is `query(self, collection, query_text, k, filter)`. On line 284, `kwargs["limit"] = k` is set correctly. However, on line 288:

```python
conditions = [Filter.by_property(k).equal(v) for k, v in filter.items()]
```

The loop variable `k` inside the list comprehension shadows the outer `k` parameter for the duration of the comprehension. In Python 3, list comprehension variables do **not** leak into the enclosing scope, so the outer `k` is restored after the comprehension — but this is a well-known readability trap. More critically, `Filter.by_property(k)` on line 288 passes the *filter key string* (e.g., `"book_name"`) to `by_property()`, which is intended. However, the shadowing means any future use of `k` (the result count) after line 288 within the same method would silently get the filter key instead of the integer. This has already caused the `near_vector` call on line 298 to receive an unintended `limit` only because `limit` was set before the comprehension.

**Fix:** Rename the comprehension loop variable to avoid shadowing:
```python
conditions = [Filter.by_property(prop).equal(v) for prop, v in filter.items()]
```

---

### CR-03: `QdrantLoader` never closes its client connection

**File:** `loaders/qdrant_loader.py` (entire class)

**Issue:** `QdrantClient` (from `qdrant-client`) holds an internal connection to the Qdrant gRPC/REST endpoint. The `BaseLoader` base class provides a no-op `close()`. `QdrantLoader` does not override `close()`. The runner's `main()` function calls `loader.close()` in a `finally` block (runner.py:688), which silently does nothing for Qdrant. When benchmarking all three DBs, the Qdrant client connection is leaked for the entire process lifetime.

Compare: `WeaviateLoader` correctly overrides `close()` to call `self._client.close()` (weaviate_loader.py:310).

**Fix:**
```python
def close(self) -> None:
    """Close the Qdrant client and release its underlying connection."""
    self._client.close()
```

Add this method to `QdrantLoader`, after the `query()` method.

---

### CR-04: `_collect_chroma_baseline` leaks a `ChromaDBLoader` connection

**File:** `benchmark/runner.py:561-578`

**Issue:** `_collect_chroma_baseline` instantiates a `ChromaDBLoader` on line 561:

```python
chroma = ChromaDBLoader(host="localhost", port=8000, embed_fn=embed, batch_size=100)
```

`ChromaDBLoader.__init__` calls `chromadb.HttpClient(...)`, which opens an HTTP connection pool. The function never calls `chroma.close()` (which is a no-op anyway for `ChromaDBLoader`, but structurally the pattern is wrong). If `ChromaDBLoader` is later updated to manage explicit connections, this will become a leak. More importantly, when `--db all` is used, `ChromaDB` is *also* loaded as a primary DB via `_build_loader`, creating two separate clients to the same endpoint. There is no client sharing or reuse.

This is lower severity than CR-03 because `chromadb.HttpClient` is a lightweight HTTP client, but the pattern is still incorrect and should be fixed by wrapping in `try/finally` or using `ChromaDBLoader` as a context manager if one is added.

**Fix:**
```python
def _collect_chroma_baseline(queries: list[dict[str, Any]]) -> "dict[str, list[str]] | None":
    try:
        chroma = ChromaDBLoader(host="localhost", port=8000, embed_fn=embed, batch_size=100)
        try:
            baseline: dict[str, list[str]] = {}
            for q in queries:
                try:
                    ids = chroma.query(...)
                    baseline[q["query_text"]] = ids
                except Exception as e:
                    logger.warning(...)
                    baseline[q["query_text"]] = []
            return baseline
        finally:
            chroma.close()
    except Exception as e:
        logger.warning(...)
        return None
```

---

## Warnings

### WR-01: `run_serial_latency` falsely inflates `failed_queries` on legitimate empty results

**File:** `benchmark/runner.py:277-281`

**Issue:** The failure counter is incremented whenever `_query_db()` returns `[]`:

```python
ids = self._query_db(q)
latencies.append((time.monotonic() - t0) * 1000.0)
if not ids:
    failed += 1
```

`_query_db()` returns `[]` both when an exception occurs (genuine failure) AND when the query succeeds but the collection has no matching results (valid empty result set). The same false-positive pattern exists in `run_filtered_unfiltered`. This inflates `QueryMetrics.failed_queries` in the JSON report, making a DB with sparse data appear unreliable.

**Fix:** Track failures separately from empty results. `_query_db` should return a sentinel (e.g., `None`) on failure, and `[]` for a successful empty result:
```python
def _query_db(self, query: dict[str, Any]) -> list[str] | None:
    try:
        return self._loader.query(...)
    except Exception as e:
        logger.warning(...)
        return None  # None = failure, [] = valid empty result
```
Then callers check `if ids is None: failed += 1`.

---

### WR-02: `_finalize_memory_upsert` measures post-upsert RSS, not peak RSS during upsert

**File:** `benchmark/runner.py:189-198`

**Issue:** `run_memory_upsert()` captures a baseline RSS before the upsert loop. `_finalize_memory_upsert()` captures the current RSS *after* the upsert loop completes. If the Python allocator or the OS reclaimed memory (via GC or heap trimming) during or after the upsert, the measured peak will be lower than the actual peak — potentially returning a negative `delta_mb`. By contrast, `run_memory_query` correctly uses a background polling thread to track the peak RSS continuously.

**Fix:** Apply the same background-polling approach from `run_memory_query` to the upsert phase:
```python
def run_memory_upsert(self) -> None:
    self._mem_upsert_baseline_bytes = psutil.Process().memory_info().rss
    self._mem_upsert_samples: list[float] = []
    self._mem_upsert_stop = threading.Event()
    self._mem_poller = threading.Thread(
        target=_poll_memory, args=(self._mem_upsert_samples, self._mem_upsert_stop), daemon=True
    )
    self._mem_poller.start()

def _finalize_memory_upsert(self) -> None:
    self._mem_upsert_stop.set()
    self._mem_poller.join(timeout=1.0)
    baseline_mb = self._mem_upsert_baseline_bytes / 1024**2
    peak_bytes = max(self._mem_upsert_samples) if self._mem_upsert_samples else self._mem_upsert_baseline_bytes
    peak_mb = peak_bytes / 1024**2
    self.results["memory_upsert"] = asdict(MemoryMetrics(...))
```

---

### WR-03: `recall_at_k` docstring contradicts its implementation

**File:** `benchmark/metrics.py:65-82`

**Issue:** The docstring states: *"fraction of baseline_ids[:k] that appear in candidate_ids[:k]"*. This implies the denominator should be `len(baseline_set)` (i.e., how many of the ground-truth top-k were recalled). However, the code divides by `k`:

```python
return len(baseline_set & candidate_set) / k
```

These two formulations are identical only when `len(baseline_ids) >= k`. If `baseline_ids` has fewer than `k` elements (e.g., a sparse collection returns fewer than 10 results for a given query), `baseline_set` will have fewer than `k` elements, but the denominator is still `k` — capping the achievable recall below 1.0 even when the candidate perfectly matches the baseline. This is the standard definition of recall@k in IR literature, so the code is arguably correct, but the docstring misleads callers into thinking perfect overlap always yields 1.0.

**Fix:** Align the docstring to the actual behavior:
```python
"""
Compute recall@k: fraction k that appear in both baseline_ids[:k] and candidate_ids[:k].

Formally: |baseline_ids[:k] ∩ candidate_ids[:k]| / k

Note: if baseline_ids has fewer than k elements, the maximum achievable score
is len(baseline_ids) / k (< 1.0), not 1.0.
"""
```

---

### WR-04: `run_recall` k50 baseline truncation logic is misleading

**File:** `benchmark/runner.py:462-463`

**Issue:**
```python
baseline_ids_50 = baseline_ids[:50] if len(baseline_ids) >= 50 else baseline_ids
k50_scores.append(recall_at_k(baseline_ids_50, candidate_ids_50, k=50))
```

`baseline_ids` comes from `_collect_chroma_baseline`, which queries ChromaDB with `k=50`, so it will contain at most 50 results. The conditional `if len(baseline_ids) >= 50 else baseline_ids` is effectively always taking the `else` branch (when baseline has exactly 50, `[:50]` is a no-op copy; when it has fewer, the full list is used). The intent seems to be to handle the case where baseline has fewer than 50 items — but `recall_at_k` already handles this via its `baseline_set = set(baseline_ids[:k])` slicing, so the truncation here is redundant and the comment/conditional misleads readers into thinking there's meaningful handling happening. More importantly, when `len(baseline_ids) < 50`, `recall_at_k` is still called with `k=50`, making perfect recall unreachable (see WR-03), but no warning is logged.

**Fix:** Remove the redundant conditional and log a debug message if the baseline has fewer than k results:
```python
if len(baseline_ids) < 50:
    logger.debug("[%s] recall@k50: baseline has only %d results for '%s'", self._db_name, len(baseline_ids), q["query_text"])
k50_scores.append(recall_at_k(baseline_ids, candidate_ids_50, k=50))
```

---

### WR-05: `run_filtered_unfiltered` produces a zero-count metrics block with no signal when no filtered queries exist

**File:** `benchmark/runner.py:287-313`

**Issue:** If `CANONICAL_QUERIES` is modified to contain zero filtered queries, `_run_group([])` returns a `QueryMetrics` with all fields at 0.0 and `query_count=0`. This is stored in `self.results["query_latency_filtered"]` with no indication that the measurement was skipped rather than performed. A report consumer cannot distinguish "filtered queries were run and completed in 0ms" from "no filtered queries were defined". The same applies to the unfiltered group, which currently has 6 entries but could be reduced to zero by a future change.

**Fix:** Add a guard and store `None` (or a clearly annotated dict) when the group is empty:
```python
uf_metrics = _run_group(unfiltered) if unfiltered else None
f_metrics = _run_group(filtered) if filtered else None
self.results["query_latency_unfiltered"] = asdict(uf_metrics) if uf_metrics else None
self.results["query_latency_filtered"] = asdict(f_metrics) if f_metrics else None
```

---

### WR-06: `BaseLoader` ABC does not declare `query()` as abstract

**File:** `loaders/__init__.py:41-57`

**Issue:** The `BaseLoader` ABC defines `load()` as `@abstractmethod`, correctly preventing subclasses from omitting it. However, `query()` is called on every `BaseLoader` instance throughout `runner.py` (e.g., `self._loader.query(...)` on line 151), but `query()` is not declared as abstract in `BaseLoader`. A future loader subclass that omits `query()` will successfully instantiate and only fail at runtime deep inside a benchmark run. The `close()` method has the same issue but less urgently — the base no-op is at least safe.

**Fix:**
```python
@abstractmethod
def query(
    self,
    collection: str,
    query_text: str,
    k: int,
    filter: dict | None = None,
) -> list[str]:
    """Query the target DB and return top-k document IDs."""
    ...
```

---

### WR-07: `_poll_memory` appends RSS bytes to a `list[float]` but RSS is in bytes (int)

**File:** `benchmark/runner.py:93-98`

**Issue:**
```python
samples: list[float] = []
...
samples.append(proc.memory_info().rss)
```

`psutil.Process().memory_info().rss` returns an `int` (bytes). The type annotation `list[float]` is wrong — these are integers, not floats. Downstream, `max(samples)` on line 373 and the division `peak_bytes / 1024**2` will work numerically (Python coerces int to float), but the variable is then named `peak_bytes` in the caller, which expects bytes. The semantic naming inconsistency (a `float` list named `samples` holding raw byte counts) will cause confusion during maintenance.

**Fix:** Type the list correctly and use a clearer name:
```python
samples: list[int] = []  # RSS in bytes
```
And in `_poll_memory`:
```python
def _poll_memory(samples: list[int], stop_event: threading.Event, interval_s: float = 0.150) -> None:
```

---

## Info

### IN-01: `sys.path.append` used inconsistently across loader modules

**File:** `loaders/chromadb_loader.py:19`, `loaders/weaviate_loader.py:19`, `loaders/qdrant_loader.py:19`

**Issue:** All three loader files use `sys.path.append(str(Path(__file__).parent.parent))` at module import time. `benchmark/runner.py` uses the safer `sys.path.insert(0, ...)`. The `append` variant adds the project root at the *end* of the path, meaning any installed package with the same name (e.g., a `config` package) takes precedence over the project's local `config/` module. `insert(0, ...)` guarantees local modules win.

**Fix:** Change all three loader files to use `sys.path.insert(0, ...)` for consistency with runner.py:
```python
sys.path.insert(0, str(Path(__file__).parent.parent))
```

---

_Reviewed: 2026-04-24T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
