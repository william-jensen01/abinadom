---
phase: 21-db-loaders
plan: "02"
subsystem: database
tags: [vector-db, embeddings, ollama, chromadb, weaviate, qdrant, abc, shared-transforms]

# Dependency graph
requires:
  - phase: 21-01
    provides: "weaviate-client + qdrant-client installed, conftest.py fixtures, test stubs, test_phase6.py pre-updated for 4-element tuples"
provides:
  - "loaders/shared_transforms.py: all 5 prepare_* functions return (doc, meta, id, vector|None) 4-element tuples"
  - "loaders/shared_transforms.py: prepare_talk_bundle_rich() and 4 _rich helper functions using rich_metadata()"
  - "loaders/__init__.py: BaseLoader ABC with abstract load(bundle: TalkBundle) -> None"
  - "loaders/embeddings.py: embed() helper calling Ollama nomic-embed-text, returning list[float] length 768"
affects:
  - 21-03 (ChromaDB loader imports prepare_talk_bundle_rich and BaseLoader)
  - 21-04 (Weaviate loader same)
  - 21-05 (Qdrant loader same)
  - 22 (benchmark runner imports BaseLoader and list[BaseLoader])

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "4-element tuple (doc, meta, id, vector|None) as universal record type for all vector DB loaders"
    - "embed_fn=None default for backward compat — existing callers get vector=None automatically"
    - "BaseLoader ABC with constructor-injected embed_fn (D-02) and configurable batch_size (D-06)"
    - "_rich variant pattern for functions that use rich_metadata() vs flatten_metadata()"

key-files:
  created:
    - loaders/embeddings.py
  modified:
    - loaders/shared_transforms.py
    - loaders/__init__.py

key-decisions:
  - "embed_fn=None default on all prepare_* functions preserves full backward compat — phase6 tests unaffected"
  - "BaseLoader ABC lives in loaders/__init__.py so `from loaders import BaseLoader` works cleanly"
  - "embed() propagates Ollama exceptions to callers — no try/except in embeddings.py per D-07"

patterns-established:
  - "Vector fill pattern: `vector = embed_fn(document) if embed_fn is not None else None` at end of each record tuple"
  - "Rich variant: separate _prepare_*_rich() helpers using rich_metadata() instead of flatten_metadata()"
  - "prepare_talk_bundle_rich() mirrors prepare_talk_bundle() but routes all metadata through rich_metadata()"

requirements-completed:
  - BENCH-02
  - BENCH-03
  - BENCH-04

# Metrics
duration: 25min
completed: 2026-04-22
---

# Phase 21 Plan 02: Shared Transforms Extension and BaseLoader ABC Summary

**Extended all 5 prepare_* functions to 4-element (doc, meta, id, vector|None) tuples, added prepare_talk_bundle_rich() with _rich helpers using rich_metadata(), created BaseLoader ABC, and Ollama embed() helper — all backward compat gates green (76 tests passed).**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-22T21:39:00Z
- **Completed:** 2026-04-22T22:04:20Z
- **Tasks:** 2
- **Files modified:** 3 (shared_transforms.py, __init__.py, embeddings.py new)

## Accomplishments
- All 5 `prepare_*` functions in `loaders/shared_transforms.py` now return 4-element `(doc, meta, id, vector|None)` tuples with `embed_fn=None` backward compat default
- Added `prepare_talk_bundle_rich()` and four `_prepare_*_rich()` helpers using `rich_metadata()` — lists (topics, verse_list) preserved as native Python lists for Weaviate/Qdrant
- `BaseLoader` ABC in `loaders/__init__.py` enforces uniform `load(bundle: TalkBundle) -> None` interface; `__abstractmethods__ == frozenset({'load'})`
- `embed()` in `loaders/embeddings.py` calls `ollama.Client(host=url).embed(model=model, input=text)` and returns `list[float]` of length 768

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend shared_transforms.py — 4-element tuples and _rich variants** - `287e51a` (feat)
2. **Task 2: Create loaders/__init__.py (BaseLoader ABC) and loaders/embeddings.py** - `f9c776d` (feat)

**Plan metadata:** (see final commit below)

## Files Created/Modified
- `loaders/shared_transforms.py` — Extended all 5 `prepare_*` functions with `embed_fn=None` param; added `_prepare_*_rich()` helpers and `prepare_talk_bundle_rich()`
- `loaders/__init__.py` — Replaced package marker with `BaseLoader` ABC (abstract `load(bundle)` method, constructor with `host`, `port`, `embed_fn`, `batch_size=100`)
- `loaders/embeddings.py` — New file: synchronous `embed(text, model, url)` helper calling Ollama, `OLLAMA_URL = "http://localhost:11434"`

## Decisions Made
- `embed_fn=None` default on all `prepare_*` functions ensures every existing caller (phase6 loader, test_phase6.py) receives `vector=None` without any code changes — backward compat guaranteed
- `BaseLoader` in `loaders/__init__.py` (not a separate file) so `from loaders import BaseLoader` is the clean import path for Phase 22 benchmark runner
- No try/except in `loaders/embeddings.py` — exceptions propagate to callers per D-07 skip-and-log pattern

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — all tests passed on first run after implementation. The Wave 0 pre-work (27 tuple unpack site updates in test_phase6.py from Plan 01) meant test_phase6.py was already ready for 4-element tuples.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave 2 loaders (ChromaDB, Weaviate, Qdrant) can now import `BaseLoader` from `loaders` and `prepare_talk_bundle_rich` from `loaders.shared_transforms`
- `embed` from `loaders.embeddings` is ready to inject as `embed_fn` into all 3 loaders
- All 76 backward compat tests green: `tests/test_shared_transforms.py` (14 passed), `tests/test_phase6.py` (59 passed), `tests/test_embeddings.py` (3 passed — mock tests pass, live test passes with Ollama running)

## Known Stubs
None — all functions are fully implemented. Wave 2 loader stubs (`tests/test_loaders_*.py`) remain from Plan 01 Wave 0 and will be resolved in Plans 03-05.

## Threat Surface Scan
No new network endpoints introduced. `embed()` calls Ollama at localhost only (LAN-local, per T-21-02-01 accepted). T-21-02-03 mitigation confirmed: `embed_fn=None` default preserves behavioral backward compat for all existing callers.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| loaders/shared_transforms.py — prepare_talk_bundle_rich exists | FOUND |
| loaders/shared_transforms.py — _prepare_paragraph_records_rich exists | FOUND |
| loaders/shared_transforms.py — embed_fn.*None matches (25 sites) | FOUND |
| loaders/__init__.py — class BaseLoader | FOUND |
| loaders/__init__.py — abstractmethod | FOUND |
| loaders/embeddings.py — def embed | FOUND |
| loaders/embeddings.py — OLLAMA_URL | FOUND |
| Commit 287e51a (shared_transforms.py extension) | FOUND |
| Commit f9c776d (BaseLoader ABC + embeddings.py) | FOUND |
| tests/test_shared_transforms.py + test_phase6.py + test_embeddings.py: 76 passed | PASS |
