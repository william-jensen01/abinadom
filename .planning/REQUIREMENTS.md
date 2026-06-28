# Requirements — v4.0 Vector DB Migration

## Milestone v4.0 Requirements

### Benchmark Framework

- [ ] **BENCH-01**: User can transform talk data into ChromaDB-safe flat metadata and native rich metadata via shared `flatten_metadata` / `rich_metadata` / `prepare_*` functions
- [ ] **BENCH-02**: User can load talk bundles into a benchmark ChromaDB instance via a benchmark-specific ChromaDB loader
- [ ] **BENCH-03**: User can load talk bundles into Weaviate (with schema creation and UUID mapping) via a Weaviate loader
- [ ] **BENCH-04**: User can load talk bundles into Qdrant (with collection creation and payload indexes) via a Qdrant loader
- [ ] **BENCH-05**: User can measure upsert speed, query latency (p50/p95/p99), concurrency throughput, and memory delta via metric dataclasses and `recall_at_k`
- [ ] **BENCH-06**: User can run a canonical query set (paragraph + citation queries with and without filters) as the standard workload for all three DBs
- [ ] **BENCH-07**: User can run the full benchmark from CLI (`benchmark/runner.py`) and receive a structured JSON report

### Evaluation

- [ ] **EVAL-01**: User can start ChromaDB, Weaviate, and Qdrant locally via a single Docker Compose file
- [x] **EVAL-02**: User can run a full benchmark (upsert, query latency, concurrency, memory) against all three DBs in a single command
- [x] **EVAL-03**: Each DB is fully populated with all 5,838 talks before query and concurrency benchmarks run, ensuring comparable results
- [x] **EVAL-04**: User can see recall@k10 and recall@k50 comparing Weaviate vs ChromaDB and Qdrant vs ChromaDB
- [x] **EVAL-05**: User can read a written decision report identifying the winning DB with rationale

### Migration

- [x] **MIGR-01**: User can run the full pipeline against the winning DB via an updated `scripts/run_pipeline.py` (Phase 6 loader swapped)
- [x] **MIGR-02**: MCP server uses the winning DB client at runtime (server.py startup validation updated)
- [x] **MIGR-03**: Production Docker Compose stack uses the winning DB service (docker-compose.yml updated, .env.example reflects new vars)
- [ ] **MIGR-04**: Winning DB is populated with all 5,838 GC talks and MCP `search` + `get_talk` tools verified end-to-end

## Future Requirements

- Journal of Discourse and scriptures content — future milestones
- Multi-user / hosted deployment support
- Re-embedding with an updated model (if nomic-embed-text is superseded)

## Out of Scope

- Supporting multiple vector DBs in production simultaneously — one DB in production at a time; ChromaDB removed after migration
- Re-embedding — same Ollama nomic-embed-text model used throughout benchmark and migration
- Migrating SQLite — read-only source of truth stays unchanged
- Journal of Discourse or scriptures content — future milestones

## Traceability

| REQ-ID   | Phase | Notes |
|----------|-------|-------|
| BENCH-01 | 20    | Shared transforms — foundation for all loaders |
| BENCH-02 | 21    | ChromaDB benchmark loader |
| BENCH-03 | 21    | Weaviate loader (schema + UUID + batch) |
| BENCH-04 | 21    | Qdrant loader (collections + payload indexes) |
| BENCH-05 | 20    | Metrics dataclasses + recall_at_k |
| BENCH-06 | 20    | Canonical query set |
| BENCH-07 | 22    | benchmark/runner.py CLI |
| EVAL-01  | 20    | Docker Compose for all 3 DBs |
| EVAL-02  | 23    | Full benchmark run in one command |
| EVAL-03  | 23    | Load gate — all 5,838 talks before query benchmarks |
| EVAL-04  | 23    | recall@k10 and recall@k50 comparisons |
| EVAL-05  | 23    | Written decision report with winner + rationale |
| MIGR-01  | 24    | scripts/run_pipeline.py Phase 6 loader swapped |
| MIGR-02  | 24    | server.py winning DB client + startup validation |
| MIGR-03  | 24    | docker-compose.yml + .env.example updated |
| MIGR-04  | 24    | Full pipeline re-run + MCP smoke test |
