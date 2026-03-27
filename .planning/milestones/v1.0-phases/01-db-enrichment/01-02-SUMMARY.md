---
phase: 01-db-enrichment
plan: 02
subsystem: api
tags: [church-api, requests-cache, sqlite, two-level-fetch, previews]

requires:
  - phase: 01-db-enrichment/00
    provides: talk_metadata DDL with preview column
provides:
  - Church API two-level preview fetcher script (api/fetch_talk_previews.py)
  - Conference-level talk URI extraction from toc.entries[1:]
  - Individual talk preview extraction from page-meta-social path
  - URI_GC lookup for matching API URIs to talk IDs
affects: [01-db-enrichment/03, backfill-previews]

tech-stack:
  added: []
  patterns: [two-level-api-fetch, requests-cache-idempotent, uri-gc-normalization]

key-files:
  created: [api/fetch_talk_previews.py]
  modified: []

key-decisions:
  - "Sequential fetching (no threading) to be polite to Church API; requests_cache makes re-runs fast"
  - "URI normalization strips /study prefix for matching API URIs to DB uri_gc values"

patterns-established:
  - "Two-level Church API fetch: Level 1 conference -> talk URIs, Level 2 talk -> preview"
  - "Dry-run mode pattern for safe API script testing"

requirements-completed: [ENRCH-03]

duration: 3min
completed: 2026-03-20
---

# Phase 01 Plan 02: Church API Preview Fetcher Summary

**Two-level Church API fetcher extracting talk previews via conference-level URI collection then per-talk preview retrieval with requests_cache**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-20T00:21:40Z
- **Completed:** 2026-03-20T00:25:06Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Built complete two-level Church API fetcher for talk previews
- Level 1 correctly parses toc.entries[1:] to extract talk URIs per session
- Level 2 navigates page-meta-social.pageMeta.description for preview text
- Dry-run verification: 167 conferences, 4230 talk URIs collected successfully

## Task Commits

Each task was committed atomically:

1. **Task 1: Build Church API preview fetcher** - `26842d9` (feat)

**Plan metadata:** [pending final commit]

## Files Created/Modified
- `api/fetch_talk_previews.py` - Church API two-level preview fetcher with dry-run mode, uri_gc lookup, and coverage reporting

## Decisions Made
- Sequential fetching chosen over threading to be polite to the Church API; requests_cache ensures idempotent re-runs are fast
- URI normalization strips `/study` prefix when matching API URIs to database URI_GC values
- Used `pipenv run python` (not `pipenv run py`) due to Python Launcher availability

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Preview fetcher script ready; next plan can run full fetch (without --dry-run) to populate talk_previews.json
- URI_GC lookup pattern established for matching API data to database records

---
*Phase: 01-db-enrichment*
*Completed: 2026-03-20*

## Self-Check: PASSED
