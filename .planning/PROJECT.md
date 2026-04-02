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

### Active

<!-- Milestone 2: MCP Server — v2.0 -->

- ✓ MCP server foundation — FastMCP server with lifespan startup validation (ChromaDB path resolution, Ollama health check, 4-collection warmup, stderr-only logging) — Phase 9 (v2.0)
- ✓ Paragraph metadata enrichment — `prepare_paragraph_records()` injects `speaker_name`, `title`, `conference_year`, `conference_month` into ChromaDB paragraph metadata; VER-06 coverage check added — Phase 9.1 (v2.0)
- ✓ MCP server with `search` tool — semantic search + metadata filters across 4 collections, speaker post-filter, collection validation — Phase 10 (v2.0)
- ✓ MCP server with `get_talk` tool — full ordered talk content by ID, paragraphs sorted by paragraph_number — Phase 10 (v2.0)
- [ ] Concise tool descriptions — minimal token overhead
- [ ] System prompt priming Claude to engage conversationally, not just retrieve
- [ ] Claude Desktop config wired and working end-to-end

### Out of Scope

- Remote/mobile access — Milestone 3 (ChromaDB across machines, hosting, auth)
- Journal of Discourse content — Milestone 4
- Scriptures (OT, NT, BOM, D&C, POGP) — Milestone 5+
- Web scraping — HTML is read from SQLite only, no live fetching
- Multi-user / hosted deployment — personal use only

## Context

- **Data source**: BYU Scripture Citation Index SQLite database (5,838 General Conference talks via INNER JOIN conference_talk — GC-only, verified)
- **Current state (v1.0)**: Full 8-phase pipeline shipped — Phases 1–6 extractors bug-free, tested, and loading to ChromaDB; `scripts/run_pipeline.py` orchestrates all 5,838 talks; ChromaDB holds 5,838 talks / 202,175 paragraphs / 67,307 citations / 25,608 footnotes
- **Architecture**: Layered, configuration-driven (`config/pipeline_config.py`), typed dataclasses, pure functions, idempotent; fail-fast (schema validation) + fail-safe (FK spot-check) hybrid
- **Processing model**: Per-talk streaming loop — Phases 1–6 run sequentially per talk; ChromaDB write buffer flushes every 1,000 talks
- **ID strategy**: Existing SQLite primary keys (`talk_8820`, `para_156789`, etc.) for bidirectional lookups
- **Current milestone**: v2.0 MCP Server — local MCP server exposing `search` and `get_talk` tools to Claude Desktop for conversational exploration of GC talks

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

---
## Current Milestone: v2.0 MCP Server

**Goal:** Expose ChromaDB via a local MCP server so Claude Desktop can have rich, conversational exploration of General Conference talks — searching by meaning, reading full talks, discussing LDS teachings as an informed partner.

**Target features:**
- `search` tool: semantic + metadata filters, server-side fuzzy normalization, collection parameter
- `get_talk` tool: full ordered talk content by ID
- Concise tool descriptions — minimal token overhead
- System prompt priming Claude to engage conversationally
- Claude Desktop config wired and working end-to-end

---
*Last updated: 2026-04-02 — Phase 10 complete: search and get_talk MCP tools shipped*
