---
gsd_state_version: 1.0
milestone: v5.0
milestone_name: Scriptures
status: planning
stopped_at: Phase 25 context gathered
last_updated: "2026-07-03T20:59:45.913Z"
last_activity: 2026-07-03 — v5.0 roadmap written (Phases 25–29, 18 requirements mapped)
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-03)

**Core value:** All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks and discourse.
**Current focus:** v5.0 Scriptures — roadmap created; ready for Phase 25 planning

## Current Position

Phase: Phase 25 (next — not started)
Plan: —
Status: Roadmap created; ready for planning
Last activity: 2026-07-03 — v5.0 roadmap written (Phases 25–29, 18 requirements mapped)

## Progress Bar

```
Phase 25 [ ] → Phase 26 [ ] → Phase 27 [ ] → Phase 28 [ ] → Phase 29 [ ]
0 / 5 phases complete
```

## Next Steps

Run `/gsd-plan-phase 25` to plan Phase 25: Data Model, Book Resolver & Extraction.

## Accumulated Context

### Roadmap Evolution

- 2026-04-18: v4.0 roadmap created — 5 phases (20–24), 16 requirements mapped
- Phase 22.1 inserted after Phase 22: address Recall@k = 0.0 bug (URGENT)
- Phase 22.2 inserted after Phase 22.1: optimize benchmark loaders for efficiency (URGENT)
- 2026-07-02: v4.0 archived — ROADMAP.md collapsed, REQUIREMENTS.md removed
- 2026-07-03: v5.0 roadmap created — 5 phases (25–29), 18 requirements mapped

### Key Decisions (v5.0)

- Phase structure mirrors SPEC §13 exactly: 5 phases 1→2→3→4→5 mapped to 25→29
- book_resolver (Phase 25) is the shared dependency reused by both the pipeline (Phase 27) and MCP tools (Phase 28)
- Phases 25–26 are pure/offline (no Weaviate, no Ollama) and fully unit-testable
- Phase 28 can be built and tested against a Phase-27 subset before the Phase-29 full load
- No UI phases — all work is backend pipeline + MCP server

### Key Decisions (v4.0)

- Weaviate selected over ChromaDB and Qdrant based on full benchmark data (serial p50 42ms, filtered p50 51ms, recall@k10=0.9875)
- AppContext holds only weaviate.WeaviateClient — collections.use() called inline per tool call (D-02)
- doc_id_str as TEXT property in Weaviate schemas — ensures stable set-intersection key for recall computation (Phase 22.1 fix)
- CHROMADB_COLLECTION_NAMES retained in pipeline_config.py for backward compat with verify_chromadb_pipeline.py

### Blockers

None.

### Session

**Last session:** 2026-07-03T20:59:45.903Z
**Stopped at:** Phase 25 context gathered

## Session

**Last session:** 2026-07-03T20:59:45.903Z
**Stopped at:** Phase 25 context gathered
**Resume file:** .planning/phases/25-data-model-book-resolver-extraction/25-CONTEXT.md
