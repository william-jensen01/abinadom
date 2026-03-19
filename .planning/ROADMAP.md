# Roadmap -- BYU Scripture Citation Index RAG System
# Milestone 1: General Conference Pipeline

*Status: In Progress | Started: 2026-03-19*

## Overview

Milestone 1 delivers an end-to-end pipeline that processes all 7,659 General Conference talks from SQLite through Phases 1-6 into four ChromaDB vector collections. The ordering is intentional: restructure the database enrichment layer first (it changes how Phase 1 reads data), clean up tech debt so the codebase is navigable, fix bugs on stable code, lock in test coverage, then build the new ChromaDB loader, wrap it in an orchestrator, and verify the full run.

## Milestone Goal

All 7,659 General Conference talks processed through Phases 1-6 with verified record counts, working semantic search, and full foreign key integrity across all four ChromaDB collections.

## Phase Summary

| Phase | Name | Status | Requirements |
|-------|------|--------|--------------|
| 1 | DB Enrichment | Planning Complete | ENRCH-01, ENRCH-02, ENRCH-03, ENRCH-04, ENRCH-05, ENRCH-06 |
| 2 | Code Quality | Not Started | QUAL-01, QUAL-02, QUAL-03, QUAL-07, QUAL-08, QUAL-09 |
| 3 | Bug Audit & Fixes | Not Started | BUGS-01, BUGS-02, BUGS-03 |
| 4 | Test Coverage | Not Started | QUAL-04, QUAL-05, QUAL-06, QUAL-10 |
| 5 | ChromaDB Loader | Not Started | LOAD-01, LOAD-02, LOAD-03, LOAD-04, LOAD-05, LOAD-06 |
| 6 | Pipeline Orchestrator | Not Started | PIPE-01, PIPE-02, PIPE-03, PIPE-04 |
| 7 | Full Run & Verification | Not Started | VER-01, VER-02, VER-03, VER-04 |

## Phases

### Phase 1 -- DB Enrichment

**Goal:** Restructure metadata storage so Phase 1 reads enriched fields from a dedicated `talk_metadata` table instead of scattered `talks` columns.
**Requirements:** ENRCH-01, ENRCH-02, ENRCH-03, ENRCH-04, ENRCH-05, ENRCH-06
**Depends on:** --
**Plans:** 4 plans

Plans:
- [ ] 01-00-PLAN.md -- Wave 0: create test stubs for enrichment requirements (ENRCH-01, ENRCH-02, ENRCH-04, ENRCH-05, ENRCH-06)
- [ ] 01-01-PLAN.md -- Create talk_metadata table DDL and migrate backfill scripts to write there (ENRCH-01, ENRCH-02, ENRCH-06)
- [ ] 01-02-PLAN.md -- Build and run Church API preview fetcher to populate talk_previews.json (ENRCH-03)
- [ ] 01-03-PLAN.md -- Run backfills to populate talk_metadata, update Phase 1 extractor with LEFT JOIN (ENRCH-04, ENRCH-05)

**Acceptance criteria:**
- [ ] `talk_metadata` table exists with columns `speaker_role_id`, `uri_l`, `uri_gc`, `kicker`, `talk_preview`, `data_aid` and has one row per GC talk
- [ ] No backfill script in `db/one-off-migration/` writes to the `talks` table directly -- all target `talk_metadata`
- [ ] `talk_previews.json` contains preview text for all available GC talks from the Church API
- [ ] Phase 1 extractor output includes enriched fields (`speaker_role_id`, `kicker`, `talk_preview`) when present in `talk_metadata`
- [ ] `talk_topic` and `conference_topic` tables are untouched

---

### Phase 2 -- Code Quality

**Goal:** Clean up tech debt so the codebase is consistent, configurable, and navigable before hunting bugs.
**Requirements:** QUAL-01, QUAL-02, QUAL-03, QUAL-07, QUAL-08, QUAL-09
**Depends on:** Phase 1

#### Plans
1. **Phase 3 citation position refactor** -- Implement ID-based anchor walking per `REFACTOR_CITATION_PARSING.md` to fix duplicate scripture position bugs (QUAL-01)
2. **Config centralization and logging standardization** -- Create `config/pipeline_config.py` with all hardcoded values; standardize logging levels across all phases (QUAL-02, QUAL-03)
3. **Legacy and model cleanup** -- Resolve duplicate cache managers, audit and relocate root-level scripts, remove deprecated Phase 5 model fields (`is_opening`, `is_scripture`, etc.) (QUAL-07, QUAL-08, QUAL-09)

*Plans 1, 2, and 3 are independent of each other and can run in parallel.*

