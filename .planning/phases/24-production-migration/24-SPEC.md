# Phase 24: Production Migration — Specification

**Created:** 2026-05-08
**Ambiguity score:** 0.136 (gate: ≤ 0.20)
**Requirements:** 8 locked

## Goal

The production MCP server, the full pipeline, and the Docker deployment stack all run on Weaviate; ChromaDB is fully removed from all production code paths; all 5,838 GC talks are searchable via MCP tools.

## Background

Phase 23 benchmark execution selected Weaviate as the production vector DB (see `benchmark/DECISION.md`). Key data points: Weaviate p50=42ms, filtered p50=51ms, 4.41 rec/s upsert — best across all dimensions that affect MCP user experience.

Current state of production code:
- `extractors/phase6_chromadb_loader.py` — already deleted from working tree
- `scripts/run_pipeline.py` — still imports from the deleted Phase 6 ChromaDB loader; broken
- `server.py` — uses `import chromadb`, `get_chromadb_client()`, `CHROMADB_COLLECTION_NAMES`
- `config/chromadb_client.py` — shared ChromaDB HttpClient factory (to be deleted)
- `config/pipeline_config.py` — has `CHROMADB_COLLECTION_NAMES` (snake_case)
- `docker-compose.yml` — has only `mcp-server` service; no Weaviate service
- `loaders/weaviate_loader.py` — exists; `WeaviateLoader` class with PascalCase collections (Talk, Paragraph, Citation, Footnote)
- `loaders/chromadb_loader.py` — benchmark loader; stays (not a production file)

## Requirements

1. **Phase 6 Weaviate Loader**: Create `extractors/phase6_weaviate_loader.py` as the production Phase 6 loader.
   - Current: Phase 6 loader slot is empty; `scripts/run_pipeline.py` imports from the deleted `extractors/phase6_chromadb_loader.py` → `ModuleNotFoundError` at runtime
   - Target: `extractors/phase6_weaviate_loader.py` exists and exposes `load_talk_bundles()` and `TalkBundle`, wrapping `loaders/weaviate_loader.py`'s `WeaviateLoader`
   - Acceptance: `python -c "from extractors.phase6_weaviate_loader import load_talk_bundles, TalkBundle"` exits 0

2. **Pipeline Weaviate Integration**: `scripts/run_pipeline.py` uses the new Weaviate loader with no ChromaDB imports.
   - Current: Imports `from extractors.phase6_chromadb_loader import load_talk_bundles, TalkBundle`; imports `get_chromadb_client`; uses `CHROMADB_COLLECTION_NAMES`, `CHROMADB_BATCH_SIZE`
   - Target: Imports from `extractors.phase6_weaviate_loader`; uses `WEAVIATE_COLLECTION_NAMES`; connects to Weaviate via env vars
   - Acceptance: `grep -i "chromadb" scripts/run_pipeline.py` → no matches; `pipenv run py scripts/run_pipeline.py --help` exits 0

3. **Collection Name Constants**: `config/pipeline_config.py` replaces `CHROMADB_COLLECTION_NAMES` with `WEAVIATE_COLLECTION_NAMES`.
   - Current: `CHROMADB_COLLECTION_NAMES = {"talks": "conference_talks", ...}` (snake_case ChromaDB names)
   - Target: `WEAVIATE_COLLECTION_NAMES = {"talks": "ConferenceTalks", "paragraphs": "ConferenceTalkParagraphs", "citations": "ConferenceTalkCitations", "footnotes": "ConferenceTalkFootnotes"}` — PascalCase conversions of the original ChromaDB names (D-18, decided post-SPEC). `WeaviateLoader.COLLECTIONS` is updated to match.
   - Acceptance: `python -c "from config.pipeline_config import WEAVIATE_COLLECTION_NAMES"` exits 0; `python -c "from config.pipeline_config import CHROMADB_COLLECTION_NAMES"` raises `ImportError`

4. **server.py Weaviate Client**: `server.py` connects to Weaviate and validates its collections at startup.
   - Current: `import chromadb`; `from config.chromadb_client import get_chromadb_client`; startup validates 4 ChromaDB collections; `GET /health` reports ChromaDB status
   - Target: Uses Weaviate client via `config/weaviate_client.py`; startup validates `ConferenceTalks`, `ConferenceTalkParagraphs`, `ConferenceTalkCitations`, `ConferenceTalkFootnotes` are non-empty (D-18, D-04); `GET /health` reports Weaviate as healthy
   - Acceptance: `grep -i "chromadb" server.py` → no matches; `GET /health` returns 200 with Weaviate status field

