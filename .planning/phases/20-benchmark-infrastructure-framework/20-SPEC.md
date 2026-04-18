# Phase 20: Benchmark Infrastructure & Framework — Specification

**Created:** 2026-04-18
**Ambiguity score:** 0.18 (gate: ≤ 0.20)
**Requirements:** 7 locked

## Goal

Developer can start all three vector DBs locally via one Docker Compose command and import shared transform, metric, and query modules that all Phase 21+ loaders and the Phase 22 runner will depend on.

## Background

The project uses ChromaDB over HTTP with 4 collections (talks, paragraphs, citations, footnotes). The production loader (`extractors/phase6_chromadb_loader.py`) contains a private `_flatten_metadata()` and public `prepare_*` functions that are ChromaDB-specific. No benchmark infrastructure exists today: no `benchmark/` directory, no `loaders/` directory, and no Docker Compose file for local vector DB testing.

Phase 20 extracts the shared transform logic into `loaders/shared_transforms.py`, adds a `rich_metadata()` variant for Weaviate/Qdrant, creates the metrics and canonical query modules, and brings up the Docker Compose stack — all as the foundation for Phases 21–23.

The production loader (`extractors/phase6_chromadb_loader.py`) is **not modified** in this phase.

## Requirements

1. **Docker Compose stack**: All three vector DBs start via a single compose file and pass individual health checks.
   - Current: No local vector DB stack exists; only Caddy+cloudflared (`infra/docker-compose.yml`) and MCP server (`docker-compose.yml`)
   - Target: `docker compose -f infra/docker-compose.vector-dbs.yml up -d` starts ChromaDB, Weaviate, and Qdrant; each passes its HTTP health check
   - Acceptance: All three health check URLs return HTTP 200 after `docker compose up`

2. **`flatten_metadata()`**: Converts a raw metadata dict to ChromaDB-safe flat scalars.
   - Current: Exists as private `_flatten_metadata()` in `extractors/phase6_chromadb_loader.py`; not importable by external code
   - Target: Public `flatten_metadata()` in `loaders/shared_transforms.py`; removes None values, joins lists to strings (int lists → comma-joined, str lists → pipe-joined)
   - Acceptance: `flatten_metadata({"a": None, "b": [1,2], "c": ["x","y"]})` returns `{"b": "1,2", "c": "x|y"}`

3. **`rich_metadata()`**: Preserves Python list types for Weaviate and Qdrant native array support.
   - Current: Does not exist anywhere
   - Target: `rich_metadata()` in `loaders/shared_transforms.py`; strips None values, keeps lists as-is (no flattening)
   - Acceptance: `rich_metadata({"a": None, "b": [1,2], "c": ["x","y"]})` returns `{"b": [1,2], "c": ["x","y"]}`

4. **`prepare_*` functions**: All five transform functions are importable from `loaders/shared_transforms.py`.
   - Current: `prepare_talk_record`, `prepare_paragraph_records`, `prepare_citation_records`, `prepare_footnote_records`, `prepare_talk_bundle` exist in `extractors/phase6_chromadb_loader.py` using the private flatten helper
   - Target: All five extracted (not copied — extracted via import delegation or direct move) to `loaders/shared_transforms.py`; `prepare_talk_bundle` returns dict with keys `"talks"`, `"paragraphs"`, `"citations"`, `"footnotes"`
   - Acceptance: `from loaders.shared_transforms import prepare_talk_bundle` succeeds and calling it with a valid bundle returns a dict with all four keys; existing `tests/test_phase6.py` still passes

5. **Metric dataclasses**: Four metric dataclasses and `recall_at_k` are importable from `benchmark/metrics.py`.
   - Current: Does not exist
   - Target: `UpsertMetrics`, `QueryMetrics`, `ConcurrencyMetrics`, `MemoryMetrics` dataclasses and `recall_at_k(baseline_ids, candidate_ids, k) -> float` function in `benchmark/metrics.py`
   - Acceptance: `from benchmark.metrics import UpsertMetrics, QueryMetrics, ConcurrencyMetrics, MemoryMetrics, recall_at_k` succeeds; `recall_at_k(["a","b","c"], ["a","c","d"], k=3)` returns `2/3` (≈ 0.667)

6. **Canonical query set**: Query set is loadable as a Python list from `benchmark/queries.py`.
   - Current: Does not exist
   - Target: `CANONICAL_QUERIES` list in `benchmark/queries.py` with ≥ 5 paragraph queries and ≥ 2 citation queries; each query is a dict with `query_text`, `k`, `collection`, and `filter` keys (`filter` is None or a dict)
   - Acceptance: `from benchmark.queries import CANONICAL_QUERIES` succeeds; `len(CANONICAL_QUERIES) >= 7`; all entries have `query_text`, `k`, `collection`, `filter` keys; at least one entry has a non-None `filter`

7. **Unit tests**: Tests for shared transforms and metrics pass.
   - Current: No tests for `loaders/` or `benchmark/` modules
   - Target: `tests/test_shared_transforms.py` and `tests/test_metrics.py` with ≥ 3 tests each covering the core behavior
   - Acceptance: `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py` exits 0 with all tests passing

## Boundaries

