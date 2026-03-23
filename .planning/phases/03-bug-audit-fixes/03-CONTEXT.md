# Phase 3: Bug Audit & Fixes - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

All known and discovered bugs in Phases 1–5 are identified, fixed at root cause, and covered by regression tests. Three sequential tracks: (1) fix the 11 existing known failures first, (2) run a curated ~20-talk audit through all phases to discover additional bugs, (3) add one regression test per fixed bug to the existing per-phase test files. No new capabilities added.

</domain>

<decisions>
## Implementation Decisions

### Bug Sequencing (BUGS-01 → BUGS-02 → BUGS-03)
- **D-01:** Fix the 11 known failing tests first before running the broader audit. Starting from a clean baseline makes it easier to distinguish new bugs found during the audit.
  - 10 failures in `tests/test_phase2.py` — paragraph extraction logic bugs (pre-existing)
  - 1 failure in `tests/test_phase4.py::TestFootnoteTextRendering::test_rbrackdotrdquo_gives_compound_suffix` — encoding issue (`]."` → replacement character)
- **D-02:** After known failures are fixed, run the curated sample through all phases to discover additional bugs. All discovered bugs go into the catalogue.

### Audit Sample Configuration (BUGS-01)
- **D-03:** Sample size is approximately 20 talks, curated by the user (not random, not algorithm-selected).
- **D-04:** Sample list lives in a config file — `config/audit_sample.json` — as a list of `talk_id` values. Version-controlled, easy to edit without touching source code.
- **D-05:** The audit script reads `config/audit_sample.json` to know which talks to run. The user will populate this file with their chosen talk_ids before the audit runs.

### Bug Catalogue (BUGS-01)
- **D-06:** Single `BUGS.md` file with a markdown table. One row per bug.
- **D-07:** Minimal fields per bug: `ID`, `Phase`, `Description`, `Status` (open/fixed). Root cause and fix details go in commit messages, not the catalogue.

### Regression Tests (BUGS-03)
- **D-08:** Regression tests go into the existing `tests/test_phase*.py` files, co-located with the phase they cover.
- **D-09:** One test per bug — enough to fail if the fix were reverted, no more.
- **D-10:** BUGS-03 also requires coverage for existing Phase 4 fixes already in place. These should be identified during the fix phase (Plan 1) and covered alongside other regressions.

### Claude's Discretion
- Exact `BUGS.md` file location (root, `docs/`, or `.planning/phases/03-bug-audit-fixes/`)
- Audit script name and location (e.g., `scripts/run_audit.py` or ad-hoc)
- Whether to run all 5 phases per talk or limit scope based on what bugs surface
- Fix commit granularity (one commit per bug vs. batching closely-related bugs)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Bug Requirements
- `.planning/REQUIREMENTS.md` §Bug Fixes (BUGS) — Acceptance criteria for BUGS-01, BUGS-02, BUGS-03

### Phase 4 Existing Fixes
- `docs/pipeline/phase-4-footnote/BUG_FIXING_SUMMARY.md` — Summary of Phase 4 bug fixes already in place (these need regression test coverage per BUGS-03)

### Pipeline Architecture (for understanding phases under audit)
- `docs/PIPELINE_SPEC.md` — Full pipeline specification covering Phases 1–5

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config/pipeline_config.py` — Processing constants; audit script should use these rather than hardcoding
- `cache_manager_CLAUDE.py` — Canonical cache manager for any HTTP requests during audit
- `scripts/` — Active entry point for scripts; audit script goes here

### Established Patterns
- `encoding='utf-8'` on all file I/O (Phase 1 fix) — the Phase 4 test failure is likely the same Windows cp1252 issue
- `logger = logging.getLogger(__name__)` — logging standard across all modules
- `tests/test_phase*.py` — one test file per phase; regression tests extend these files

### Integration Points
- `config/audit_sample.json` — new file; read by audit script to determine which talk_ids to process
- `tests/test_phase2.py` — 10 regression tests to add after fixes
- `tests/test_phase4.py` — 1 regression test to add after fix (encoding bug)

### Known Failing Tests (starting inventory)
| Test | Phase | Description |
|------|-------|-------------|
| `test_nested_tags_stripped` | 2 | Nested tag stripping logic |
| `test_skip_tags` | 2 | Skip tag count (expected 2, got 1) |
| `test_extract_simple_talk` | 2 | Simple talk extraction |
| `test_extract_with_multiple_paragraphs` | 2 | Multi-paragraph extraction |
| `test_paragraph_ids_generated` | 2 | Paragraph ID generation |
| `test_very_long_paragraph` | 2 | Long paragraph handling |
| `test_multiple_paragraphs` | 2 | Multiple paragraph extraction |
| `test_is_container_figure` | 2 | Figure container detection |
| `test_extract_semantic_paragraphs_mixed` | 2 | Semantic paragraph extraction (mixed) |
| `test_extract_list_items_separately` | 2 | List item extraction |
| `test_rbrackdotrdquo_gives_compound_suffix` | 4 | Unicode right-quote encoding (`]."` → `].`) |

</code_context>

<specifics>
## Specific Ideas

- The Phase 4 encoding bug (`].` instead of `]."`) is almost certainly the Windows cp1252 vs UTF-8 issue — same root cause as the Phase 1 fix that added `encoding='utf-8'` to file reads.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-bug-audit-fixes*
*Context gathered: 2026-03-23*
