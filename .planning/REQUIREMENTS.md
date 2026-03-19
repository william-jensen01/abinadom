# Requirements — BYU Scripture Citation Index RAG System
# Milestone 1: General Conference Pipeline

*Last updated: 2026-03-19*

---

## Validated Requirements (Existing, Phases 1–5)

These requirements are satisfied by the current codebase and are preserved as-is.

| ID | Requirement |
|----|-------------|
| VAL-01 | Talk metadata extracted: speaker, title, conference, session, URL — Phase 1 |
| VAL-02 | Paragraphs segmented with position tracking and era-specific fallbacks — Phase 2 |
| VAL-03 | Citations extracted and parsed (book, chapter, verses, context window) — Phase 3 |
| VAL-04 | Footnotes extracted and parsed (reference type, context window) — Phase 4 |
| VAL-05 | Enrichment, cross-reference linking, and integrity validation — Phase 5 |

---

## Active Requirements (v1 — Milestone 1)

### Bug Fixes (BUGS)

| ID | Requirement |
|----|-------------|
| BUGS-01 | All Phase 1–5 extractor bugs identified and catalogued across the codebase |
| BUGS-02 | All identified bugs fixed with root cause addressed (not papered over) |
| BUGS-03 | Regression tests added for all fixed bugs, including coverage of the Phase 4 fixes already in place |

### DB Enrichment (ENRCH)

| ID | Requirement |
|----|-------------|
| ENRCH-01 | `talk_metadata` table created (1:1 with `talks`, GC entries only) with columns: `speaker_role`, `uri_l`, `uri_gc`, `kicker`, `talk_preview`, `data_aid` |
| ENRCH-02 | All existing backfill scripts in `db/one-off-migration/` updated to write to `talk_metadata` instead of `talks` columns |
| ENRCH-03 | Talk preview collection script completed: fetches all GC previews from Church API, saves to `talk_previews.json` |
| ENRCH-04 | All backfill scripts re-run to populate `talk_metadata` with current data |
| ENRCH-05 | Phase 1 metadata extractor updated to JOIN `talks + talk_metadata` and expose enriched fields downstream |
| ENRCH-06 | `talk_topic` and `conference_topic` tables remain unchanged |

### Code Quality (QUAL)

| ID | Requirement |
|----|-------------|
| QUAL-01 | Phase 3 citation position bug fixed: switch from text-search to ID-based anchor walking per `docs/pipeline/phase-3-citation/REFACTOR_CITATION_PARSING.md` — fixes wrong positions when the same scripture appears multiple times in a paragraph |
| QUAL-02 | Hardcoded config values centralized into `config/pipeline_config.py`: parser choice, context window size, batch sizes, regex patterns |
| QUAL-03 | Logging verbosity standardized across all phases with documented level conventions |
| QUAL-04 | End-to-end integration test added: `tests/test_pipeline_integration.py` runs 3–5 real talks through all phases and verifies phase-to-phase data contracts |
| QUAL-05 | Phase 1 edge case tests added: missing speaker, unusual session types, talks with no URL |
| QUAL-06 | SQLite schema validation at startup: verify `core.52.db` schema matches expected structure before running the pipeline |
| QUAL-07 | Duplicate cache manager resolved: determine which of `cache_manager_CLAUDE.py` / `cache_manager_OLD.py` is canonical; delete or archive the other |
| QUAL-08 | Legacy root-level scripts audited: `UPDATE.py`, `process_all.py`, `process_topics.py`, `run_phase2_tests.py` — each either moved to `scripts/` with clear ownership or documented as active entry points |
| QUAL-09 | Deprecated Phase 5 model fields removed: `is_opening`, `is_scripture`, and similar unused fields cleaned from `models/validation_report.py` and all references updated |
| QUAL-10 | Phase 5 adversarial test cases added: malformed inputs, boundary conditions, and unexpected data shapes covered in `tests/test_phase5.py` |

### ChromaDB Loader (LOAD)

| ID | Requirement |
|----|-------------|
| LOAD-01 | Phase 5 output transformed into `documents`, `metadatas`, `ids` format for each of the 4 ChromaDB collections |
| LOAD-02 | Annotation paragraphs (`source_type="annotation"`) excluded from `conference_talk_paragraphs`; text folded into `conference_talks` metadata as pipe-joined string |
| LOAD-03 | Citations extracted from annotation paragraphs still included in `conference_talk_citations` normally |
| LOAD-04 | All 4 collections inserted in dependency order (talks → paragraphs → citations/footnotes) with configurable batch chunking |
| LOAD-05 | Insertion progress logged per batch for large runs |
| LOAD-06 | Post-insertion verification report generated: record counts, sample queries, foreign key spot checks |

### Pipeline Orchestrator (PIPE)

| ID | Requirement |
|----|-------------|
| PIPE-01 | Single orchestrator script runs per-talk streaming loop (Phases 1–6) across all 7,659 General Conference talks |
| PIPE-02 | Progress tracked by `talk_id`; interrupted run resumes from last successfully processed talk |
| PIPE-03 | Skip-if-processed mode is default; `--force` flag re-processes already-completed talks |
| PIPE-04 | ChromaDB write buffer size configurable; default 500–1000 talks per flush |

### Verification (VER)

| ID | Requirement |
|----|-------------|
| VER-01 | Record counts in all 4 ChromaDB collections match expected totals derived from SQLite |
| VER-02 | Semantic search on `conference_talk_paragraphs` returns relevant results for test queries |
| VER-03 | Metadata filtering by speaker, year, and session returns correct, non-empty results |
| VER-04 | All foreign keys (`talk_id`, `paragraph_id`) resolvable across all 4 collections |

---

## Out of Scope (v1)

| Item | Deferred To |
|------|------------|
| MCP server with semantic search | Milestone 2 |
| ChromaDB metadata noise stripping (`to_chromadb_format()`) | Milestone 2 (before MCP) |
| Journal of Discourse content | Milestone 3 |
| Scriptures (OT, NT, BOM, D&C, POGP) | Milestone 4+ |
| Performance optimizations (batched DB lookups, streaming Phase 2) | When needed |
| Web scraping (all HTML from SQLite only) | Never |
| Multi-user / hosted deployment | Never (personal use) |

---

## Traceability

> Roadmap phases reference these IDs to show what each phase delivers.

| Category | IDs | Description |
|----------|-----|-------------|
| VAL | 01–05 | Validated — already exists |
| BUGS | 01–03 | Extractor bug audit and fixes |
| ENRCH | 01–06 | DB enrichment restructure + backfill |
| QUAL | 01–10 | Code quality, tests, cleanup |
| LOAD | 01–06 | Phase 6 ChromaDB loader |
| PIPE | 01–04 | Pipeline orchestrator |
| VER | 01–04 | Post-run verification |