**In scope:**
- `infra/docker-compose.vector-dbs.yml` — ChromaDB, Weaviate, Qdrant services with ports published to localhost
- `loaders/__init__.py` — package marker only
- `loaders/shared_transforms.py` — `flatten_metadata`, `rich_metadata`, `prepare_*`, `TalkBundle`
- `benchmark/__init__.py` — package marker only
- `benchmark/metrics.py` — four metric dataclasses + `recall_at_k`
- `benchmark/queries.py` — `CANONICAL_QUERIES` list
- `tests/test_shared_transforms.py` — unit tests for transform functions
- `tests/test_metrics.py` — unit tests for metric dataclasses and `recall_at_k`

**Out of scope:**
- `loaders/chromadb_loader.py`, `loaders/weaviate_loader.py`, `loaders/qdrant_loader.py` — that is Phase 21
- `benchmark/runner.py` — that is Phase 22
- Loading any actual talk data into the DBs — that is Phase 21+
- Running queries against the DBs — that is Phase 22+
- Ollama container in Docker Compose — Ollama runs on the host; `OLLAMA_URL` is an env var set by the operator
- Modifying `extractors/phase6_chromadb_loader.py` — production loader is not touched
- Authentication or TLS config for the benchmark DBs — local dev only, anonymous access
- `benchmark/results/` directory contents — gitignored outputs produced at runtime

## Constraints

- Vector dimension is 768 — the output dimension of `nomic-embed-text` (Ollama); loaders and runners must not hardcode a different value
- Benchmark Docker Compose uses an isolated `benchmark` Docker network; it does NOT join the production `proxy` network
- Published ports: ChromaDB → 8000, Weaviate → 8080 + 50051, Qdrant → 6333 + 6334
- The benchmark runner (Phase 22) will connect to DBs via `localhost:<port>`; env vars `CHROMADB_HOST`, `WEAVIATE_URL`, `QDRANT_URL` control connection
- `loaders/shared_transforms.py` must be importable without installing chromadb, weaviate-client, or qdrant-client — shared transforms have no DB-client dependencies
- All Python commands use `pipenv run py` (Windows Python Launcher)

## Acceptance Criteria

- [ ] `docker compose -f infra/docker-compose.vector-dbs.yml up -d` exits 0 and all three services start
- [ ] `curl http://localhost:8000/api/v1/heartbeat` returns HTTP 200 (ChromaDB)
- [ ] `curl http://localhost:8080/v1/.well-known/ready` returns HTTP 200 (Weaviate)
- [ ] `curl http://localhost:6333/healthz` returns HTTP 200 (Qdrant)
- [ ] `from loaders.shared_transforms import flatten_metadata, rich_metadata, prepare_talk_bundle` succeeds with no DB-client packages imported
- [ ] `flatten_metadata({"a": None, "b": [1,2], "c": ["x","y"]})` returns `{"b": "1,2", "c": "x|y"}`
- [ ] `rich_metadata({"a": None, "b": [1,2], "c": ["x","y"]})` returns `{"b": [1,2], "c": ["x","y"]}`
- [ ] `from benchmark.metrics import UpsertMetrics, QueryMetrics, ConcurrencyMetrics, MemoryMetrics, recall_at_k` succeeds
- [ ] `recall_at_k(["a","b","c"], ["a","c","d"], k=3)` returns `0.6666...` (2 overlapping IDs / k=3)
- [ ] `from benchmark.queries import CANONICAL_QUERIES` succeeds; `len(CANONICAL_QUERIES) >= 7`
- [ ] Every query dict in `CANONICAL_QUERIES` has keys: `query_text`, `k`, `collection`, `filter`
- [ ] At least one query in `CANONICAL_QUERIES` has `filter` set to a non-None dict
- [ ] `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py` exits 0
- [ ] `pipenv run py -m pytest tests/test_phase6.py` still exits 0 (no regression in production loader)

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                              |
|--------------------|-------|------|--------|----------------------------------------------------|
| Goal Clarity       | 0.85  | 0.75 | ✓      | Compose location locked (infra/); 4 deliverables clear |
| Boundary Clarity   | 0.85  | 0.70 | ✓      | Tests in scope; loaders/runner explicitly excluded |
| Constraint Clarity | 0.80  | 0.65 | ✓      | Network resolved (isolated benchmark); ports explicit |
| Acceptance Criteria| 0.75  | 0.70 | ✓      | Health check URLs explicit; recall_at_k example given |
| **Ambiguity**      | 0.18  | ≤0.20| ✓      |                                                    |

## Interview Log

| Round | Perspective | Question summary                          | Decision locked                                      |
|-------|-------------|------------------------------------------|------------------------------------------------------|
| 1     | Researcher  | Compose file location — infra/ vs benchmark/? | `infra/docker-compose.vector-dbs.yml`           |
| 1     | Researcher  | Docker network — proxy or isolated?      | Isolated `benchmark` network; runner connects via host ports |
| 1     | Researcher  | Unit tests in Phase 20?                  | Yes — `test_shared_transforms.py` + `test_metrics.py` |

---

*Phase: 20-benchmark-infrastructure-framework*
*Spec created: 2026-04-18*
*Next step: /gsd-discuss-phase 20 — implementation decisions (how to build what's specified above)*
