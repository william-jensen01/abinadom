# BYU Scripture Citation Index RAG System

## What This Is

A data pipeline and RAG system that transforms the BYU Scripture Citation Index SQLite database into four ChromaDB vector collections optimized for semantic search. Content is exposed via an MCP server to AI clients (e.g., Claude Desktop). The project starts with General Conference talks (5,838 GC-only via INNER JOIN) and expands to Journal of Discourse, and the standard LDS scripture canon in future milestones.

## Core Value

All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks and discourse, with full referential integrity between talks, paragraphs, citations, and footnotes.

## Requirements

### Validated

<!-- Implemented in Phases 1–5 extractors — existing, brownfield code. -->

- ✓ Talk metadata extraction (speaker, title, conference, session, URL) — Phase 1
- ✓ Paragraph segmentation with position tracking — Phase 2
- ✓ Citation extraction and parsing (book, chapter, verses, context window) — Phase 3
- ✓ Footnote extraction and parsing (reference type, context window) — Phase 4
- ✓ Enrichment, cross-reference linking, and integrity validation — Phase 5

### Active

<!-- Milestone 1: Complete General Conference pipeline end-to-end -->

- [x] DB Enrichment layer — `talk_metadata` table, backfill scripts, Phase 1 LEFT JOIN, preview cache (4,006 entries) — Validated in Phase 01: db-enrichment
- [x] Code quality — `config/pipeline_config.py` centralized constants, logging standardized (no `basicConfig` in extractors), codebase clutter removed (duplicate cache manager, superseded test runner, scripts relocated to `scripts/`) — Validated in Phase 02: code-quality
- [x] Phase 1–5 extractors: all known bugs diagnosed and fixed — Validated in Phase 03: bug-audit-fixes
- [x] Test coverage: integration tests (5 real talks, all phases), schema validation, Phase 1 edge cases, Phase 5 adversarial inputs — Validated in Phase 04: test-coverage
- [x] Phase 6: ChromaDB loader — transform validated records into 4 collections, batch insert, verify — Validated in Phase 05: chromadb-loader
- [x] Full pipeline orchestrator — `scripts/run_pipeline.py`, skip-if-processed default, `--force` override, ChromaDB write buffer (1000 talks/flush), 11 orchestrator tests — Validated in Phase 06: pipeline-orchestrator
- [x] Full pipeline run over all 5,838 General Conference talks, resumable and idempotent — Validated in Phase 07: full-run-verification
- [x] Post-run verification: record counts (VER-01), semantic search (VER-02), metadata filters (VER-03), FK integrity (VER-04) — all passed — Validated in Phase 07: full-run-verification
- [x] Topic metadata enrichment — `TalkMetadata.topics: List[str]`, Phase 1 GROUP_CONCAT subquery, Phase 6 document text and pipe-joined ChromaDB metadata, schema coverage, 12 new tests — Validated in Phase 08: include-topics-in-talk-metadata

### Out of Scope

- MCP server — deferred to Milestone 2 (pipeline must be solid first)
- Journal of Discourse content — Milestone 3
- Scriptures (OT, NT, BOM, D&C, POGP) — Milestone 4+
- Web scraping — HTML is read from SQLite only, no live fetching
- Multi-user / hosted deployment — personal use only

## Context

- **Data source**: BYU Scripture Citation Index SQLite database (5,838 General Conference talks via INNER JOIN conference_talk — GC-only, verified)
- **Existing pipeline**: Phases 1–5 implemented in `extractors/` with typed dataclasses (`models/`), shared HTML utilities (`extractors/html_parsing_utils.py`), and per-phase tests (`tests/`)
- **Known state**: Phases 1–5 have known bugs; Phase 6 (ChromaDB loader) does not yet exist
- **Architecture decisions established**: Layered architecture, configuration-driven schemas, pure functions, typed dataclasses, idempotent design, fail-fast vs fail-safe hybrid (see `docs/PROJECT.md`)
- **Processing model**: Per-talk streaming loop — Phases 1–5 run sequentially per talk; Phase 6 buffers and batch-inserts across talks
- **ID strategy**: Use existing SQLite primary keys (`talk_8820`, `para_156789`, etc.) for bidirectional lookups

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
*Last updated: 2026-03-27 — Phase 08 (include-topics-in-talk-metadata) complete — topic metadata now flows through pipeline*
