# Phase 7: Full Run & Verification - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Verify the ChromaDB collections populated by the completed pipeline run. The full pipeline run (Plan 1) is **already complete**: 5,838 GC talks processed in 2731.8s with 0 failures and 0 skips. This phase now covers Plans 2 and 3 only: quantitative record count verification and semantic search verification.

</domain>

<decisions>
## Implementation Decisions

### Pipeline Run Status

- **D-01:** Plan 1 (full pipeline run) is already complete. The run processed 5,838 General Conference talks (not 7,659 — see D-02) in 2731.8s with no failures and no skips. Planning covers verification only.

### Talk Count Baseline

- **D-02:** 5,838 is the correct and expected GC talk count. The 7,659 figure in the roadmap includes non-General-Conference content (e.g., welfare sessions, one-offs) that is excluded by the `INNER JOIN conference_talk` in the orchestrator. ROADMAP.md acceptance criteria should be updated to reflect the SQLite-derived GC-only count.

### Record Count Verification (VER-01)

- **D-03:** Derive expected counts from SQLite at runtime using `INNER JOIN conference_talk` to get the authoritative GC-only talk count. Compare ChromaDB `collection.count()` against SQLite-derived expectations. This is the authoritative check — it will catch any talks that were silently missed.

### Semantic Query Design (VER-02)

- **D-04:** Run a mix of topical and scriptural queries against `conference_talk_paragraphs`. Claude selects representative queries:
  - **Topical (2-3):** e.g., "the Atonement of Jesus Christ", "faith and repentance", "eternal family and temple covenants"
  - **Scriptural (1-2):** e.g., "Mosiah 3:19", "John 3:16"
- **D-05:** Pass criteria is manual spot-check. Print top 5 results per query showing talk title, speaker, year, and paragraph text. Engineer reviews output to confirm results are semantically relevant. No automated relevance scoring.

### Metadata Filtering (VER-03)

- **D-06:** Test metadata filtering by speaker, year, and session against `conference_talk_paragraphs`. Use `where` filters. Verify non-empty result sets. Specific test values left to Claude's discretion (e.g., a known speaker like "Russell M. Nelson", a year like "2023", a session like "Saturday Morning").

### FK Integrity (VER-04)

- **D-07:** Full scan of all `talk_id` and `paragraph_id` foreign keys across all 4 collections. At 5,838 talks this is manageable. Fetch IDs from each collection and verify they resolve against expected sets. Claude's discretion on implementation approach.

### Verification Artifact

- **D-08:** Write a reusable `scripts/verify_pipeline.py` script that runs all 4 VER checks in sequence. Designed for re-use in future milestone pipeline runs.
- **D-09:** Output a structured JSON report to `data/verification_report.json` for archival and future comparison across runs. Also print a human-readable summary to stdout.

### Claude's Discretion

- Exact semantic query strings (within the mix-of-topical-and-scriptural constraint)
- Specific speaker/year/session values for metadata filter tests (VER-03)
- FK integrity implementation approach (set intersection, spot-sample, or full scan)
- JSON schema for `verification_report.json`
- Whether to accept `--output` flag to customize report path

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Verification Requirements
- `.planning/REQUIREMENTS.md` §Verification (VER) — VER-01 through VER-04 acceptance criteria

### Orchestrator (already completed Plan 1)
- `scripts/run_pipeline.py` — completed orchestrator; understand its GC-only talk_id selection to match verification query
- `.planning/phases/06-pipeline-orchestrator/06-CONTEXT.md` §decisions — D-01 (ChromaDB skip check), D-03 (failed_talks.json), D-09 (invocation pattern)

### ChromaDB Loader
- `extractors/phase6_chromadb_loader.py` — verify_collections() method already implemented; understand its interface before duplicating
- `config/pipeline_config.py` — CHROMADB_PATH, CHROMADB_COLLECTION_NAMES, CHROMADB_BATCH_SIZE

### Existing Verification Infrastructure
- `extractors/phase6_chromadb_loader.py` §verify_collections — existing verification logic; verify_pipeline.py should call or extend this, not duplicate

### DB Access Pattern
- `scripts/run_audit.py` — `from db import content_db, core_db` pattern; use same imports for SQLite queries in verify_pipeline.py

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `extractors/phase6_chromadb_loader.py` `verify_collections()` — already computes collection counts and FK cross-checks; verify_pipeline.py should call this rather than reimplement
- `config/pipeline_config.py` — CHROMADB_PATH and CHROMADB_COLLECTION_NAMES already defined; no new config needed
- `scripts/run_audit.py` — argparse + DB import pattern to follow for verify_pipeline.py

### Established Patterns
- `from db import content_db, core_db` — standard for scripts accessing SQLite
- `pipenv run py scripts/verify_pipeline.py` — invocation convention
- `encoding='utf-8'` on all file I/O (for verification_report.json write)
- `logger = logging.getLogger(__name__)` — no basicConfig in modules

### Integration Points
- `data/verification_report.json` — new output file; `data/` directory exists (contains `chromadb/` and `failed_talks.json`)
- ChromaDB PersistentClient at `data/chromadb` with OllamaEmbeddingFunction — same instantiation as Phase 6 loader

### Key Phase 6 Decisions That Affect Verification
- Annotation paragraphs excluded from `conference_talk_paragraphs` (folded into talks metadata or dropped) — paragraph count will be lower than raw Phase 2 output
- `_flatten_metadata` strips None/empty — metadata fields for filters may be missing for some talks; metadata filter tests should use well-populated fields
- Talk text = annotation content folded in; paragraph IDs in paragraphs collection skip annotation source_type='a'

</code_context>

<specifics>
## Specific Ideas

- `verify_pipeline.py` should be idempotent and safe to re-run (overwrites `verification_report.json` on each run)
- Print a one-line PASS/FAIL per check to stdout before writing full JSON, so the operator gets immediate feedback
- The semantic query results displayed to stdout should include enough context (title + speaker + year + first 100 chars of paragraph) to make manual spot-check fast
- `data/failed_talks.json` from the completed run should be checked as part of quantitative verification — if it exists and is non-empty, that's a count discrepancy to flag

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 07-full-run-verification*
*Context gathered: 2026-03-26*
