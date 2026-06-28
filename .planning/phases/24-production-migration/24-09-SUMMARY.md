---
phase: 24-production-migration
plan: "09"
subsystem: verification-tooling
tags:
  - weaviate
  - verification
  - pipeline
  - migration
dependency_graph:
  requires:
    - 24-01
    - 24-04
  provides:
    - scripts/verify_chromadb_pipeline.py
    - scripts/verify_weaviate_pipeline.py
  affects:
    - config/pipeline_config.py
    - CLAUDE.md
tech_stack:
  added:
    - weaviate-client v4 collections.aggregate / query APIs in verification script
    - weaviate.classes.query.Filter for metadata filter checks
    - weaviate.util.generate_uuid5 for deterministic FK spot-check
  patterns:
    - Context-manager connection: `with weaviate.connect_to_local(...) as client`
    - WEAVIATE_COLLECTION_NAMES lookup for all 4 collection keys
    - Optional Ollama embedding via --embedding flag (VER-02 skipped otherwise)
key_files:
  created:
    - scripts/verify_weaviate_pipeline.py
  modified:
    - scripts/verify_chromadb_pipeline.py (git mv of verify_pipeline.py + docstring + import fix)
    - config/pipeline_config.py (CHROMADB_COLLECTION_NAMES re-added for backward compat)
    - CLAUDE.md (scripts index updated)
decisions:
  - "verify_chromadb_pipeline.py imports fixed inline (get_chromadb_client/get_embedding_function) after phase6_chromadb_loader deletion — no logic change to check implementations"
  - "CHROMADB_COLLECTION_NAMES re-added to pipeline_config.py for backward compat; comment explains production now uses Weaviate (Phase 24)"
  - "VER-02 in verify_weaviate_pipeline.py skipped by default; --embedding flag triggers Ollama via requests API (consistent with 24-07 OllamaEmbedder pattern)"
  - "VER-04 uses spot-check (10 paragraphs, 5 citations) rather than full scan — Weaviate lacks ChromaDB-style paged offset iteration in this API shape"
metrics:
  duration: "~12 minutes"
  completed: "2026-06-28T00:52:25Z"
  tasks_completed: 2
  files_created: 1
  files_modified: 3
status: complete
requirements:
  - MIGR-02
  - MIGR-03
---

# Phase 24 Plan 09: Verification Tooling Rename and Weaviate Script Summary

Rename `scripts/verify_pipeline.py` to `scripts/verify_chromadb_pipeline.py` (git mv, history preserved), fix broken import from the deleted `phase6_chromadb_loader`, and create `scripts/verify_weaviate_pipeline.py` with VER-01 through VER-05 checks against Weaviate collections using the v4 client API.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rename verify_pipeline.py to verify_chromadb_pipeline.py | 5d46d47 | scripts/verify_chromadb_pipeline.py, config/pipeline_config.py, CLAUDE.md |
| 2 | Create scripts/verify_weaviate_pipeline.py | 959d526 | scripts/verify_weaviate_pipeline.py |

## What Was Built

### Task 1: verify_chromadb_pipeline.py (renamed)

- `git mv scripts/verify_pipeline.py scripts/verify_chromadb_pipeline.py` — git history preserved
- Updated module docstring: "Post-pipeline verification script (ChromaDB)." with note to use `verify_weaviate_pipeline.py` for Weaviate
- Fixed broken import: `extractors.phase6_chromadb_loader` was deleted in 24-07; replaced with inline `get_chromadb_client()` (uses `chromadb.HttpClient` via env vars) and `get_embedding_function()` (uses chromadb OllamaEmbeddingFunction with graceful fallback)
- Added `CHROMADB_COLLECTION_NAMES` back to `config/pipeline_config.py` for backward compatibility (with comment explaining production now uses Weaviate)
- `pipenv run py scripts/verify_chromadb_pipeline.py --help` exits 0

### Task 2: verify_weaviate_pipeline.py (new)

Full Weaviate verification script implementing VER-01 through VER-05:

