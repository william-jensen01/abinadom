---
gsd_state_version: 1.0
milestone: v5.0
milestone_name: Scriptures
status: planning
last_updated: "2026-07-03T18:40:42.748Z"
last_activity: 2026-07-03
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-02)

**Core value:** All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks.
**Current focus:** v4.0 shipped — start next milestone with `/gsd-new-milestone`

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-07-03 — Milestone v5.0 started

## Next Steps

Run `/gsd-new-milestone` to define v5.0 goals, requirements, and roadmap.

## Accumulated Context

### Roadmap Evolution

- 2026-04-18: v4.0 roadmap created — 5 phases (20–24), 16 requirements mapped
- Phase 22.1 inserted after Phase 22: address Recall@k = 0.0 bug (URGENT)
- Phase 22.2 inserted after Phase 22.1: optimize benchmark loaders for efficiency (URGENT)
- 2026-07-02: v4.0 archived — ROADMAP.md collapsed, REQUIREMENTS.md removed

### Key Decisions (v4.0)

- Weaviate selected over ChromaDB and Qdrant based on full benchmark data (serial p50 42ms, filtered p50 51ms, recall@k10=0.9875)
- AppContext holds only weaviate.WeaviateClient — collections.use() called inline per tool call (D-02)
- doc_id_str as TEXT property in Weaviate schemas — ensures stable set-intersection key for recall computation (Phase 22.1 fix)
- CHROMADB_COLLECTION_NAMES retained in pipeline_config.py for backward compat with verify_chromadb_pipeline.py

### Session

**Last session:** 2026-07-02
**Stopped at:** Milestone v4.0 archived
