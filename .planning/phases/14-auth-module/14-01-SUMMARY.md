---
phase: 14-auth-module
plan: 01
subsystem: auth
tags: [sqlite3, secrets, hashlib, hmac, abc, bearer-token, api-key]

# Dependency graph
requires:
  - phase: 13-http-transport
    provides: Streamable HTTP server with Starlette app (middleware integration point)

provides:
  - KeyStore ABC with verify_token and log_request abstract methods
  - SqliteKeyStore: full key management (create/verify/revoke/list) and usage logging
  - auth/ package with clean import interface

affects:
  - 14-auth-module (Plan 02 — middleware depends on KeyStore interface)
  - 14-auth-module (Plan 03 — CLI depends on SqliteKeyStore)

# Tech tracking
tech-stack:
  added: []  # stdlib only: secrets, hashlib, hmac, sqlite3, abc — no new dependencies
  patterns:
    - "Provider pattern: middleware/CLI depend on KeyStore ABC, not SqliteKeyStore directly"
    - "Per-operation SQLite connections for thread safety in async contexts"
    - "SHA-256 token hashing with hmac.compare_digest constant-time comparison"
    - "Path(__file__).parent.resolve() for db_path default (matches _resolve_chromadb_path)"

key-files:
  created:
    - auth/__init__.py
    - auth/store.py
    - tests/test_auth.py
  modified: []

key-decisions:
  - "KeyStore implemented as ABC (not Protocol) — explicit abstract method enforcement for correctness"
  - "Per-operation connections: sqlite3.connect(self._db_path) called in each method, not stored in __init__"
  - "hmac.compare_digest used even though lookup-by-hash already narrows timing surface — defense in depth"
  - "idx_usage_key index added proactively (zero cost now, avoids migration when usage admin added)"

patterns-established:
  - "Pattern: auth/ package mirrors config/ and models/ — package per subsystem"
  - "Pattern: TDD RED-GREEN with atomic commits per phase"

requirements-completed: [AUTH-01, AUTH-03]

# Metrics
duration: 4min
completed: 2026-04-04
---

# Phase 14 Plan 01: Auth Storage Layer Summary

**KeyStore ABC + SqliteKeyStore with SHA-256 token hashing, hmac constant-time comparison, per-operation SQLite connections, and 13 passing unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-04T07:58:44Z
- **Completed:** 2026-04-04T08:02:52Z
- **Tasks:** 1 (TDD: 2 commits — RED + GREEN)
- **Files created:** 3

## Accomplishments

- KeyStore ABC defines the provider interface (verify_token + log_request abstract methods) — middleware and CLI in Plans 02-03 depend on this, not on SqliteKeyStore directly
- SqliteKeyStore implements full key lifecycle: create (secrets.token_urlsafe, SHA-256 hash stored), verify (constant-time compare), revoke, list (never exposes token_hash)
- usage_log table with idx_usage_key index ready for AUTH-03 logging from middleware
- 13 unit tests cover all AUTH-01 and AUTH-03 behaviors including duplicate name enforcement, revoked token invalidation, and ABC instantiation guard

## Task Commits

TDD task with two commits per protocol:

1. **RED — Failing tests** - `65708f5` (test)
2. **GREEN — Implementation** - `8c34741` (feat)

## Files Created/Modified

- `auth/__init__.py` — Package exports: `from auth.store import KeyStore, SqliteKeyStore`
- `auth/store.py` — KeyStore ABC + SqliteKeyStore; stdlib only (secrets, hashlib, hmac, sqlite3, abc)
- `tests/test_auth.py` — 13 unit tests covering all specified behaviors; uses tmp_path for isolation

## Decisions Made

- **KeyStore as ABC (not Protocol):** ABC gives explicit `TypeError` on direct instantiation, which is testable and verified in `test_keystore_is_abc`. Protocol is structurally typed and would silently allow instantiation.
- **Per-operation connections:** `_connect()` opens a fresh `sqlite3.Connection` each call, satisfying Pitfall 4 (thread safety in async/uvicorn). The connection is cheap and the pattern is correct for stdlib sqlite3.
- **hmac.compare_digest retained:** Even though lookup-by-hash already narrows timing surface, the constant-time final comparison is defense in depth and required by D-11. Cost is negligible.
- **idx_usage_key index added:** AUTH-06 (usage admin endpoint) is deferred but the index is zero cost now and avoids a migration later.

## Deviations from Plan

None — plan executed exactly as written. The research patterns from 14-RESEARCH.md Pattern 1 were followed directly. No bugs found, no blocking issues encountered.

## Issues Encountered

- **Worktree virtualenv missing packages:** The git worktree had a fresh virtualenv without pytest installed (pipenv install did not install dev packages automatically). Fixed by running `pipenv run pip install pytest` — no Pipfile change needed since pytest is already in the Pipfile lock.

## Known Stubs

None — all methods are fully implemented with real behavior. No placeholders, no hardcoded returns.

## Next Phase Readiness

- **Plan 02 (BearerAuthMiddleware):** `auth/store.py` exports `KeyStore` — middleware imports this interface and receives a `SqliteKeyStore` instance at startup. Integration point is confirmed in 14-RESEARCH.md Pattern 2.
- **Plan 03 (manage_keys.py CLI):** `SqliteKeyStore` is fully functional — CLI can be wired directly.
- No blockers. AUTH-DB-PATH env var resolution (D-07, Pitfall 5) is documented in RESEARCH.md and will be handled in server.py during Plan 02.

---
*Phase: 14-auth-module*
*Completed: 2026-04-04*
