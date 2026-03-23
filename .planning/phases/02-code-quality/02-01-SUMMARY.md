---
phase: 02-code-quality
plan: 01
subsystem: config, extractors, api
tags: [config, logging, code-quality, refactor]
dependency_graph:
  requires: []
  provides: [config/pipeline_config.py, standardized-logging]
  affects: [config/schemas.py, extractors/phase1_talk_metadata.py, extractors/phase2_paragraph_extraction.py, api/fetch_talk_previews.py]
tech_stack:
  added: []
  patterns: [centralized-constants, getLogger-only]
key_files:
  created: [config/pipeline_config.py]
  modified: [config/schemas.py, extractors/phase1_talk_metadata.py, extractors/phase2_paragraph_extraction.py, api/fetch_talk_previews.py]
decisions:
  - "Processing constants live in config/pipeline_config.py as module-level constants (not dicts, not dataclasses)"
  - "schemas.py dict API preserved for existing callers; values now sourced from pipeline_config constants"
  - "No extractor or API module calls logging.basicConfig; that is the caller/orchestrator's responsibility"
metrics:
  duration: 20min
  completed: 2026-03-22
  tasks_completed: 2
  files_changed: 5
---

# Phase 2 Plan 01: Config Centralization and Logging Standardization Summary

Centralized all processing parameters into `config/pipeline_config.py` as importable constants, wired `config/schemas.py` to use them, and removed `logging.basicConfig` from all extractor and API modules.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Verify QUAL-01 and create pipeline_config.py | a20fd98 | config/pipeline_config.py, config/schemas.py |
| 2 | Standardize logging across all extractor modules | 0e03754 | extractors/phase1_talk_metadata.py, extractors/phase2_paragraph_extraction.py, api/fetch_talk_previews.py |

## Decisions Made

- **D-01/D-02**: Processing constants use module-level names in `config/pipeline_config.py` (not dicts, not dataclasses). This makes constants importable directly (`from config.pipeline_config import CONTEXT_BEFORE_CHARS`) without needing a dict key lookup.
- **D-03**: `config/schemas.py` dict-based API is preserved unchanged for existing callers; dict values now reference `pipeline_config` constants, making pipeline_config the single source of truth.
- **D-04/D-05/D-06**: `logging.basicConfig` removed from `phase1_talk_metadata.py`, `phase2_paragraph_extraction.py`, and `api/fetch_talk_previews.py`. Modules now only call `logging.getLogger(__name__)`. The caller (orchestrator or CLI entry point) is responsible for configuring the root logger.

## Success Criteria Verification

- QUAL-01: Citation position tests pass — 77 passed, 6 skipped (integration tests that need DB) in test_phase3 + test_html_parsing_utils
- QUAL-02: `config/pipeline_config.py` exists with all processing constants; `config/schemas.py` imports from it
- QUAL-03: Zero `logging.basicConfig` matches in `extractors/` and `api/`; level conventions documented in pipeline_config.py module docstring

## Deviations from Plan

### Pre-existing test failures (out of scope, not caused by this plan)

The following test failures existed before this plan's changes and were confirmed by running tests on the original code:

- `tests/test_phase1.py` — 3 DDL tests fail due to missing DB in worktree environment
- `tests/test_phase2.py` — 10 tests fail (pre-existing extraction logic bugs, not config-related)
- `tests/test_phase3.py` — 4 integration tests fail due to missing DB in worktree environment

These are logged to `deferred-items.md` for Phase 02 bug-fixing plans.

None of these failures were introduced by this plan's changes. The 77 tests that were passing before the plan remain passing after.

## Known Stubs

None. All constants have concrete values; no placeholder data flows to UI or output.

## Self-Check: PASSED
