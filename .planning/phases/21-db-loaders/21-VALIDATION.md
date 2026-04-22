---
phase: 21
slug: db-loaders
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-21
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already installed) |
| **Config file** | none — pytest discovers `tests/` directory |
| **Quick run command** | `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_phase6.py -x` |
| **Full suite command** | `pipenv run py -m pytest tests/ -x` |
| **Estimated runtime** | ~10 seconds (unit tests); integration tests skip when Docker is down |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_phase6.py -x`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green (integration tests may skip if Docker is down — skips are acceptable, failures are not)
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 21-Deps | 01 | 0 | BENCH-02/03/04 | unit (import) | `pipenv run py -c "import weaviate; import qdrant_client; print('ok')"` | ❌ W0 | ⬜ pending |
| 21-Compat | 01 | 0 | BENCH-02/03/04 | unit | `pipenv run py -m pytest tests/test_phase6.py -x` | ✅ (needs unpack fix) | ⬜ pending |
| 21-Transforms | 02 | 1 | BENCH-02/03/04 | unit | `pipenv run py -m pytest tests/test_shared_transforms.py -x` | ✅ | ⬜ pending |
| 21-Embeddings | 02 | 1 | BENCH-02/03/04 | unit | `pipenv run py -m pytest tests/test_embeddings.py -x` | ❌ W0 | ⬜ pending |
| 21-ChromaDB | 03 | 2 | BENCH-02 | integration | `pipenv run py -m pytest tests/test_loaders_chromadb.py -x` | ❌ W0 | ⬜ pending |
| 21-Weaviate | 04 | 2 | BENCH-03 | integration | `pipenv run py -m pytest tests/test_loaders_weaviate.py -x` | ❌ W0 | ⬜ pending |
| 21-Qdrant | 05 | 2 | BENCH-04 | integration | `pipenv run py -m pytest tests/test_loaders_qdrant.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `Pipfile` — add `weaviate-client==4.20.5` and `qdrant-client==1.17.1`; run `pipenv install`
- [ ] `tests/test_phase6.py` — update 26 tuple unpack sites to 4-element form before modifying shared_transforms
- [ ] `tests/conftest.py` — add shared `TalkBundle` fixture + 3x session-scoped port-check skip fixtures (chromadb_available, weaviate_available, qdrant_available)
- [ ] `tests/test_loaders_chromadb.py` — stub: insert sample bundle, query paragraphs, assert round-trip
- [ ] `tests/test_loaders_weaviate.py` — stub: insert sample bundle, near-vector query, assert round-trip
- [ ] `tests/test_loaders_qdrant.py` — stub: insert sample bundle, vector search, assert round-trip
- [ ] `tests/test_embeddings.py` — stub: mock Ollama response, assert embed() returns list[float] of len 768

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Weaviate schema visible in UI | BENCH-03 | UI console not automatable in CI | Open http://localhost:8080 → Schema tab → verify Talk/Paragraph/Citation/Footnote classes exist |
| Qdrant payload indexes visible | BENCH-04 | REST API introspection | `curl http://localhost:6333/collections/paragraphs` → check `payload_schema` field |
| ChromaDB collection count | BENCH-02 | Sanity check | `chromadb.HttpClient("localhost",8000).list_collections()` → 4 collections |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
