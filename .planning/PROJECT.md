# BYU Scripture Citation Index RAG System

## What This Is

A data pipeline and RAG system that transforms the BYU Scripture Citation Index SQLite database into four Weaviate vector collections optimized for semantic search. Content is exposed via an MCP server to AI clients (e.g., Claude Desktop). The project covers General Conference talks (5,838 GC-only via INNER JOIN) and will expand to Journal of Discourse and the standard LDS scripture canon in future milestones.

## Core Value

All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks and discourse, with full referential integrity between talks, paragraphs, citations, and footnotes.

## Current Milestone: v5.0 Scriptures

**Goal:** Make the LDS scripture canon a first-class searchable corpus alongside conference talks — semantic + hybrid search over verse text, exact-reference retrieval, and grounded composition with the existing talk tools. Sourced entirely from the core DB (`db/core.52.db`); no web scraping.

**Target features:**
- Canonical (`S`) + JST (`J`,`F`) verse extraction from `core.52.db` → clean, canonical `ScriptureVerse` objects (~41,996 canonical + ~31k JST; NULL-`Verse` front matter dropped)
- `config/book_resolver.py` — word↔digit ordinal bridge ("1 Nephi"/"First Nephi"/"1 Ne."), D&C `Sections`→"Doctrine and Covenants" mapping, em-dash mojibake repair; shared by `get_verse` and `search`
- Reference-prefixed windowed embedding on the existing Ollama/nomic stack — `standard` verses get a chapter-clamped neighbor window (`SCRIPTURE_WINDOW_RADIUS`, default 1); JST embedded reference-prefixed but un-windowed (sparse)
- New `ScriptureVerses` Weaviate collection + `ScriptureLoader(BaseLoader)` + `scripts/run_scripture_pipeline.py` (streaming, resume, `--force`)
- New `get_verse` MCP tool (pure filter query, no Ollama); `search` and `corpus_stats` extended to `scripture_verses` (search defaults to `variant=standard`)
- Post-load verification `scripts/verify_weaviate_scripture.py` (SCR-01…06)

**Scope boundary:** v1 = verse text only. Chapter/section headings, summaries, footnote cross-references, Topical Guide, and the verse↔verse graph are all deferred to v2 (a Church-API "study apparatus" milestone). Full spec: `docs/scriptures/SPEC.md`.

## Requirements

### Validated

<!-- v1.0 General Conference Pipeline — shipped 2026-03-27 -->

- ✓ Talk metadata extraction (speaker, title, conference, session, URL) — Phase 1 (brownfield)
- ✓ Paragraph segmentation with position tracking — Phase 2 (brownfield)
- ✓ Citation extraction and parsing (book, chapter, verses, context window) — Phase 3 (brownfield)
- ✓ Footnote extraction and parsing (reference type, context window) — Phase 4 (brownfield)
- ✓ Enrichment, cross-reference linking, and integrity validation — Phase 5 (brownfield)
- ✓ DB Enrichment layer — `talk_metadata` table, backfill scripts, Phase 1 LEFT JOIN, preview cache (4,006 entries) — v1.0
- ✓ Code quality — `config/pipeline_config.py` centralized constants, logging standardized, codebase clutter removed — v1.0
- ✓ Phase 1–5 extractors: all 15 known bugs diagnosed, fixed at root cause, regression tests added — v1.0
- ✓ Test coverage — integration tests (5 talks, all phases), schema validation gate, Phase 1 edge cases, Phase 5 adversarial inputs — v1.0
- ✓ Phase 6 ChromaDB loader — transform validated records into 4 collections, annotation handling, batch insert, verify — v1.0
- ✓ Full pipeline orchestrator — `scripts/run_pipeline.py`, skip-if-processed, `--force`, 1000-talk write buffer — v1.0
- ✓ Full pipeline run — 5,838 GC talks processed, resumable, idempotent — v1.0
- ✓ Post-run verification — record counts, semantic search, metadata filters, FK integrity — all passed — v1.0
- ✓ Topic metadata enrichment — `TalkMetadata.topics: List[str]`, GROUP_CONCAT subquery, Phase 6 doc text, ChromaDB metadata — v1.0

<!-- v2.0 MCP Server — shipped 2026-04-03 -->

