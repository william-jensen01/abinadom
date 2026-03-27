# Phase 2: Code Quality - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Clean up tech debt so the codebase is consistent, configurable, and navigable before hunting bugs in Phase 3. Three independent tracks: (1) Phase 3 citation position refactor per spec, (2) config centralization and logging standardization, (3) legacy and model cleanup. No new capabilities added.

</domain>

<decisions>
## Implementation Decisions

### Config Centralization (QUAL-02)
- **D-01:** Create `config/pipeline_config.py` with processing parameters only — parser choice, context window sizes, batch sizes, regex patterns. DB paths and file paths are NOT included; they stay passed-in or per-script.
- **D-02:** Expose values as module-level constants (e.g., `CONTEXT_WINDOW_SIZE = 150`, `BATCH_SIZE = 500`). No dataclasses, no dicts — plain importable constants.
- **D-03:** Extractors updated to import and use constants directly (replace in-place). No fallback defaults with comments — single source of truth.

### Logging Standardization (QUAL-03)
- **D-04:** Standard: `logger = logging.getLogger(__name__)` in every module. No `logging.basicConfig` in any module — that's the caller's job (orchestrator or CLI entry point).
- **D-05:** Level conventions:
  - `DEBUG` — verbose parsing detail, per-item tracing
  - `INFO` — progress milestones, phase start/completion, record counts
  - `WARNING` — skipped items, fallbacks, suspicious-but-not-blocking events
  - `ERROR` — failures that halt or corrupt output
- **D-06:** Phase 1's `logging.basicConfig` at module level must be removed and replaced with `getLogger(__name__)` to match the standard.

### Root-Level Script Cleanup (QUAL-08)
- **D-07:** Three active scripts moved to `scripts/`: `UPDATE.py`, `process_all.py`, `process_topics.py`. Each gets a clear module docstring explaining its purpose and entry point usage.
- **D-08:** `run_phase2_tests.py` deleted — superseded by pytest. No archiving needed.

### Cache Manager Resolution (QUAL-07)
- **D-09:** `cache_manager_CLAUDE.py` is the canonical cache manager. It uses the modern `CachedSession` API correctly.
- **D-10:** `cache_manager_OLD.py` deleted — no archiving needed.

### Citation Position Refactor (QUAL-01)
- **D-11:** Implement per `docs/pipeline/phase-3-citation/REFACTOR_CITATION_PARSING.md` — switch from text-search to ID-based anchor walking. No deviation from that spec.

### Deprecated Model Fields (QUAL-09)
- **D-12:** Audit `models/validation_report.py` for any deprecated fields (`is_opening`, `is_scripture`, etc.) and remove with all references. (Current review suggests the file may already be clean — confirm during execution.)

### Claude's Discretion
- Exact module docstring wording for moved scripts
- How to handle any edge cases found during the citation refactor not covered by REFACTOR_CITATION_PARSING.md
- Whether to add a `__all__` to pipeline_config.py

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Citation Position Refactor
- `docs/pipeline/phase-3-citation/REFACTOR_CITATION_PARSING.md` — Full spec for ID-based anchor walking, all 7 citation HTML patterns, and the correct anchor selection algorithm

### Code Quality Requirements
- `.planning/REQUIREMENTS.md` §Code Quality (QUAL) — Acceptance criteria for QUAL-01 through QUAL-09

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config/schemas.py` — Already exists in config/; `pipeline_config.py` goes alongside it
- `cache_manager_CLAUDE.py` — Canonical cache manager to keep; uses `CachedSession` from requests_cache
- `scripts/` — Directory already exists with other utilities; active scripts move here

### Established Patterns
- Phase 3 (`extractors/phase3_citation_extraction.py`) — Already uses `logging.getLogger(__name__)` correctly; use as the reference implementation for logging standard
- Phase 1 (`extractors/phase1_talk_metadata.py`) — Has `logging.basicConfig` at module level (anti-pattern to fix)

### Integration Points
- All extractor files (`extractors/phase*.py`) will need import updated to pull constants from `config/pipeline_config.py`
- Any callers of moved scripts (`scripts/UPDATE.py`, `scripts/process_all.py`, `scripts/process_topics.py`) need path updates

</code_context>

<specifics>
## Specific Ideas

No specific references or "I want it like X" moments — standard cleanup, follow existing patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-code-quality*
*Context gathered: 2026-03-20*
