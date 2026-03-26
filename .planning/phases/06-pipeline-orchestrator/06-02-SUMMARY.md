---
phase: 06-pipeline-orchestrator
plan: "02"
subsystem: pipeline-orchestrator
tags: [pipeline, chromadb, configuration, testing, tqdm]
dependency_graph:
  requires: ["06-01"]
  provides: ["PIPE-03", "PIPE-04"]
  affects: ["config/pipeline_config.py", "tests/test_phase6_orchestrator.py", "Pipfile", "CLAUDE.md"]
tech_stack:
  added: [tqdm]
  patterns: [batch-flush-boundary-testing, mock-side-effect-snapshot]
key_files:
  created: []
  modified:
    - config/pipeline_config.py
    - tests/test_phase6_orchestrator.py
    - Pipfile
    - CLAUDE.md
decisions:
  - "CHROMADB_BATCH_SIZE set to 1000 (PIPE-04 compliance): 500-1000 range, limits re-processing on interrupt to at most 1000 talks"
  - "Buffer flush test captures size via side_effect snapshot rather than checking post-clear list reference"
  - "tqdm declared as explicit runtime dependency in Pipfile (was installed but undeclared)"
metrics:
  duration: "10min"
  completed: "2026-03-26"
  tasks_completed: 2
  files_modified: 4
---

# Phase 6 Plan 02: Run Modes and Buffer Flush Configuration Summary

Finalized PIPE-03 (skip-if-processed default with --force override) and PIPE-04 (configurable ChromaDB write buffer) by correcting CHROMADB_BATCH_SIZE from 5000 to 1000, declaring tqdm as an explicit Pipfile dependency, adding four targeted behavioral tests for skip/force/buffer behavior, and updating the CLAUDE.md project index.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Update CHROMADB_BATCH_SIZE and install tqdm in Pipfile | 8a4c72d | config/pipeline_config.py, Pipfile |
| 2 | Add skip/force/buffer tests and update CLAUDE.md index | efc7235 | tests/test_phase6_orchestrator.py, CLAUDE.md |

## Decisions Made

1. **CHROMADB_BATCH_SIZE = 1000**: Reconciled discrepancy (was 5000, PIPE-04 requires 500-1000 range). At 1000, a full 5,838-talk run flushes ~6 times and limits re-processing on interrupt to at most 1000 talks.

2. **Side-effect snapshot for buffer flush tests**: `pending_bundles` is cleared in-place after each flush call. Using `side_effect` to capture `len(bundles)` before clear avoids the stale-reference problem from checking call args after the fact.

3. **tqdm declared in Pipfile**: Was installed (4.67.3) but not declared. Added as runtime dependency per D-05.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed buffer flush test assertion strategy**
- **Found during:** Task 2 (RED phase)
- **Issue:** Plan specified asserting `len(first_call_bundles) == 2` via `mock_load.call_args_list[0][0][0]`, but `pending_bundles` is cleared in-place after each flush — the recorded mock arg reference points to the same (now-empty) list object
- **Fix:** Used `side_effect` functions that capture `len(bundles)` before `clear()` is called, then assert on the snapshot list
- **Files modified:** tests/test_phase6_orchestrator.py
- **Commit:** efc7235

## Known Stubs

None — all new tests exercise real pipeline behavior via mocks with correct expectations.

## Self-Check: PASSED

- config/pipeline_config.py contains `CHROMADB_BATCH_SIZE = 1000`: FOUND
- Pipfile contains `tqdm = "*"`: FOUND
- tests/test_phase6_orchestrator.py contains `test_skip_mode_default`: FOUND
- tests/test_phase6_orchestrator.py contains `test_force_flag_reprocesses`: FOUND
- tests/test_phase6_orchestrator.py contains `test_buffer_flush_at_batch_size`: FOUND
- tests/test_phase6_orchestrator.py contains `test_final_flush_on_remaining`: FOUND
- Commits 8a4c72d and efc7235: FOUND
- All 11 orchestrator tests pass: CONFIRMED
