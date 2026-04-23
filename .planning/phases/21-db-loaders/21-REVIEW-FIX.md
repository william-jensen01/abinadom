---
phase: 21-db-loaders
fixed_at: 2026-04-23T00:00:00Z
review_path: .planning/phases/21-db-loaders/21-REVIEW.md
fix_scope: critical_warning
findings_in_scope: 5
fixed: 5
skipped: 0
iteration: 1
status: all_fixed
---

# Phase 21: Code Review Fix Report

**Fixed at:** 2026-04-23T00:00:00Z
**Source review:** `.planning/phases/21-db-loaders/21-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0

## Fixed Issues

### WR-01: `rich_metadata()` passes empty lists into Weaviate

**Files modified:** `loaders/shared_transforms.py`
**Commit:** `74b0e1a`
**Applied fix:** Added `and v != []` to the dict comprehension filter condition in `rich_metadata()`. The docstring was also updated to document that empty lists are removed (same as `None` values) because Weaviate rejects empty arrays for `TEXT_ARRAY` / `INT_ARRAY` properties.

---

### WR-02: `WeaviateLoader.load()` checks `col.batch.failed_objects` after context exit

**Files modified:** `loaders/weaviate_loader.py`
**Commit:** `43a89a4`
**Applied fix:** Renamed the context manager target from `batch` to `batch_ctx` throughout the `with col.batch.fixed_size(...) as batch_ctx:` block, and changed the post-block check from `col.batch.failed_objects` to `batch_ctx.failed_objects`. The comment was updated to explain that `failed_objects` is a property of the context manager object in weaviate-client v4, not of the persistent `col.batch` handle.

---

### WR-03: `WeaviateLoader` has no `__enter__`/`__exit__`

**Files modified:** `loaders/__init__.py`, `loaders/weaviate_loader.py`
**Commit:** `c30aa80`
**Applied fix:**
- Added a concrete `close()` method to `BaseLoader` in `loaders/__init__.py` with a no-op body and docstring explaining subclasses should override when they hold connections.
- Added `__enter__` (returns `self`) and `__exit__` (calls `self.close()`, returns `False`) to `WeaviateLoader` in `loaders/weaviate_loader.py`, placed immediately before the existing `close()` method. This enables `with WeaviateLoader(...) as loader:` usage and ensures the gRPC connection is released even when callers iterate over a `list[BaseLoader]` and call `close()` via the ABC interface.

---

### WR-04: `_ensure_collections()` creates payload indexes only on first collection creation

**Files modified:** `loaders/qdrant_loader.py`
**Commit:** `47523ba`
**Applied fix:** Moved the three `create_payload_index()` calls (`talk_id`, `conference_year`, `speaker_name`) outside the `if not self._client.collection_exists(name):` guard so they run unconditionally for every collection on every startup. Added a comment explaining that this is idempotent on Qdrant (no error if index already exists) and that the indexes must be present for Phase 22 filtered queries even when connecting to collections created in a prior run.

---

### WR-05: `test_loaders_chromadb.py` round-trip assertion is fragile

**Files modified:** `tests/test_loaders_chromadb.py`
**Commit:** `5444b95`
**Applied fix:** Applied both remediation options from the review:
- Before calling `loader.load(talk_bundle)`, the test now calls `col.delete(where={"talk_id": 9999})` to purge any stale records from prior runs (Option A).
- The query now passes `where={"talk_id": 9999}` and `n_results=5` instead of `n_results=1` with no filter (Option B), so only records belonging to the test talk are candidates for the assertion (Option B). This makes the assertion deterministic regardless of what other data exists in the collection.

---

_Fixed: 2026-04-23T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