**Acceptance criteria:**
- [ ] Phase 3 extractor produces correct citation positions when the same scripture reference appears multiple times in one paragraph
- [ ] `config/pipeline_config.py` exists and all phases read parser choice, context window size, batch sizes, and regex patterns from it -- no hardcoded magic values in extractor files
- [ ] Logging uses consistent level conventions (documented) across Phases 1-5
- [ ] Exactly one canonical cache manager exists; the other is deleted or archived with a note
- [ ] Root-level scripts (`UPDATE.py`, `process_all.py`, `process_topics.py`, `run_phase2_tests.py`) are each either moved to `scripts/` or documented as active entry points
- [ ] Deprecated Phase 5 model fields (`is_opening`, `is_scripture`, etc.) removed from `models/validation_report.py` and all references updated

---

### Phase 3 -- Bug Audit & Fixes

**Goal:** All known and discovered bugs in Phases 1-5 are identified, fixed at root cause, and covered by regression tests.
**Requirements:** BUGS-01, BUGS-02, BUGS-03
**Depends on:** Phase 2

#### Plans
1. **Bug audit** -- Systematically run sample talks through all phases, identify and catalogue every bug with reproduction steps (BUGS-01)
2. **Bug fixes** -- Fix all catalogued bugs with root-cause fixes (BUGS-02)
3. **Regression tests** -- Add test cases for every fixed bug, including coverage for existing Phase 4 fixes (BUGS-03)

*Plan 1 must complete before Plan 2. Plan 3 can partially overlap with Plan 2 (write tests as bugs are fixed).*

**Acceptance criteria:**
- [ ] Bug catalogue exists with every identified issue, root cause, and fix applied
- [ ] All identified bugs are fixed -- none papered over with workarounds
- [ ] Every fixed bug has at least one regression test that would fail if the fix were reverted
- [ ] Existing Phase 4 bug fixes have regression test coverage

---

### Phase 4 -- Test Coverage

**Goal:** Integration and edge-case tests prove that phases compose correctly and handle boundary conditions, including adversarial inputs.
**Requirements:** QUAL-04, QUAL-05, QUAL-06, QUAL-10
**Depends on:** Phase 3

#### Plans
1. **End-to-end integration test** -- Create `tests/test_pipeline_integration.py` that runs 3-5 real talks through Phases 1-5 and validates phase-to-phase data contracts (QUAL-04)
2. **Phase 1 edge cases and schema validation** -- Add tests for missing speaker, unusual sessions, no-URL talks; add startup schema validation against `core.52.db` (QUAL-05, QUAL-06)
3. **Phase 5 adversarial test cases** -- Add test cases with malformed, edge-case, and adversarial inputs to Phase 5 validation (QUAL-10)

*All three plans are independent and can run in parallel.*

**Acceptance criteria:**
- [ ] `tests/test_pipeline_integration.py` passes: 3-5 real talks run through all phases with data contract assertions between each phase boundary
- [ ] Phase 1 edge case tests cover missing speaker, unusual session types, and talks with no URL
- [ ] Pipeline startup validates SQLite schema matches expected structure and fails fast with a clear error if mismatched
- [ ] Phase 5 has adversarial test cases covering malformed inputs, boundary conditions, and unexpected data shapes

---

### Phase 5 -- ChromaDB Loader

**Goal:** A new Phase 6 extractor transforms validated pipeline output into four ChromaDB collections with batch insertion and post-load verification.
**Requirements:** LOAD-01, LOAD-02, LOAD-03, LOAD-04, LOAD-05, LOAD-06
**Depends on:** Phase 4

#### Plans
1. **Document transformation** -- Build the transformer that converts Phase 5 output into ChromaDB `documents/metadatas/ids` format for all 4 collections, with annotation paragraph handling (LOAD-01, LOAD-02, LOAD-03)
2. **Batch insertion** -- Implement dependency-ordered insertion (talks, paragraphs, citations, footnotes) with configurable batch chunking and per-batch progress logging (LOAD-04, LOAD-05)
3. **Post-insertion verification** -- Generate verification report with record counts, sample queries, and foreign key spot checks (LOAD-06)

*Plan 1 must complete before Plan 2. Plan 3 depends on Plan 2.*

**Acceptance criteria:**
- [ ] Phase 6 loader produces correct `documents`, `metadatas`, `ids` for all 4 ChromaDB collections from Phase 5 output
- [ ] Annotation paragraphs are excluded from `conference_talk_paragraphs`; their text appears as pipe-joined metadata in `conference_talks`
- [ ] Citations from annotation paragraphs still appear normally in `conference_talk_citations`
- [ ] Collections are inserted in dependency order: talks first, then paragraphs, then citations and footnotes
- [ ] Post-insertion verification report shows record counts, sample query results, and foreign key spot-check results

---

### Phase 6 -- Pipeline Orchestrator

**Goal:** A single orchestrator script runs the full Phases 1-6 pipeline across all talks with resume, skip, and force capabilities.
**Requirements:** PIPE-01, PIPE-02, PIPE-03, PIPE-04
**Depends on:** Phase 5