- ✓ MCP server foundation — FastMCP server with lifespan startup validation (ChromaDB path resolution, Ollama health check, 4-collection warmup, stderr-only logging) — Phase 9 (v2.0)
- ✓ Paragraph metadata enrichment — `prepare_paragraph_records()` injects `speaker_name`, `title`, `conference_year`, `conference_month` into ChromaDB paragraph metadata; VER-06 coverage check added — Phase 9.1 (v2.0)
- ✓ MCP server with `search` tool — semantic search + metadata filters across 4 collections, speaker post-filter, collection validation — Phase 10 (v2.0)
- ✓ MCP server with `get_talk` tool — full ordered talk content by ID, paragraphs sorted by paragraph_number — Phase 10 (v2.0)
- ✓ Concise tool descriptions — minimal token overhead — Phase 11 (v2.0)
- ✓ System prompt priming Claude to engage conversationally, not just retrieve — Phase 11 (v2.0)
- ✓ Claude Desktop config wired and working end-to-end — Phase 11 (v2.0)
- ✓ Tech debt cleanup — all 4 phase VALIDATION.md files Nyquist-compliant, SUMMARY frontmatter complete, OLLAMA_URL single-source consolidated — Phase 12 (v2.0)

<!-- v3.0 Remote MCP — shipped 2026-04-17 -->

- ✓ Streamable HTTP transport replacing stdio — `MCP_HOST`/`MCP_PORT` env vars, `GET /health` with live Ollama + ChromaDB checks — Phase 13 (v3.0)
- ✓ Docker Compose deployment — Dockerfile (python:3.12-slim), docker-compose.yml (bind mounts, healthcheck, env_file), .env.example, requirements.txt pinned from Pipfile.lock — Phase 15 (v3.0)
- ✓ Caddy reverse proxy for TLS termination + Cloudflare Tunnel for stable public URL (home IP hidden) — Phase 16 (v3.0)
- ✓ OAuth 2.1 via ScaleKit — native FastMCP server with two-mode ScalekitProvider auth (local passthrough / remote OAuth); Auth0 fallback path removed; 449 tests green — Phases 16.1, 16.2, 18, 19 (v3.0)
- ✓ Operator docs — connection guide, self-deploy guide, root README entry point — Phase 17 (v3.0)

### Validated (v4.0 — Vector DB Migration)

- ✓ Benchmark framework — `loaders/shared_transforms.py` (flatten_metadata, rich_metadata, prepare_*), `benchmark/metrics.py` (4 dataclasses + recall_at_k), `benchmark/queries.py` (8 canonical queries), `infra/docker-compose.vector-dbs.yml` (ChromaDB 1.5.7, Weaviate 1.37.1, Qdrant v1.17.1) — Phase 20 (v4.0)
- ✓ DB loaders — ChromaDB, Weaviate, and Qdrant loaders each accept a talk bundle and persist it correctly — Phase 21 (v4.0)
- ✓ Benchmark runner — `benchmark/runner.py` CLI orchestrates full benchmark run and emits structured JSON reports; recall@k bug fixed (ChromaDB phantom collection + Weaviate UUID fallback); Weaviate and Qdrant recall@k10=1.0 confirmed on smoke test — Phases 22, 22.1 (v4.0)
- ✓ Benchmark efficiency — `embed_batch()` batches all embed calls per talk (1 Ollama call vs N); `shared_transforms.py` collect-embed-distribute pattern; `WeaviateLoader` uses `insert_many`; `runner.py` upsert parallelized with ThreadPoolExecutor (thread-local loaders, `--workers` default 4); smoke test confirmed all 3 DBs exceed pre-22.2 rps baselines — Phase 22.2 (v4.0)
- ✓ Full benchmark run — 5,838 talks loaded into all 3 DBs; Weaviate wins: serial p50 42ms, filtered p50 51ms (4× faster than ChromaDB/Qdrant), cold-start 34ms, throughput 215 q/s, recall@k10=0.9875 — Phase 23 (v4.0)
- ✓ Decision report — `benchmark/DECISION.md` names Weaviate as winner; full comparison table with real numbers; recall@k framed as ANN fidelity — Phase 23 (v4.0)
- ✓ Production migration — ChromaDB removed; Weaviate in server.py (native filters, startup validation, health check), run_pipeline.py, and Docker stack; verify_weaviate_pipeline.py with VER-01–VER-05 — Phase 24 (v4.0)
- ✓ MCP server smoke test — `search` and `get_talk` tools verified end-to-end on Weaviate; 44 server tests green — Phase 24 (v4.0)

### Active (v5.0 — Scriptures)

