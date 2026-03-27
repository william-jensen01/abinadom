---
phase: 02-code-quality
plan: 02
subsystem: project-structure
tags: [cleanup, scripts, cache-manager, validation-model]
dependency_graph:
  requires: []
  provides: [clean-project-root, scripts-in-scripts-dir, single-cache-manager]
  affects: [CLAUDE.md, scripts/]
tech_stack:
  added: []
  patterns: [git-mv-for-renames, module-docstrings, sys-path-correction]
key_files:
  created: []
  modified:
    - scripts/UPDATE.py
    - scripts/process_all.py
    - scripts/process_topics.py
    - CLAUDE.md
  deleted:
    - cache_manager_OLD.py
    - run_phase2_tests.py
decisions:
  - "sys.path in UPDATE.py updated to use dirname(dirname(...)) since script moved from root to scripts/"
  - "CLAUDE.md Project Structure Index updated to include scripts/ section"
  - "Pre-existing test failure in test_phase2.py::TestTextExtraction::test_nested_tags_stripped logged as out-of-scope"
metrics:
  duration: "8min"
  completed_date: "2026-03-23"
  tasks_completed: 2
  files_changed: 6
---

# Phase 02 Plan 02: Codebase Cleanup - Duplicate Cache Manager and Script Relocation Summary

**One-liner:** Eliminated duplicate cache_manager_OLD.py and superseded run_phase2_tests.py, relocated three root-level scripts to scripts/ with module docstrings and corrected sys.path references, and confirmed no deprecated Phase 5 model fields remain.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Delete cache_manager_OLD.py and run_phase2_tests.py | 4c02987 | cache_manager_OLD.py (deleted), run_phase2_tests.py (deleted) |
| 2 | Move root-level scripts to scripts/ with docstrings | 0e30563 | scripts/UPDATE.py, scripts/process_all.py, scripts/process_topics.py, CLAUDE.md |

## Verification Results

- Root `ls *.py` shows only `__init__.py` and `cache_manager_CLAUDE.py` — confirmed clean
- `scripts/UPDATE.py`, `scripts/process_all.py`, `scripts/process_topics.py` all exist
- `cache_manager_CLAUDE.py` imports successfully (`from cache_manager_CLAUDE import CachedSession`)
- `models/validation_report.py` has exactly 5 fields: talk_id, is_valid, errors, warnings, stats
- `grep -rn "is_opening\|is_scripture" models/ extractors/` returns zero matches
- `process_topics` imports OK after move

## Success Criteria

- QUAL-07: Only `cache_manager_CLAUDE.py` exists; `cache_manager_OLD.py` deleted — DONE
- QUAL-08: `UPDATE.py`, `process_all.py`, `process_topics.py` in `scripts/` with docstrings; `run_phase2_tests.py` deleted — DONE
- QUAL-09: Confirmed no deprecated fields in `models/validation_report.py` — DONE

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] sys.path correction in UPDATE.py line 35**
- **Found during:** Task 2
- **Issue:** `UPDATE.py` had a second sys.path line adding `os.path.join(os.path.dirname(__file__), "db", "one-off-migration")` — after moving to scripts/, this would have resolved to `scripts/db/one-off-migration` instead of the correct `db/one-off-migration` at project root
- **Fix:** Updated to `os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "one-off-migration")`
- **Files modified:** `scripts/UPDATE.py`
- **Commit:** 0e30563

### Out-of-Scope Issues Deferred

**Pre-existing test failure:** `tests/test_phase2.py::TestTextExtraction::test_nested_tags_stripped` fails with `IndexError: list index out of range`. Confirmed pre-existing by git stash test — present before any changes in this plan. Not caused by this plan's changes.

## Self-Check: PASSED

- `scripts/UPDATE.py` — FOUND
- `scripts/process_all.py` — FOUND
- `scripts/process_topics.py` — FOUND
- `CLAUDE.md` updated with scripts/ section — FOUND
- `cache_manager_OLD.py` — confirmed deleted
- `run_phase2_tests.py` — confirmed deleted
- Commit `4c02987` — FOUND
- Commit `0e30563` — FOUND