#### Plans
1. **Orchestrator core** -- Build the per-talk streaming loop that runs Phases 1-6 sequentially per talk, with progress tracking by `talk_id` and resume-from-last capability (PIPE-01, PIPE-02)
2. **Run modes and buffering** -- Implement skip-if-processed default, `--force` flag, and configurable ChromaDB write buffer size (PIPE-03, PIPE-04)

**Acceptance criteria:**
- [ ] Running the orchestrator processes talks through Phases 1-6 in a per-talk streaming loop
- [ ] An interrupted run resumes from the last successfully processed `talk_id` without reprocessing completed talks
- [ ] Default mode skips already-processed talks; `--force` flag reprocesses them
- [ ] ChromaDB write buffer size is configurable with a default of 500-1000 talks per flush

---

### Phase 7 -- Full Run & Verification

**Goal:** All 7,659 General Conference talks are processed and the resulting ChromaDB collections pass quantitative and semantic verification.
**Requirements:** VER-01, VER-02, VER-03, VER-04
**Depends on:** Phase 6

#### Plans
1. **Full pipeline run** -- Execute the orchestrator across all 7,659 talks, monitoring for errors and completion
2. **Quantitative verification** -- Verify record counts match SQLite-derived expectations; confirm all foreign keys resolve across collections (VER-01, VER-04)
3. **Semantic verification** -- Run test semantic searches on `conference_talk_paragraphs`; verify metadata filtering by speaker, year, and session returns correct results (VER-02, VER-03)

*Plan 1 must complete before Plans 2 and 3. Plans 2 and 3 are independent and can run in parallel.*

**Acceptance criteria:**
- [ ] All 7,659 General Conference talks processed without unrecoverable errors
- [ ] Record counts in all 4 ChromaDB collections match expected totals derived from SQLite source
- [ ] Semantic search on `conference_talk_paragraphs` returns relevant results for at least 3 test queries
- [ ] Metadata filtering by speaker, year, and session returns correct, non-empty result sets
- [ ] All `talk_id` and `paragraph_id` foreign keys resolve across all 4 collections

---

## Deferred

| Item | Target |
|------|--------|
| MCP server with semantic search | Milestone 2 |
| ChromaDB metadata noise stripping (`to_chromadb_format()`) | Milestone 2 |
| Journal of Discourse content | Milestone 3 |
| Scriptures (OT, NT, BOM, D&C, POGP) | Milestone 4+ |
| Performance optimizations (batched DB lookups, streaming Phase 2) | When needed |
| Web scraping | Never |
| Multi-user / hosted deployment | Never |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENRCH-01 | Phase 1 | Pending |
| ENRCH-02 | Phase 1 | Pending |
| ENRCH-03 | Phase 1 | Pending |
| ENRCH-04 | Phase 1 | Pending |
| ENRCH-05 | Phase 1 | Pending |
| ENRCH-06 | Phase 1 | Pending |
| QUAL-01 | Phase 2 | Pending |
| QUAL-02 | Phase 2 | Pending |
| QUAL-03 | Phase 2 | Pending |
| QUAL-07 | Phase 2 | Pending |
| QUAL-08 | Phase 2 | Pending |
| QUAL-09 | Phase 2 | Pending |
| BUGS-01 | Phase 3 | Pending |
| BUGS-02 | Phase 3 | Pending |
| BUGS-03 | Phase 3 | Pending |
| QUAL-04 | Phase 4 | Pending |
| QUAL-05 | Phase 4 | Pending |
| QUAL-06 | Phase 4 | Pending |
| QUAL-10 | Phase 4 | Pending |
| LOAD-01 | Phase 5 | Pending |
| LOAD-02 | Phase 5 | Pending |
| LOAD-03 | Phase 5 | Pending |
| LOAD-04 | Phase 5 | Pending |
| LOAD-05 | Phase 5 | Pending |
| LOAD-06 | Phase 5 | Pending |
| PIPE-01 | Phase 6 | Pending |
| PIPE-02 | Phase 6 | Pending |
| PIPE-03 | Phase 6 | Pending |
| PIPE-04 | Phase 6 | Pending |
| VER-01 | Phase 7 | Pending |
| VER-02 | Phase 7 | Pending |
| VER-03 | Phase 7 | Pending |
| VER-04 | Phase 7 | Pending |

## Progress

**Execution Order:** Phase 1 > Phase 2 > Phase 3 > Phase 4 > Phase 5 > Phase 6 > Phase 7

| Phase | Plans Complete | Status | Completed |
|-------|---------------|--------|-----------|
| 1. DB Enrichment | 0/4 | Planning complete | - |
| 2. Code Quality | 0/3 | Not started | - |
| 3. Bug Audit & Fixes | 0/3 | Not started | - |
| 4. Test Coverage | 0/3 | Not started | - |
| 5. ChromaDB Loader | 0/3 | Not started | - |
| 6. Pipeline Orchestrator | 0/2 | Not started | - |
| 7. Full Run & Verification | 0/3 | Not started | - |
