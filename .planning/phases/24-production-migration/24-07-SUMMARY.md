---
phase: 24-production-migration
plan: "07"
subsystem: config, server, models, extractors, tests
status: complete
tags: [chromadb-removal, refactor, rename, production-blocker]
completed: "2026-06-28T00:25:03Z"
duration: ~5min

dependency_graph:
  requires: [24-01, 24-02, 24-03, 24-04, 24-05]
  provides: [chromadb-free-ollama-embedder, standalone-validate-collections, db-record-interface]
  affects: [config/ollama.py, server.py, models/*.py, extractors/phase5_validation.py, tests/]

tech_stack:
  added: []
  patterns: [requests-based-embedder, extraction-refactor, rename-for-generality]

key_files:
  created: []
  modified:
    - config/ollama.py
    - server.py
    - models/talk_metadata.py
    - models/paragraph_data.py
    - models/citation_data.py
    - models/footnote_data.py
    - extractors/phase5_validation.py
    - extractors/phase1_talk_metadata.py
    - extractors/phase2_paragraph_extraction.py
    - tests/test_phase1.py
    - tests/test_phase4.py
    - tests/test_phase5.py

decisions:
  - "OllamaEmbedder uses one requests.post per text (Ollama /api/embeddings is one-text-per-call)"
  - "get_embedding_function() preserves public API signature — no caller changes needed"
  - "paragraphs_to_chromadb_format function name in phase2 preserved — only callee call site updated"
  - "examples/phase1_example.py left with old to_chromadb_format call — intentional (per plan note)"

metrics:
  tasks_completed: 3
  tasks_total: 3
  commits: 3
  files_changed: 12
---

# Phase 24 Plan 07: Production Blocker Fixes Summary

Three production blockers fixed in a single wave-3 plan: chromadb import in config/ollama.py,
inlined collection validation in _startup(), and ChromaDB-named data model methods across
four model classes — all resolved via requests-based replacement, function extraction, and
mechanical renaming with zero behavior changes.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Fix config/ollama.py — remove chromadb import | 35b8a76 | config/ollama.py |
| 2 | Extract _validate_collections() from server.py | b65caf5 | server.py |
| 3 | Rename to_chromadb_format -> to_db_record across models, extractors, tests | bd8a585 | models/*.py, extractors/phase5_validation.py, tests/ |

## What Was Built

**Task 1 — config/ollama.py rewrite:**
Replaced `from chromadb.utils.embedding_functions import OllamaEmbeddingFunction` with a
plain `OllamaEmbedder` class that posts to Ollama's `/api/embeddings` endpoint via `requests`.
Public API preserved exactly: `resolve_ollama_url()` and `get_embedding_function(url=None)`
both work identically. Zero chromadb references remain.

**Task 2 — server.py extraction:**
Extracted the 4-collection validation for-loop from `_startup()` into a new standalone
`_validate_collections(client: weaviate.WeaviateClient) -> None` function placed immediately
before `_startup()`. `_startup()` now calls `_validate_collections(client)`. The function is
independently importable and testable. Behavior is identical.

**Task 3 — mechanical rename across 10 files:**
- `to_chromadb_format()` -> `to_db_record()` in all 4 model classes (talk_metadata, paragraph_data, citation_data, footnote_data)
- `_check_chromadb_readiness()` -> `_check_db_readiness()` in phase5_validation.py plus all internal call sites updated to `.to_db_record()`
- Call sites in phase1_talk_metadata.py and phase2_paragraph_extraction.py updated
- Test methods renamed and patched methods updated in test_phase1.py, test_phase4.py, test_phase5.py

## Verification Results

```
grep -rn "chromadb" config/ollama.py server.py models/ extractors/phase5_validation.py
→ NONE (only pycache binaries)

pipenv run py -c "from config.ollama import get_embedding_function, resolve_ollama_url; print('ollama ok')"
→ ollama ok

pipenv run py -c "from server import _validate_collections; print('server ok')"
→ server ok

pipenv run py -c "from extractors.phase5_validation import _check_db_readiness; print('phase5 ok')"
→ phase5 ok

pipenv run py -c "from models.talk_metadata import TalkMetadata; assert hasattr(TalkMetadata, 'to_db_record')"
→ rename ok

pipenv run py -m pytest tests/test_phase1.py tests/test_phase4.py tests/test_phase5.py -x -q
→ 153 passed in 0.72s
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- config/ollama.py: exists, no chromadb imports
- server.py: _validate_collections defined at line 127, called at line 161
- models/talk_metadata.py: to_db_record() present
- models/paragraph_data.py: to_db_record() present
- models/citation_data.py: to_db_record() present
- models/footnote_data.py: to_db_record() present
- extractors/phase5_validation.py: _check_db_readiness() present
- Commits: 35b8a76 (ollama), b65caf5 (server), bd8a585 (rename)
- 153 tests pass
