# Roadmap — BYU Scripture Citation Index RAG System

## Milestones

- ✅ **v1.0 General Conference Pipeline** — Phases 1–8 (shipped 2026-03-27)
- ✅ **v2.0 MCP Server** — Phases 9–12 (shipped 2026-04-03)
- ✅ **v3.0 Remote MCP** — Phases 13–19 (shipped 2026-04-17)
- 🔄 **v4.0 Vector DB Migration** — Phases 20–24 (in progress)

## Phases

<details>
<summary>✅ v1.0 General Conference Pipeline (Phases 1–8) — SHIPPED 2026-03-27</summary>

- [x] Phase 1: DB Enrichment (5/5 plans) — completed 2026-03-20
- [x] Phase 2: Code Quality (2/2 plans) — completed 2026-03-21
- [x] Phase 3: Bug Audit & Fixes (3/3 plans) — completed 2026-03-22
- [x] Phase 4: Test Coverage (3/3 plans) — completed 2026-03-24
- [x] Phase 5: ChromaDB Loader (3/3 plans) — completed 2026-03-25
- [x] Phase 6: Pipeline Orchestrator (2/2 plans) — completed 2026-03-26
- [x] Phase 7: Full Run & Verification (2/2 plans) — completed 2026-03-27
- [x] Phase 8: Topic Metadata (1/1 plan) — completed 2026-03-27

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v2.0 MCP Server (Phases 9–12) — SHIPPED 2026-04-03</summary>

- [x] Phase 9: Server Foundation (1/1 plans) — completed 2026-04-02
- [x] Phase 9.1: Paragraph Metadata Enrichment (1/1 plans) — completed 2026-04-02
- [x] Phase 10: Tools & Normalization (2/2 plans) — completed 2026-04-02
- [x] Phase 11: Claude Desktop Integration (2/2 plans) — completed 2026-04-03
- [x] Phase 12: Tech Debt & Validation Cleanup (1/1 plans) — completed 2026-04-03

Full details: `.planning/milestones/v2.0-ROADMAP.md`

</details>

<details>
<summary>✅ v3.0 Remote MCP (Phases 13–19) — SHIPPED 2026-04-17</summary>

- [x] Phase 13: HTTP Transport (2/2 plans) — completed 2026-04-03
- [x] Phase 14: Auth Module (3/3 plans) — completed 2026-04-04
- [x] Phase 15: Docker Compose & Config (2/2 plans) — completed 2026-04-04
- [x] Phase 16: Caddy & Cloudflare Tunnel (2/2 plans) — completed 2026-04-05
- [x] Phase 16.1: OAuth 2.0 for Claude Desktop (5/5 plans) — completed 2026-04-13
- [x] Phase 16.2: FastAPI MCP Protocol Rewrite (2/2 plans) — completed 2026-04-09
- [x] Phase 17: Operator Docs (4/4 plans) — completed 2026-04-13
- [x] Phase 18: Cleanup of Previous Phases (3/3 plans) — completed 2026-04-14
- [x] Phase 19: FastMCP + ScaleKit Server (3/3 plans) — completed 2026-04-16

Full details: `.planning/milestones/v3.0-ROADMAP.md`

</details>

## v4.0 Vector DB Migration (In Progress)

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 20 | Benchmark Infrastructure & Framework | 4/4 | Complete    | 2026-04-20 |
| 21 | DB Loaders | 5/5 | Complete   | 2026-04-22 |
| 22 | Benchmark Runner | 3/3 | Complete | 2026-04-25 |
| 23 | Benchmark Execution & Decision | All three DBs fully loaded and benchmarked; decision report names the winning DB | EVAL-02, EVAL-03, EVAL-04, EVAL-05 | 4 |
| 24 | Production Migration | Production MCP server, pipeline loader, and Docker stack run on the winning DB; all 5,838 talks loaded and search verified | MIGR-01, MIGR-02, MIGR-03, MIGR-04 | 4 |

