---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: MCP Server
status: Defining requirements
stopped_at: ~
last_updated: "2026-03-30T00:00:00.000Z"
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-19)

**Core value:** All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks.
**Current focus:** Planning Milestone 2 — MCP server for semantic search

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-30 — Milestone v2.0 started

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: --
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: --
- Trend: --

*Updated after each plan completion*
| Phase 01 P02 | 3min | 1 tasks | 1 files |
| Phase 01 P03 | 9min | 2 tasks | 5 files |
| Phase 01 P04 | 2min | 2 tasks | 1 files |
| Phase 02 P02 | 8min | 2 tasks | 6 files |
| Phase 02-code-quality P01 | 20 | 2 tasks | 5 files |
| Phase 03-bug-audit-fixes P01 | 45min | 2 tasks | 7 files |
| Phase 03-bug-audit-fixes P02 | 10min | 1 tasks | 2 files |
| Phase 03 P03 | 4min | 1 tasks | 2 files |
| Phase 04-test-coverage P01 | 4min | 2 tasks | 1 files |
| Phase 04-test-coverage P03 | 15min | 2 tasks | 1 files |
| Phase 04-test-coverage P02 | 5min | 2 tasks | 2 files |
| Phase 05-chromadb-loader P01 | 10min | 2 tasks | 8 files |
| Phase 05-chromadb-loader P02 | 11min | 2 tasks | 4 files |
| Phase 05-chromadb-loader P03 | 5min | 1 tasks | 2 files |
| Phase 06 P01 | 6min | 2 tasks | 2 files |
| Phase 06 P02 | 10min | 2 tasks | 4 files |
| Phase 07 P01 | 3min | 2 tasks | 2 files |
| Phase 07 P02 | 15min | 3 tasks | 2 files |
| Phase 08 P01 | 6min | 2 tasks | 5 files |

## Accumulated Context

### Roadmap Evolution

