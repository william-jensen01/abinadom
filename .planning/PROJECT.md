# BYU Scripture Citation Index RAG System

## What This Is

A data pipeline and RAG system that transforms the BYU Scripture Citation Index SQLite database into four ChromaDB vector collections optimized for semantic search. Content is exposed via an MCP server to AI clients (e.g., Claude Desktop). The project starts with General Conference talks (5,838 GC-only via INNER JOIN) and expands to Journal of Discourse, and the standard LDS scripture canon in future milestones.

## Core Value

All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks and discourse, with full referential integrity between talks, paragraphs, citations, and footnotes.

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

### Active (v4.0 — Next Milestone)

*(No active requirements — define with `/gsd-new-milestone`)*

### Out of Scope

- Remote/mobile access — Milestone 3 (ChromaDB across machines, hosting, auth)
- Journal of Discourse content — Milestone 4
- Scriptures (OT, NT, BOM, D&C, POGP) — Milestone 5+
- Web scraping — HTML is read from SQLite only, no live fetching
- Multi-user / hosted deployment — personal use only

## Current State: v3.0 Shipped — Planning Next Milestone

**v3.0 shipped 2026-04-17.** The server is now a publicly-accessible remote MCP endpoint with OAuth 2.1 auth via ScaleKit, served over HTTPS via Caddy + Cloudflare Tunnel, deployable with `docker compose up`.

**Next:** Run `/gsd-new-milestone` to define v4.0 goals.

## Context

- **Data source**: BYU Scripture Citation Index SQLite database (5,838 General Conference talks via INNER JOIN conference_talk — GC-only, verified)
- **Current state (v2.0)**: Full MCP server shipped — FastMCP with startup validation, `search` and `get_talk` tools, Claude Desktop config template, system prompt, 38 server tests green; ChromaDB holds 5,838 talks / 202,175 paragraphs / 67,307 citations / 25,608 footnotes (paragraphs enriched with speaker/title/date metadata)
- **Architecture**: Layered, configuration-driven (`config/pipeline_config.py`), typed dataclasses, pure functions, idempotent; fail-fast (schema validation) + fail-safe (FK spot-check) hybrid; MCP server as read-only consumer of ChromaDB
- **Processing model**: Per-talk streaming loop — Phases 1–6 run sequentially per talk; ChromaDB write buffer flushes every 1,000 talks
- **ID strategy**: Existing SQLite primary keys (`talk_8820`, `para_156789`, etc.) for bidirectional lookups
- **MCP server**: Native FastMCP 3.2.4 server with two-mode ScalekitProvider auth — local mode (no SCALEKIT_ vars) passes all requests unauthenticated; remote mode (SCALEKIT_ENVIRONMENT_URL + SCALEKIT_RESOURCE_ID + MCP_BASE_URL set) validates OAuth JWTs; `GET /health` returns live Ollama + ChromaDB status
- **Deployment**: Dockerfile (python:3.12-slim), docker-compose.yml (single mcp-server service, bind mounts, healthcheck), infra/docker-compose.yml (Caddy + cloudflared), .env.example (7 operator vars); full stack starts with `docker compose up` in each directory
- **Current state (v3.0 shipped 2026-04-17)**: 449 tests green; server live at lds-sci.williambjensen.com; Claude Desktop connects via OAuth 2.1 handshake; FastAPI dependency removed

## Constraints

- **Tech stack**: Python (pipenv), ChromaDB, SQLite — no changes to stack
- **Pattern consistency**: New phases must follow the patterns established in Phases 1–5 (layered architecture, dataclasses, same logging/error handling strategy)
- **Database**: Read-only from SQLite; all output goes to ChromaDB only
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
*Last updated: 2026-04-17 after v3.0 milestone*