5. **ChromaDB and Qdrant Production Dependencies Removed**: All benchmark vector DB files and dependencies removed from production.
   - Current: `config/chromadb_client.py` exists; `chromadb` and `qdrant-client` in Pipfile `[packages]`; CHROMADB_HOST, CHROMADB_PORT referenced in `.env.example`
   - Target: `config/chromadb_client.py` deleted; `chromadb` and `qdrant-client` removed from Pipfile `[packages]`; no CHROMADB_* env vars in `.env.example`. `qdrant-client` has no production callers — same rationale as `chromadb`.
   - Acceptance: `ls config/chromadb_client.py` → file not found; `grep "chromadb" Pipfile` → no match in `[packages]` section; `grep "qdrant" Pipfile` → no match in `[packages]` section

6. **Docker Stack — Weaviate Service**: `docker-compose.yml` adds Weaviate as a co-located service.
   - Current: `docker-compose.yml` has only `mcp-server` service (external image); no Weaviate service; `.env.example` has ChromaDB env vars
   - Target: `docker-compose.yml` adds `weaviate` service using `cr.weaviate.io/semitechnologies/weaviate` (latest stable at execution time); HTTP port 8080 and gRPC port 50051 mapped; `mcp-server` service updated to reference WEAVIATE_* env vars; `.env.example` updated with `WEAVIATE_HOST`, `WEAVIATE_PORT`, `WEAVIATE_GRPC_PORT`; CHROMADB_* vars removed
   - Acceptance: `docker compose config` parses without error; `weaviate` service is present in the parsed output; `.env.example` has no CHROMADB_* lines

7. **Full Pipeline Run (Human-Gated Acceptance)**: `scripts/run_pipeline.py` processes all 5,838 GC talks writing to Weaviate.
   - Current: Pipeline is broken due to missing Phase 6 import
   - Target: After code changes, `pipenv run py scripts/run_pipeline.py` completes all 5,838 talks via `extractors/phase6_weaviate_loader.py` with 0 unrecoverable failures
   - Acceptance (human-gated): Run completes; Weaviate Paragraph collection count ≥ 5,838; `failed_talks.json` is empty or absent

8. **MCP Tool Smoke Test (Human-Gated Acceptance)**: `search` and `get_talk` MCP tools return correct results against Weaviate.
   - Current: Tools are wired to ChromaDB
   - Target: Tools query Weaviate; `search` returns semantically relevant paragraphs with talk metadata; `get_talk` returns ordered talk text
   - Acceptance (human-gated): Three representative queries return non-empty, correct results; no Weaviate connection errors in server logs

## Boundaries

**In scope:**
- Create `extractors/phase6_weaviate_loader.py`
- Update `scripts/run_pipeline.py` (swap ChromaDB imports → Weaviate loader)
- Replace `CHROMADB_COLLECTION_NAMES` with `WEAVIATE_COLLECTION_NAMES` in `config/pipeline_config.py`
- Update `server.py` (swap ChromaDB client → Weaviate client, update startup validation and health check)
- Delete `config/chromadb_client.py`
- Remove `chromadb` from Pipfile `[packages]`
- Add `weaviate` service to `docker-compose.yml`
- Update `.env.example` (WEAVIATE_* vars in, CHROMADB_* vars out)
- Update CLAUDE.md project structure index (add new file, remove deleted file)

**Out of scope:**
- `loaders/chromadb_loader.py` — benchmark infrastructure; stays untouched
- `benchmark/` directory — benchmark infra; no changes
- `infra/docker-compose.vector-dbs.yml` — benchmark stack; no changes
- Docker image rebuild and push — user's responsibility; Phase 24 delivers code changes only
- `tests/test_phase6.py`, `tests/test_phase6_orchestrator.py` — test updates deferred unless they block `pipenv run py -m pytest` across the suite; if blocking, update minimally to fix import errors only
- Weaviate schema migration tooling — schema was finalized in Phase 21/23; no schema changes
- Re-embedding — same `nomic-embed-text` model used in benchmark and migration
- Auth changes — ScaleKit/OAuth configuration unchanged
- Migrating SQLite — read-only source stays unchanged