<!-- Building toward these. Full requirements in REQUIREMENTS.md. -->

- [ ] Scripture verse extraction — canonical (`S`) + JST (`J`,`F`) from `core.52.db`, NULL-`Verse` front matter excluded, UTF-8 decode, HTML + name-encoding cleanup
- [ ] `book_resolver` — canonical digit-form names, word↔digit ordinals, D&C mapping, em-dash repair; shared by `get_verse` and `search`
- [ ] Windowing + validation — `standard` neighbor window / JST reference-prefix-only; per-verse and per-chapter sanity checks
- [ ] `ScriptureLoader` + `ScriptureVerses` collection + `run_scripture_pipeline.py` — idempotent, resumable, `--force`
- [ ] `get_verse` MCP tool + `search`/`corpus_stats` extension to `scripture_verses`
- [ ] Full load + post-load verification (SCR-01…06)

### Out of Scope

- Scripture study apparatus — headings, chapter summaries, footnote cross-refs, Topical Guide, verse↔verse graph — deferred to v2 (requires Church-API scrape; none exists in `core.db`)
- Official Declarations & other verse-less canonical front matter — v2 candidate, not a v1 verse (NULL `Verse`)
- Late chunking / embedding-model swap / multi-model routing — parked in `backlog.md`; non-blocking for v1 (stay on nomic)
- Remote/mobile access — delivered in v3.0
- Journal of Discourse content — future milestone
- Web scraping — content is read from SQLite only, no live fetching
- Multi-user / hosted deployment — personal use only

## Current State: v4.0 Shipped 2026-07-02

**Delivered:** Evaluated ChromaDB, Weaviate, and Qdrant against the 5,838-talk corpus; migrated production MCP server, pipeline, and Docker stack to Weaviate.

**What shipped:**
- Benchmark framework (shared transforms, loaders, metrics, canonical queries, runner CLI)
- Full benchmark run with structured comparison report (`benchmark/DECISION.md`)
- Production migration of server, pipeline loader, and Docker stack to Weaviate
- End-to-end MCP server smoke test verified on Weaviate

## Context

- **Data source**: BYU Scripture Citation Index SQLite database (5,838 General Conference talks via INNER JOIN conference_talk — GC-only, verified)
- **Current state (v4.0 shipped 2026-07-02)**: Weaviate in production; ChromaDB removed from all production paths; 44 server tests green; 5,838 talks loaded and searchable via MCP tools; server live at lds-sci.williambjensen.com; Claude Desktop connects via OAuth 2.1 handshake
- **Architecture**: Layered, configuration-driven (`config/pipeline_config.py`), typed dataclasses, pure functions, idempotent; fail-fast (schema validation) + fail-safe (FK spot-check) hybrid; MCP server as read-only consumer of Weaviate
- **Processing model**: Per-talk streaming loop — Phases 1–6 run sequentially per talk; WeaviateLoader batch inserts via `insert_many()`; `embed_batch()` makes one Ollama call per talk bundle
- **ID strategy**: Existing SQLite primary keys (`talk_8820`, `para_156789`, etc.) for bidirectional lookups; Weaviate UUIDs derived via `generate_uuid5` + stored `doc_id_str` for set-intersection lookups
- **MCP server**: Native FastMCP 3.2.4 server with two-mode ScalekitProvider auth — local mode (no SCALEKIT_ vars) passes all requests unauthenticated; remote mode (SCALEKIT_ENVIRONMENT_URL + SCALEKIT_RESOURCE_ID + MCP_BASE_URL set) validates OAuth JWTs; `GET /health` returns live Ollama + Weaviate status
- **Deployment**: Dockerfile (python:3.12-slim), docker-compose.yml (single mcp-server service with Weaviate, bind mounts, healthcheck), infra/docker-compose.yml (Caddy + cloudflared), .env.example (updated for Weaviate vars); full stack starts with `docker compose up` in each directory

## Constraints

