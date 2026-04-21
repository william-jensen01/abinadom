# Phase 21: DB Loaders — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 21-db-loaders
**Areas discussed:** Loader interface design, Embedding helper location, Batch size & error handling, Integration test strategy

---

## Loader Interface Design

| Option | Description | Selected |
|--------|-------------|----------|
| Class-based | `ChromaDBLoader(host, port)` with `.load(bundle)` method; connection reused | ✓ |
| Function-based | `load_to_chromadb(host, port, bundle, embed_fn)` — no state, simpler isolation | |

**User's choice:** Class-based

---

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse connection | Client created in `__init__`, reused across `.load()` calls | ✓ |
| New connection per load | Opens and closes connection per call | |

**User's choice:** Reuse connection

---

| Option | Description | Selected |
|--------|-------------|----------|
| Constructor injection | `embed_fn` passed once at construction time | ✓ |
| Per-load injection | `embed_fn` passed on each `.load()` call | |

**User's choice:** Constructor injection

---

| Option | Description | Selected |
|--------|-------------|----------|
| Shared BaseLoader ABC | Abstract base in `loaders/__init__.py` with `load()` method | ✓ |
| Duck typing | No base class — all 3 loaders share same interface by convention | |

**User's choice:** Shared ABC

---

## Embedding Helper Location

| Option | Description | Selected |
|--------|-------------|----------|
| `loaders/embeddings.py` | Dedicated file in same package as loaders | ✓ |
| `benchmark/embeddings.py` | Lives with runner code; creates sibling-package dependency | |
| `loaders/shared_transforms.py` | Inline with prepare_* — mixes I/O with data transforms | |

**User's choice:** `loaders/embeddings.py`

---

| Option | Description | Selected |
|--------|-------------|----------|
| Synchronous | Simple `httpx.post` to Ollama | ✓ |
| Async | `httpx` async client | |

**User's choice:** Synchronous

---

## Batch Size & Error Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable constructor arg | `batch_size=100` default, caller overrides | ✓ |
| Hardcoded 100 | Simpler, no parameter surface | |
| Hardcoded 50 | Conservative default | |

**User's choice:** Configurable constructor arg (default 100)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Skip-and-log | Log WARNING, continue with remaining records | ✓ |
| Fail-fast (raise) | Raise immediately on first error | |

**User's choice:** Skip-and-log

---

## Integration Test Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Skip-if-port-closed | Session-scoped fixture checks port reachability; auto-skip | ✓ |
| pytest.mark.integration flag | Tests skipped unless `--run-integration` passed | |
| Always fail | No special handling — fail with connection error | |

**User's choice:** Skip-if-port-closed

---

| Option | Description | Selected |
|--------|-------------|----------|
| Shared fixture in conftest.py | One minimal TalkBundle fixture shared across all 3 loader tests | ✓ |
| Inline per test file | Each test file builds its own bundle | |

**User's choice:** Shared fixture in conftest.py

---

## Claude's Discretion

- Collection/class naming conventions (Qdrant snake_case, Weaviate PascalCase)
- Qdrant default vector vs named vectors (chose default — simpler API)
- Weaviate UUID derivation using `generate_uuid5(doc_id)`
- Minimal TalkBundle fixture uses `talk_id=9999` for deterministic test assertions
