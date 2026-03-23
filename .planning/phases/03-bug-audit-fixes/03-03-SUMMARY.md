---
phase: 03-bug-audit-fixes
plan: 03
subsystem: testing
tags: [pytest, regression-tests, bug-catalogue, docstrings]

requires:
  - phase: 03-bug-audit-fixes/03-01
    provides: All 15 known bugs fixed across Phase 2 and Phase 4 extractors
  - phase: 03-bug-audit-fixes/03-02
    provides: 52-talk audit confirming no additional bugs exist

provides:
  - Every fixed bug (BUG-01 through BUG-15) has at least one regression test with Regression: BUG-NN docstring
  - Two new regression tests for BUG-06 (bare li text) and BUG-07 (debug prints)
  - Phase 4 existing fix coverage (Bugs 1-3 from BUG_FIXING_SUMMARY.md) confirmed via TestFootnoteTextRendering tests

affects:
  - Future pipeline phases: regression tests serve as guardrails against reintroducing fixed bugs

tech-stack:
  added: []
  patterns:
    - "Regression test naming: test_regression_bug_NN_short_description per D-09"
    - "Regression docstring tagging: each fixed bug's test includes 'Regression: BUG-NN' in its docstring per D-08"

key-files:
  created: []
  modified:
    - tests/test_phase2.py
    - tests/test_phase4.py

key-decisions:
  - "Existing tests serve as regression tests for BUG-02/03/04/08/09/10/11/12 — added docstrings rather than duplicating tests per D-09 (one test per bug)"
  - "BUG-13/14/15 mapped to existing TestFootnoteTextRendering tests — docstrings added to test_cite_tags_preserve_surrounding_spaces, test_sx_anchor_removed_no_extra_space, test_rsemi_gives_semicolon_suffix"

patterns-established:
  - "Regression: BUG-NN docstring convention: every fixed bug has a traceable test that would fail if the fix were reverted"

requirements-completed: [BUGS-03]

duration: 4min
completed: 2026-03-23
---

# Phase 03 Plan 03: Add Regression Tests for Fixed Bugs Summary

**Added regression test coverage for all 15 fixed bugs with BUG-NN docstrings — 2 new tests (BUG-06, BUG-07) and 13 docstring annotations on existing tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-23T22:31:34Z
- **Completed:** 2026-03-23T22:35:51Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Added `Regression: BUG-NN` docstrings to 13 existing tests that already covered fixed bugs (BUG-01 through BUG-05, BUG-08 through BUG-15)
- Created `test_regression_bug_06_bare_li_text` — verifies bare `<li>` text without `<p>` wrapper is extracted as a paragraph; would fail if the bare-li fallback in `extract_list_item_paragraphs` were removed
- Created `test_regression_bug_07_no_debug_prints` — verifies no "Stanza Detected" print output from `extract_semantic_paragraphs`; would fail if debug prints were re-added
- Confirmed all 15 TestFootnoteTextRendering tests pass, covering Phase 4 Bugs 1-3 from BUG_FIXING_SUMMARY.md (BUG-13 whitespace, BUG-14 sx() anchors, BUG-15 ccontainer punctuation)
- Full test suite: 269 tests, 0 failures in Phase 2 + Phase 4 (7 pre-existing DB-absent failures in Phase 1/3 unrelated to this plan)

## Task Commits

1. **Task 1: Add regression tests for all fixed bugs** - `e0c4883` (test)

## Files Created/Modified

- `tests/test_phase2.py` — Added Regression: BUG-02/03/04/05/08/09/10/11/12 docstrings to existing tests; added new TestRegressionBugs class with test_regression_bug_06 and test_regression_bug_07
- `tests/test_phase4.py` — Added Regression: BUG-01/13/14/15 docstrings to existing TestFootnoteTextRendering tests

## Decisions Made

- Existing tests serve as regression tests for most bugs — added docstrings rather than duplicating tests, per D-09 (one test per bug, no duplication)
- BUG-01 (encoding) mapped to `test_rbrackdotrdquo_gives_compound_suffix` which asserts U+201D output; reverting the encoding fix would produce U+FFFD
- BUG-13/14/15 mapped to existing TestFootnoteTextRendering tests that were already written specifically to cover these Phase 4 fixes

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Known Stubs

None — all regression tests are fully wired and passing.

## Next Phase Readiness

- Phase 03 (bug-audit-fixes) is now complete: all bugs fixed, audited, and regression-tested
- Pipeline is stable and ready for Phase 6 (ChromaDB loader) or next milestone work
- No blockers or concerns

## Self-Check: PASSED

- tests/test_phase2.py: FOUND
- tests/test_phase4.py: FOUND
- Commit e0c4883: FOUND
- All 15 BUG-NN regression docstrings verified via grep

---
*Phase: 03-bug-audit-fixes*
*Completed: 2026-03-23*