- [x] **Phase 20: Benchmark Infrastructure & Framework** — Docker Compose for all 3 DBs running locally; shared transform, metrics, and canonical query modules ready (completed 2026-04-20)
- [x] **Phase 21: DB Loaders** — ChromaDB, Weaviate, and Qdrant loaders each accept a talk bundle and persist it correctly (completed 2026-04-22)
- [x] **Phase 22: Benchmark Runner** — `benchmark/runner.py` CLI orchestrates a full benchmark run and emits a structured JSON report (completed 2026-04-24)
- [ ] **Phase 23: Benchmark Execution & Decision** — Full benchmark run completes; recall@k computed; written decision report names the winner
- [ ] **Phase 24: Production Migration** — Pipeline loader, MCP server, and Docker stack all running on the winning DB with all 5,838 talks loaded

### Phase Details

#### Phase 20: Benchmark Infrastructure & Framework
**Goal**: Developer can start all three vector DBs locally and has shared code (transforms, metrics, canonical queries) that all loaders and the runner will depend on
**Depends on**: Phase 19 (v3.0 shipped)
**Requirements**: EVAL-01, BENCH-01, BENCH-05, BENCH-06
**Success Criteria** (what must be TRUE):
  1. `docker compose up` in the benchmark directory starts ChromaDB, Weaviate, and Qdrant with no errors and all three pass a health check
  2. `flatten_metadata` and `rich_metadata` (and `prepare_*` variants) are callable and produce the correct output shape for a sample talk bundle
  3. Metric dataclasses and `recall_at_k` are importable and return correct results against a synthetic ranked list
  4. Canonical query set is loadable as a Python list and covers both paragraph and citation queries, with and without metadata filters
**Plans**: 4 plans
Plans:
- [x] 20-01-PLAN.md — Package markers + Wave 0 test stubs (test_shared_transforms.py, test_metrics.py) — completed 2026-04-20
- [x] 20-02-PLAN.md — loaders/shared_transforms.py extraction + phase6 import delegation
- [x] 20-03-PLAN.md — benchmark/metrics.py + benchmark/queries.py
- [x] 20-04-PLAN.md — infra/docker-compose.vector-dbs.yml (3-DB stack)
**UI hint**: no

#### Phase 21: DB Loaders
**Goal**: Each of the three vector DBs has a dedicated loader that accepts a talk bundle and writes it to the DB using the shared transforms from Phase 20
**Depends on**: Phase 20
**Requirements**: BENCH-02, BENCH-03, BENCH-04
**Success Criteria** (what must be TRUE):
  1. ChromaDB benchmark loader inserts a sample talk bundle and a subsequent query returns the expected paragraph record
  2. Weaviate loader creates the schema, maps UUIDs, and batch-loads a sample talk bundle; a query returns the expected record
  3. Qdrant loader creates the collection, sets payload indexes, and batch-loads a sample talk bundle; a query returns the expected record
**Plans**: 5 plans
Plans:
- [x] 21-01-PLAN.md — Wave 0: Pipfile deps + test_phase6.py unpack fixes + test infrastructure stubs — completed 2026-04-22
- [x] 21-02-PLAN.md — Wave 1: shared_transforms 4-element tuples + _rich variants + BaseLoader ABC + embeddings.py — completed 2026-04-22
- [x] 21-03-PLAN.md — Wave 2: loaders/chromadb_loader.py (ChromaDBLoader)
- [x] 21-04-PLAN.md — Wave 2: loaders/weaviate_loader.py (WeaviateLoader)
- [x] 21-05-PLAN.md — Wave 2: loaders/qdrant_loader.py (QdrantLoader)
**UI hint**: no

#### Phase 22: Benchmark Runner
**Goal**: Developer can run a single CLI command against any of the three DBs and receive a structured JSON report covering all metric dimensions
**Depends on**: Phase 21
**Requirements**: BENCH-07
**Success Criteria** (what must be TRUE):
  1. `python benchmark/runner.py --help` shows the expected arguments (DB targets, upsert-limit, query-limit, output path)
  2. Running the runner with `--upsert-limit 10 --query-limit 10` against a single DB completes without error and writes a JSON file with upsert speed, p50/p95/p99 latency, concurrency throughput, and memory delta fields
  3. Running the runner against all three DBs produces three comparable JSON report files with identical schema
  4. With a small dataset, the runner enforces the load gate — upsert phase completes before any query benchmarks execute; no query is issued before all target talks are loaded
