---
phase: 14-auth-module
plan: 02
subsystem: auth
tags: [starlette, bearer-token, middleware, uvicorn, sqlite, mcp]

# Dependency graph
requires:
  - phase: 14-01
    provides: KeyStore ABC + SqliteKeyStore — verify_token and log_request methods
provides:
  - BearerAuthMiddleware Starlette middleware (auth/middleware.py)
  - server.py entry point using streamable_http_app() + uvicorn.run() with middleware injected
  - AUTH_DB_PATH env var configurable path (defaults to project_root/auth.db)
  - /health bypasses auth; all other routes require valid bearer token
affects: [14-auth-module, 15-docker-compose, 16-caddy-proxy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BearerAuthMiddleware as BaseHTTPMiddleware subclass with PUBLIC_PATHS allowlist"
    - "server.py entry point: mcp.streamable_http_app() + app.add_middleware() + uvicorn.run()"
    - "AUTH_DB_PATH resolved via Path(__file__).parent.resolve() — matches _resolve_chromadb_path pattern"
    - "_extract_tool_name helper: MCP JSON-RPC body parse for tools/call vs other methods"

key-files:
  created:
    - auth/middleware.py
  modified:
    - auth/__init__.py
    - server.py
    - tests/test_auth.py
    - tests/test_server.py

key-decisions:
  - "BearerAuthMiddleware mounts on mcp.streamable_http_app() return value — mcp.run() provides no middleware hook"
  - "_extract_tool_name logs all authenticated requests (initialize, tools/list, tools/call) — satisfies AUTH-03 literally; method name column allows future filtering"
  - "test_entry_point_transport updated to assert new streamable_http_app()+uvicorn pattern instead of old mcp.run() pattern"

patterns-established:
  - "Pattern: Auth enforcement at Starlette ASGI layer before FastMCP tools execute — tools remain auth-unaware"
  - "Pattern: PUBLIC_PATHS set constant — add new bypass routes in one place"

requirements-completed: [AUTH-02, AUTH-03]

# Metrics
duration: 15min
completed: 2026-04-04
---

# Phase 14 Plan 02: Bearer Auth Middleware Summary

**BearerAuthMiddleware Starlette middleware enforcing 401 on all routes except /health, with per-request usage logging via SqliteKeyStore, and server.py entry point replaced with streamable_http_app() + uvicorn for middleware support**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-04T08:05:00Z
- **Completed:** 2026-04-04T08:17:55Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created `auth/middleware.py` with `BearerAuthMiddleware` — `/health` bypasses auth, all other routes require valid bearer token returning 401 JSON on failure
- Implemented `_extract_tool_name` to parse MCP JSON-RPC body and extract tool/method name for usage logging
- Replaced `mcp.run(transport="streamable-http")` entry point with `streamable_http_app()` + `BearerAuthMiddleware` injection + `uvicorn.run()`
- Added `AUTH_DB_PATH` env var with `Path(__file__).parent.resolve()` default (matches `_resolve_chromadb_path` pattern)
- 21 new auth middleware integration tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing middleware tests** - `0c5b2a5` (test)
2. **Task 1 GREEN: BearerAuthMiddleware implementation** - `9883be5` (feat)
3. **Task 2: Wire auth into server.py entry point** - `5a4519a` (feat)

## Files Created/Modified
- `auth/middleware.py` — BearerAuthMiddleware and _extract_tool_name (new file, 100 lines)
- `auth/__init__.py` — Added BearerAuthMiddleware to exports
- `server.py` — Added auth imports, AUTH_DB_PATH, replaced mcp.run() with streamable_http_app()+uvicorn
- `tests/test_auth.py` — 8 new middleware integration tests + 3 _extract_tool_name unit tests
- `tests/test_server.py` — Updated test_entry_point_transport to assert new entry point pattern

## Decisions Made
- `mcp.run()` replaced with `streamable_http_app()` + `uvicorn.run()` — the only way to inject ASGI middleware into the MCP server
- `_extract_tool_name` logs non-tool MCP methods (initialize, tools/list) by method name — all authenticated requests logged per AUTH-03

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_entry_point_transport assertion now fails after entry point replacement**
- **Found during:** Task 2 (Wire auth middleware into server.py)
- **Issue:** `tests/test_server.py::test_entry_point_transport` asserted `transport="streamable-http"` was present in server.py source — the old `mcp.run()` call. After replacing with `streamable_http_app()` + `uvicorn.run()`, this assertion fails.
- **Fix:** Updated test to assert new pattern: `streamable_http_app()`, `uvicorn.run(`, `add_middleware(BearerAuthMiddleware`, and absence of old `mcp.run()` call.
- **Files modified:** `tests/test_server.py`
- **Verification:** All 66 auth + server tests pass
- **Committed in:** `5a4519a` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — broken test caused by planned entry point replacement)
**Impact on plan:** Necessary update — test was correctly checking the old pattern; updated to check the new pattern. No scope creep.

## Issues Encountered
- Worktree virtualenv had no dependencies installed — required `pipenv install --dev` to install pytest and other dependencies before running tests. This is a standard worktree initialization step.
- `tests/test_phase1.py::TestTalkMetadataDDL::test_talk_metadata_has_expected_columns` fails in this worktree — pre-existing issue (database not populated in worktree environment, confirmed by running the test before any changes). Out of scope; logged here for awareness.

## Next Phase Readiness
- AUTH-02 and AUTH-03 complete: bearer token enforcement layer is live
- AUTH-01 key management CLI (`scripts/manage_keys.py`) is the next plan (14-03)
- server.py entry point is ready for Docker Compose (Phase 15) — uvicorn accepts `--host`/`--port` env var overrides

---
*Phase: 14-auth-module*
*Completed: 2026-04-04*