## Constraints

- Weaviate service image: `cr.weaviate.io/semitechnologies/weaviate` (use latest stable tag at execution time; benchmark used 1.37.1 as reference)
- Weaviate client requires both HTTP port (8080) and gRPC port (50051) — both must be present in `docker-compose.yml` and `WeaviateLoader.__init__` call
- `extractors/phase6_weaviate_loader.py` must expose `load_talk_bundles()` and `TalkBundle` to match the interface `run_pipeline.py` expects (minimizes diff to pipeline orchestrator)
- `WEAVIATE_COLLECTION_NAMES` values must match `WeaviateLoader.COLLECTIONS` exactly — both are updated to `["ConferenceTalks", "ConferenceTalkParagraphs", "ConferenceTalkCitations", "ConferenceTalkFootnotes"]` (D-18, decided post-SPEC; overrides original benchmark names)
- `chromadb` may remain in Pipfile dev/test dependencies if `tests/test_phase6.py` requires it; it must be removed from `[packages]` (production)

## Acceptance Criteria

- [ ] `python -c "from extractors.phase6_weaviate_loader import load_talk_bundles, TalkBundle"` exits 0
- [ ] `grep -i "chromadb" scripts/run_pipeline.py` → no matches
- [ ] `pipenv run py scripts/run_pipeline.py --help` exits 0
- [ ] `python -c "from config.pipeline_config import WEAVIATE_COLLECTION_NAMES"` exits 0
- [ ] `python -c "from config.pipeline_config import CHROMADB_COLLECTION_NAMES"` raises `ImportError`
- [ ] `grep -i "chromadb" server.py` → no matches
- [ ] `GET /health` returns 200 with Weaviate status field
- [ ] `ls config/chromadb_client.py` → file not found
- [ ] `grep "chromadb" Pipfile` → no match in `[packages]` section
- [ ] `grep "qdrant" Pipfile` → no match in `[packages]` section
- [ ] `docker compose config` parses without error; `weaviate` service present in output
- [ ] `.env.example` has `WEAVIATE_HOST`, `WEAVIATE_PORT`, `WEAVIATE_GRPC_PORT`; no `CHROMADB_*` lines
- [ ] (Human-gated) Full pipeline run completes; Weaviate Paragraph collection count ≥ 5,838
- [ ] (Human-gated) Three MCP `search` + `get_talk` queries return non-empty correct results

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                               |
|--------------------|-------|------|--------|-----------------------------------------------------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | Full Weaviate migration + ChromaDB removal confirmed |
| Boundary Clarity   | 0.90  | 0.70 | ✓      | loaders/chromadb_loader.py kept; image rebuild out of scope |
| Constraint Clarity | 0.80  | 0.65 | ✓      | Weaviate image source, gRPC port, interface contract |
| Acceptance Criteria| 0.82  | 0.70 | ✓      | 11 automated + 2 human-gated criteria               |
| **Ambiguity**      | 0.136 | ≤0.20| ✓      |                                                     |

## Interview Log

| Round | Perspective     | Question summary                              | Decision locked                                                |
|-------|-----------------|-----------------------------------------------|----------------------------------------------------------------|
| 1     | Researcher      | Pipeline approach: new loader vs benchmark runner? | Create extractors/phase6_weaviate_loader.py (new production loader) |
| 1     | Researcher      | ChromaDB removal depth?                       | Full removal — Pipfile, config/chromadb_client.py, all CHROMADB_* refs |
| 2     | Researcher      | Docker stack scope?                           | Add Weaviate service + update .env.example; image rebuild is user's job |
| 2     | Simplifier      | Fresh pipeline re-run required?               | Yes, human-gated — runs via new run_pipeline.py to prove MIGR-01 |
| 3     | Boundary Keeper | Collection name constants strategy?           | Replace CHROMADB_COLLECTION_NAMES with WEAVIATE_COLLECTION_NAMES in pipeline_config.py |
| 3     | Boundary Keeper | loaders/chromadb_loader.py fate?              | Keep — benchmark infrastructure, out of scope                  |

---

*Phase: 24-production-migration*
*Spec created: 2026-05-08*
*Next step: /gsd-discuss-phase 24 — implementation decisions (how to build what's specified above)*