**Plans**: 3 plans
Plans:
- [x] 22-01-PLAN.md — Wave 1: Pipfile psutil + ScalabilityCurveEntry dataclass in benchmark/metrics.py — completed 2026-04-24
- [x] 22-02-PLAN.md — Wave 2: BenchmarkRunner class with all 10 measurement methods in benchmark/runner.py
- [x] 22-03-PLAN.md — Wave 3: run_all() + main() CLI entrypoint + _write_report() + multi-DB orchestration — completed 2026-04-24
**UI hint**: no

### Phase 22.1: address Recall@k = 0.0 bug (INSERTED)

**Goal:** Fix two root-cause bugs causing recall@k10 and recall@k50 to report 0.0 for Weaviate and Qdrant, confirmed by a local smoke test
**Requirements**: REQ-22.1-1, REQ-22.1-2, REQ-22.1-3, REQ-22.1-4
**Depends on:** Phase 22
**Plans:** 3 plans

Plans:
- [ ] 22.1-01-PLAN.md — Wave 1: Fix ChromaDBLoader.query() — resolve collection name through CHROMADB_COLLECTION_NAMES (Bug 1)
- [ ] 22.1-02-PLAN.md — Wave 1: Fix WeaviateLoader — add doc_id_str schema property, store in load(), return in query() (Bug 2)
- [ ] 22.1-03-PLAN.md — Wave 2: Smoke test (--upsert-limit 10 --query-limit 10 --db all) confirming non-zero recall

#### Phase 23: Benchmark Execution & Decision
**Goal**: All three DBs are fully loaded with 5,838 talks, benchmarks have run across all metric dimensions, recall@k is computed, and a written decision report names the winning DB with rationale
**Depends on**: Phase 22
**Requirements**: EVAL-02, EVAL-03, EVAL-04, EVAL-05
**Success Criteria** (what must be TRUE):
  1. A single command triggers the full benchmark pipeline (upsert, latency, concurrency, memory) against all three DBs and completes without manual intervention
  2. All three DBs show 5,838 talks loaded before any query or concurrency benchmarks execute (load gate enforced in runner)
  3. recall@k10 and recall@k50 scores are present in the JSON report for Weaviate vs ChromaDB and Qdrant vs ChromaDB comparisons
  4. A written decision report (`docs/benchmark/DECISION.md` or equivalent) identifies the winning DB, shows the structured comparison table, and states the rationale
**Plans**: TBD
**UI hint**: no

#### Phase 24: Production Migration
**Goal**: The production MCP server, the full pipeline, and the Docker deployment stack all run on the winning vector DB; the old ChromaDB dependency is removed; all 5,838 GC talks are searchable via MCP tools
**Depends on**: Phase 23
**Requirements**: MIGR-01, MIGR-02, MIGR-03, MIGR-04
**Success Criteria** (what must be TRUE):
  1. `scripts/run_pipeline.py` completes a full 5,838-talk pipeline run writing to the winning DB with no ChromaDB references remaining in the Phase 6 loader path
  2. `server.py` starts with the winning DB client, passes startup validation, and `GET /health` reports the winning DB as healthy
  3. `docker compose up` in the project root starts the MCP server with the winning DB service; `.env.example` reflects the updated variable contract
  4. `search` and `get_talk` MCP tools return correct results for at least three representative queries against the winning DB
**Plans**: TBD
**UI hint**: no

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 20. Benchmark Infrastructure & Framework | 4/4 | Complete | 2026-04-20 |
| 21. DB Loaders | 5/5 | Complete | 2026-04-22 |
| 22. Benchmark Runner | 3/3 | Complete | 2026-04-24 |
| 22.1. Address Recall@k = 0.0 Bug | 0/3 | Not started | - |
| 23. Benchmark Execution & Decision | 0/TBD | Not started | - |
| 24. Production Migration | 0/TBD | Not started | - |