- **VER-01** `check_counts()`: uses `collections.aggregate.over_all(total_count=True)` for all 4 collections; derives expected talk count from SQLite INNER JOIN; passes if talks match exactly and others > 0
- **VER-02** `check_semantic_search()`: skipped by default; enabled with `--embedding` flag; uses Ollama `/api/embeddings` via `requests.post` (one call per text) then `col.query.near_vector`
- **VER-03** `check_metadata_filters()`: uses `weaviate.classes.query.Filter` for speaker LIKE, year equal, month equal, and compound (year & month) filters; verifies returned objects satisfy filter
- **VER-04** `check_fk_integrity()`: spot-checks 10 paragraphs and 5 citations; derives UUID via `generate_uuid5(f"talk_{talk_id}")` and calls `fetch_object_by_id`; passes if 0 misses
- **VER-05** `check_topics_metadata()`: samples 5 talk records; checks title is non-empty string, speaker_name is non-empty string, topics is a list (may be empty)

Connection: `with weaviate.connect_to_local(host, port, grpc_port) as client` — host/port read from `WEAVIATE_HOST` / `WEAVIATE_PORT` / `WEAVIATE_GRPC_PORT` env vars.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed broken import from deleted phase6_chromadb_loader module**
- **Found during:** Task 1 pre-analysis
- **Issue:** `scripts/verify_pipeline.py` (now verify_chromadb_pipeline.py) imported `get_chromadb_client, get_embedding_function` from `extractors.phase6_chromadb_loader`, which was deleted in Phase 24-07. The module-level import would cause `ImportError` preventing `--help` from working.
- **Fix:** Replaced the broken import with inline `get_chromadb_client()` and `get_embedding_function()` functions using `chromadb.HttpClient` directly (consistent with the original `config/chromadb_client.py` factory pattern from before Phase 24-04).
- **Files modified:** `scripts/verify_chromadb_pipeline.py`
- **Commit:** 5d46d47

**2. [Rule 2 - Missing Backward Compat] Re-added CHROMADB_COLLECTION_NAMES to pipeline_config.py**
- **Found during:** Task 1 pre-analysis
- **Issue:** The plan stated "this constant was re-added to pipeline_config.py for backward compatibility" but it was not present — only `WEAVIATE_COLLECTION_NAMES` existed. `verify_chromadb_pipeline.py` imports it from there.
- **Fix:** Added `CHROMADB_COLLECTION_NAMES` dict with the original snake_case collection names to `config/pipeline_config.py` with a comment explaining production now uses Weaviate.
- **Files modified:** `config/pipeline_config.py`
- **Commit:** 5d46d47

## Verification Results

```
# Rename complete
test -f scripts/verify_chromadb_pipeline.py  -> OK
test ! -f scripts/verify_pipeline.py         -> OK

# New file exists and is runnable
pipenv run py scripts/verify_weaviate_pipeline.py --help -> exit 0, shows --output and --embedding args

# No chromadb refs in new script
grep -ic "chromadb" scripts/verify_weaviate_pipeline.py -> 0

# Weaviate imports
grep WEAVIATE_COLLECTION_NAMES -> 23 matches (all 4 VER checks use collection names)
grep connect_to_local            -> 1 match
grep Filter                      -> 5+ matches (import + 4 filter uses)

# CLAUDE.md updated
verify_chromadb_pipeline.py entry: line 124
verify_weaviate_pipeline.py entry: line 125
```

## Known Stubs

None — all VER checks are fully implemented. VER-02 is intentionally skipped by default (not a stub — it requires Ollama which may not be available at verification time; operator enables with `--embedding` flag).

## Threat Flags

No new threat surface beyond what is documented in the plan's threat model. Report file written to local `data/` directory only. Connection parameters come from environment variables (no hardcoded credentials).

## Self-Check: PASSED

- [x] `scripts/verify_chromadb_pipeline.py` exists: confirmed
- [x] `scripts/verify_pipeline.py` does not exist: confirmed
- [x] `scripts/verify_weaviate_pipeline.py` exists: confirmed
- [x] Task 1 commit 5d46d47: `git log --oneline` confirms
- [x] Task 2 commit 959d526: `git log --oneline` confirms
- [x] `grep -ic "chromadb" scripts/verify_weaviate_pipeline.py` returns 0: confirmed
- [x] CLAUDE.md updated with both entries: confirmed at lines 124-125
