---
phase: 10-tools-normalization
plan: 01
subsystem: api
tags: [chromadb, fastmcp, mcp, python, tdd, pytest]

# Dependency graph
requires:
  - phase: 09-server-foundation
    provides: AppContext dataclass, lifespan pattern, 4-collection loading into server.py
  - phase: 09.1-gap-identified-in-phase-10-plans
    provides: paragraph records enriched with speaker_name, title, conference_year, conference_month

provides:
  - _build_where_filter: pure function returning ChromaDB where dict for year/season filters
  - _matches_speaker: pure function for case-insensitive substring speaker matching
  - _format_search_result: pure function returning exactly 6 public fields, strips pipeline-internal fields
  - _parse_talk_id: pure function accepting "talk_8820" or "8820" formats, returns int or None
  - 16 unit tests covering all 4 helper functions

affects: [10-02-tools-implementation, search tool, get_talk tool]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure helper functions in server.py between _startup() and FastMCP lifespan — module-level, not methods"
    - "Speaker post-filter in Python (not ChromaDB where clause) — $contains silently broken in chromadb 1.5.5"
    - "TDD cycle: write failing tests first, then implement to pass"
    - "Test helper functions directly via import from server — no pytest-asyncio needed"

key-files:
  created: []
  modified:
    - tests/test_server.py
    - server.py

key-decisions:
  - "Helper functions are pure/sync — no async overhead, directly importable in tests without pytest-asyncio"
  - "_build_where_filter returns None (not {}) when no filters — ChromaDB rejects empty where dicts (Pitfall 6)"
  - "Speaker filtering excluded from ChromaDB where clause — $contains on metadata silently returns 0 in chromadb 1.5.5"
  - "Snippet comes from ChromaDB document param, not meta['text'] — avoids exposing pipeline-internal field"
  - "talk_id formatted as 'talk_<int>' string in output for consistency with D-03/D-12 convention"

patterns-established:
  - "Pattern: pure helper functions above FastMCP section, below _startup() in server.py"
  - "Pattern: test helper functions directly with inline data — no mocked server context needed"
  - "Pattern: _format_search_result builds 6-field dict explicitly — never return raw metadata"

requirements-completed: [CORE-04, CORE-05, TOOL-03, TOOL-04]

# Metrics
duration: 8min
completed: 2026-04-02
---

# Phase 10 Plan 01: Helper Functions for Search and Get Talk Tools Summary

**Four pure helper functions (_build_where_filter, _matches_speaker, _format_search_result, _parse_talk_id) implemented and TDD-tested with 16 new unit tests in server.py, full suite 420 tests green**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-02T07:32:55Z
- **Completed:** 2026-04-02T07:41:00Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 2

## Accomplishments
- 16 failing tests written first (RED phase) covering all 4 helpers with edge cases
- All 4 helper functions implemented in server.py between _startup() and FastMCP lifespan
- All 21 test_server.py tests pass (5 existing Phase 9 + 16 new Phase 10)
- Full suite (420 tests) green with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — Write failing tests for all 4 helper functions** - `47eeb78` (test)
2. **Task 2: GREEN — Implement all 4 helper functions to pass tests** - `b2c176b` (feat)

_Note: TDD plan — RED commit first, GREEN commit second_

## Files Created/Modified
- `tests/test_server.py` - Appended 4 test classes: TestBuildWhereFilter (4), TestMatchesSpeaker (5), TestFormatSearchResult (3), TestParseTalkId (4)
- `server.py` - Added 4 pure helper functions above lifespan section

## Decisions Made
- Helper functions placed between _startup() and lifespan as module-level pure functions (not AppContext methods) — makes them directly importable in tests without FastMCP context setup
- _build_where_filter returns None not {} for no-filter case — ChromaDB raises validation error on empty where dict
- Speaker filtering is Python post-filter (not ChromaDB where clause) because $contains on metadata silently returns 0 results in chromadb 1.5.5
- Snippet bound to document parameter not meta["text"] — text is in both places but the document param is the canonical ChromaDB snippet; using meta["text"] would expose a pipeline-internal field

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — all helper functions worked exactly as specified on first implementation pass.

## Known Stubs
None — these are pure logic functions with no data wiring. No stub patterns detected.

## Next Phase Readiness
- All 4 helpers ready for Plan 02 (search and get_talk tool registration)
- Plan 02 can import _build_where_filter, _matches_speaker, _format_search_result, _parse_talk_id directly
- Full test suite clean — no blockers

## Self-Check: PASSED

- server.py: FOUND
- tests/test_server.py: FOUND
- 10-01-SUMMARY.md: FOUND
- Commit 47eeb78 (test): FOUND
- Commit b2c176b (feat): FOUND

---
*Phase: 10-tools-normalization*
*Completed: 2026-04-02*
