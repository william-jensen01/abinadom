---
phase: 14-auth-module
plan: 03
subsystem: auth
tags: [sqlite, argparse, cli, bearer-token, api-key-management]

# Dependency graph
requires:
  - phase: 14-auth-module plan 01
    provides: SqliteKeyStore with create_key/revoke_key/list_keys/verify_token
provides:
  - scripts/manage_keys.py CLI with create/revoke/list subcommands
  - AUTH_DB_PATH env var respected for db path configuration
  - Operator-facing API key management interface
affects: [14-04-middleware, 15-docker-compose, 16-caddy-proxy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sys.path.insert(0, ...) pattern from scripts/ for project root on path"
    - "subprocess.run with AUTH_DB_PATH env override for CLI integration testing"
    - "sqlite3.IntegrityError caught at CLI layer for clear user-facing errors"

key-files:
  created:
    - scripts/manage_keys.py
  modified:
    - tests/test_auth.py

key-decisions:
  - "sqlite3.IntegrityError caught at CLI boundary and printed as clean error (no traceback)"
  - "Token shown once via 'it will not be shown again' message — never retrievable"
  - "AUTH_DB_PATH defaults to Path(__file__).parent.parent / auth.db (not cwd)"

patterns-established:
  - "Pattern: CLI integration tests use subprocess.run + AUTH_DB_PATH env override to isolate to tmp_path"
  - "Pattern: manage_keys.py follows run_pipeline.py structure (sys.path.insert, argparse, __main__ guard)"

requirements-completed: [AUTH-01]

# Metrics
duration: 3min
completed: 2026-04-04
---

# Phase 14 Plan 03: Manage Keys CLI Summary

**`scripts/manage_keys.py` operator CLI — create/revoke/list API keys with clean error handling and token-shown-once guarantee**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-04T08:08:57Z
- **Completed:** 2026-04-04T08:11:26Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- `scripts/manage_keys.py` with `create --name`, `revoke --name`, and `list` subcommands
- `create` catches `sqlite3.IntegrityError` for duplicate names and prints a clear error message (no traceback)
- `revoke` with a nonexistent name exits 1 and writes "No key named..." to stderr
- `list` prints key names and creation dates in a formatted table, never token hashes
- `AUTH_DB_PATH` env var controls the db path; default resolves relative to `__file__` (not cwd)
- 5 CLI integration tests added to `tests/test_auth.py` using `subprocess.run` with isolated tmp_path db
- All 462 tests pass (18 in test_auth.py, 444 in rest of suite)

## Task Commits

Each task was committed atomically:

1. **RED — CLI integration tests** - `e35fb81` (test)
2. **GREEN — manage_keys.py implementation** - `8a10e8d` (feat)

_Note: TDD task split into test commit and implementation commit per TDD protocol_

## Files Created/Modified

- `scripts/manage_keys.py` — CLI for API key issuance, revocation, and listing (68 lines)
- `tests/test_auth.py` — 5 CLI integration tests appended (81 lines added)

## Decisions Made

- `sqlite3.IntegrityError` caught at the CLI boundary: clean one-line error to stderr rather than raw traceback. This is the right layer — the store raises it as a natural PRIMARY KEY violation, the CLI converts it to a human-readable message.
- Token shown-once warning message uses the exact phrasing "it will not be shown again" (acceptance criterion match).
- No `logging` import added — the plan spec and reference pattern both omit it for this simple script. `print()` to stdout/stderr is appropriate for a CLI tool.

## Deviations from Plan

None — plan executed exactly as written. The plan provided a complete reference implementation in `<action>` and the code was created verbatim with no necessary changes.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. The CLI runs with `pipenv run py scripts/manage_keys.py <subcommand>`.

## Next Phase Readiness

- `scripts/manage_keys.py` is ready for operator use immediately
- AUTH-01 requirement is fulfilled: operator can issue named API keys and receive bearer tokens
- Plan 14-04 (BearerAuthMiddleware) can proceed — it depends on `auth/store.py` (Plan 01) but not on the CLI
- The `AUTH_DB_PATH` env var pattern is now established in both server and CLI layers

---
*Phase: 14-auth-module*
*Completed: 2026-04-04*

## Self-Check: PASSED

- `scripts/manage_keys.py` — FOUND
- `tests/test_auth.py` — FOUND
- `.planning/phases/14-auth-module/14-03-SUMMARY.md` — FOUND
- Commit `e35fb81` (test RED) — FOUND
- Commit `8a10e8d` (feat GREEN) — FOUND