- Phase 8 added: include topics in talk metadata for phase 1 of pipeline (talk_topic and conference_topic tables in core.52.db)

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: ENRCH before all other work -- changes how Phase 1 reads data
- [Roadmap]: QUAL tech-debt before BUGS -- clean codebase makes bugs easier to find
- [Roadmap]: QUAL-09 (deprecated phase-5 validation fields) and QUAL-10 (adversarial tests) added to Milestone 1 scope
- [Phase 01]: Sequential API fetching with requests_cache for Church API politeness
- [Phase 01]: Used LEFT JOIN talk_metadata with COALESCE for enrichment overlay pattern
- [Phase 01]: Added encoding='utf-8' to file reads in tests for Windows cp1252 compatibility
- [Phase 02]: sys.path in UPDATE.py updated to use dirname(dirname()) since script moved from root to scripts/
- [Phase 02]: CLAUDE.md Project Structure Index updated to include scripts/ section with newly moved scripts
- [Phase 02-code-quality]: Processing constants live in config/pipeline_config.py as module-level constants; schemas.py dict API preserved for callers
- [Phase 02-code-quality]: No extractor or API module calls logging.basicConfig; level conventions documented in pipeline_config.py
- [Phase 03-bug-audit-fixes]: Fix test HTML to use body-block container rather than adding extractor fallback — tests written before strict container enforcement
- [Phase 03-bug-audit-fixes]: Replace literal curly-quote bytes with \u201c/\u201d ASCII-safe escapes — more robust than coding declaration alone on Windows cp1252
- [Phase 03-bug-audit-fixes]: No new bugs found — audit confirms Plan 01 fixes were comprehensive; BUGS.md updated with audit log, not new bug rows
- [Phase 03-bug-audit-fixes]: Audit log table added to BUGS.md for future auditability — records when audits were run, what sample was used, and results
- [Phase 03]: Every fixed bug has a regression test with BUG-NN docstring — existing tests annotated, two new tests for BUG-06 and BUG-07
- [Phase 04-test-coverage]: Used c.book (CitationData.book field) not c.book_name in test_phase3_boundary
- [Phase 04-test-coverage]: Corrupt fields post-construction to test Phase 5 validator robustness against adversarial inputs without bypassing model guards
- [Phase 04-test-coverage]: Pre-existing DB failures (7 tests) are environment-only — confirmed by stash verification before any code changes
- [Phase 04-test-coverage]: Schema validation is lazy (runs on first _connect per instance) to avoid breaking tests that use in-memory or mock DBs
- [Phase 04-test-coverage]: SchemaError is a hard fail per D-09 — pipeline halts with a clear message on schema mismatch
- [Phase 04-test-coverage]: Missing speaker test documents INNER JOIN behavior: fetch_talk_by_id returns None when speaker row absent — no crash
- [Phase 05-chromadb-loader]: source_type added to ParagraphData with default p — non-breaking change enabling annotation detection
- [Phase 05-chromadb-loader]: _flatten_metadata removes None/empty lists, comma-joins List[int], pipe-joins List[str] for ChromaDB scalar requirement
- [Phase 05-chromadb-loader]: Annotation three-way split: excluded from paragraphs, text folded into talk metadata, citations preserved in citations collection
- [Phase 05-chromadb-loader]: EphemeralClient is a singleton -- fresh_client fixture deletes collections between tests
- [Phase 05-chromadb-loader]: Installed ollama python package as runtime dep (required by OllamaEmbeddingFunction at instantiation)
- [Phase 05-chromadb-loader]: Verification report returns dict (not string) for downstream flexibility; missing annotation paragraph_ids always pass FK check per D-07/D-09
- [Phase 06]: INNER JOIN conference_talk for GC-only talk IDs (~5,838 vs 7,659 total)
- [Phase 06]: logging.WARNING level so tqdm progress bar is uncluttered by INFO lines
- [Phase 06]: No include=['ids'] param in ChromaDB skip check (raises ValueError per Research Pitfall 4)
- [Phase 06]: CHROMADB_BATCH_SIZE set to 1000 (PIPE-04 compliance): reconciled discrepancy from 5000, limits re-processing on interrupt to 1000 talks
- [Phase 06]: tqdm declared as explicit Pipfile runtime dep (was installed 4.67.3 but undeclared)
- [Phase 07]: Talk count derived from SQLite INNER JOIN conference_talk at runtime (not hardcoded) for VER-01
- [Phase 07]: VER-02 skipped (not failed) when Ollama unavailable — avoids false failures in offline environments
- [Phase 07]: Citations->paragraphs FK check is informational — annotation-sourced citations have unresolvable paragraph_ids by design
- [Phase 07]: VER-02 semantic results approved manually — all 5 queries returned relevant results
- [Phase 07]: ROADMAP.md updated: 7,659 replaced with 5,838 (GC-only INNER JOIN) throughout milestone goal and acceptance criteria
- [Phase 08]: topics field uses List[str] with default_factory=list -- empty list semantically correct for talks with no topics
- [Phase 08]: GROUP_CONCAT uses pipe delimiter to match existing _flatten_metadata pipe-join convention for List[str] fields
- [Phase 08]: ct2 alias for conference_topic in subquery avoids collision with outer ct alias (conference_talk)

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260320-hr5 | backfill_talk_kicker not writing updates | 2026-03-20 | 8ba4345 | [260320-hr5-backfill-talk-kicker-not-writing-updates](./quick/260320-hr5-backfill-talk-kicker-not-writing-updates/) |
| 260323-0jy | Fix sqlite3.OperationalError no such column URI_L/URI_GC | 2026-03-23 | cc87f51 | [260323-0jy-fix-sqlite3-operationalerror-no-such-col](./quick/260323-0jy-fix-sqlite3-operationalerror-no-such-col/) |
| 260324-jmc | Update Phase 5 planning to remove embedding | 2026-03-24 | 15c5505 | [260324-jmc-update-phase-5-planning-to-remove-embedd](./quick/260324-jmc-update-phase-5-planning-to-remove-embedd/) |

## Session Continuity

Last session: 2026-03-27T19:18:11.836Z
Stopped at: Completed 08-01-PLAN.md
Resume file: None