- **Tech stack**: Python (pipenv), Weaviate v4 client, SQLite — ChromaDB removed from production (retained in benchmark tooling)
- **Pattern consistency**: New phases must follow the patterns established in Phases 1–5 (layered architecture, dataclasses, same logging/error handling strategy)
- **Database**: Read-only from SQLite; all output goes to Weaviate
- **Idempotency**: Pipeline must be safe to re-run; supports skip-if-processed and force-reprocess modes
- **Scale**: 5,838 GC talks × ~35 paragraphs each (202,175 total); batch sizes must manage memory

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| General Conference first | Largest and most structured content type; proves the pipeline before expanding | ✓ Complete — 5,838 talks loaded and verified |
| Bug-fix phase before Phase 6 | Broken extractors produce bad data; fix before loading to ChromaDB | ✓ Good — Phase 3 bugs fixed before load |
| MCP server as separate milestone | Pipeline correctness must be verified before building search layer on top | ✓ Good — Milestone 1 complete, ready for Milestone 2 |
| 4 ChromaDB collections | Talks, paragraphs, citations, footnotes — separate by semantic role | ✓ Good — 5,838 talks / 202,175 paras / 67,307 citations / 25,608 footnotes |
| Paragraph-level chunking | Preserves natural document structure; typical 200–800 tokens | ✓ Good |
| FastMCP lifespan over __main__ startup | Cleaner lifecycle integration; startup errors surface before any tool call | ✓ Good — all 4 collections warm before first request |
| Paragraph metadata denormalized at load time | Eliminates secondary ChromaDB lookup per search result | ✓ Good — Phase 9.1 insertion; VER-06 documents user --force re-run expectation |
| Speaker filtering as Python post-filter | ChromaDB 1.5.5 metadata string filters silently broken | ✓ Good — workaround documented; pre-fetch 4× limit compensates |
| Two-layer prompting (instructions + system prompt) | FastMCP instructions cover tool-level behavior; SYSTEM_PROMPT.md covers persona and synthesis style | ✓ Good — Claude engages conversationally without prompting |
| Streamable HTTP over stdio | Enable remote clients; stdio is local-only and incompatible with Docker networking | ✓ Good — any MCP client connects via URL |
| Single mcp-server Compose service (no managed Ollama) | Ollama GPU access is host-managed; containers can't easily access host GPU | ✓ Good — operator manages Ollama separately |
| infra/ as separate Compose stack for Caddy + cloudflared | Proxy stack is independent of app stack; can restart independently | ✓ Good — clean separation, external Docker network |
| ScaleKit over Auth0 for OAuth 2.1 | ScaleKit has native FastMCP integration via built-in ScalekitProvider; Auth0 required manual JWT wiring | ✓ Good — FastAPI/JSON-RPC dispatcher removed entirely |
| Two-mode auth (local passthrough / remote OAuth) | Local dev needs no auth; production needs OAuth; one binary serves both | ✓ Good — SCALEKIT_ env vars determine mode at startup |
| doc_id_str as TEXT property in Weaviate schemas (Phase 22.1) | Weaviate query() was falling back to UUID strings which never match ChromaDB's para_N baseline IDs; storing doc_id_str alongside the UUID gives a stable set-intersection key | ✓ Good — recall@k10=0.0 → 1.0 after fix |
| ChromaDB collection name resolution in query() (Phase 22.1) | Short keys like "paragraphs" must be resolved through CHROMADB_COLLECTION_NAMES before calling get_or_create_collection, otherwise a phantom empty collection is silently created | ✓ Good — phantom collection creation eliminated |
| Runner baseline collected after ChromaDB populates (Phase 22.1) | On a fresh stack, collecting the baseline before the ChromaDB benchmark loop runs guarantees an empty baseline and 0.0 recall for all comparators | ✓ Good — ordering fix ensures correct recall on fresh stacks |
| Weaviate selected as production DB (Phase 23) | Serial p50 42ms, filtered p50 51ms (4× faster than ChromaDB/Qdrant), cold-start 34ms, memory delta 0.02 MB, recall@k10=0.9875 — decisive on all dimensions for MCP use | ✓ Good — production migration complete |
| AppContext holds only weaviate.WeaviateClient, no collections dict (Phase 24) | collections.use() called inline per tool call — simpler than pre-warming a dict; matches Weaviate v4 client idiom | ✓ Good — 44 server tests green |
| weaviate.connect_to_embedded() unsupported on Windows (Phase 24-05) | gh#3315 — tests use platform-conditional fixture with MagicMock fallback on Windows | ✓ Good — CI passes on all platforms |
| CHROMADB_COLLECTION_NAMES retained in pipeline_config.py (Phase 24-09) | backward compat for verify_chromadb_pipeline.py — production uses Weaviate; comment explains the dual-path | ✓ Good — backward compat without ambiguity |

---
## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-03 — v5.0 Scriptures milestone started (verse-only searchable corpus from core.52.db; see docs/scriptures/SPEC.md)*
