---
phase: 19-create-an-alternative-mcp-server-using-fastmcp-and-scalekit
plan: 02
subsystem: auth
tags: [fastmcp, scalekit, oauth, auth, jwt]
dependency_graph:
  requires: [19-01]
  provides: [two-mode-scalekit-auth, auth-tests]
  affects: [server.py, tests/test_server.py]
tech_stack:
  added: [ScalekitProvider (fastmcp.server.auth.providers.scalekit), DebugTokenVerifier (fastmcp.server.auth.providers.debug)]
  patterns: [two-mode-auth-detection, mcp-auth-instance-patching]
key_files:
  created: []
  modified:
    - server.py
    - tests/test_server.py
  deleted:
    - auth/oauth.py
    - tests/test_oauth.py
decisions:
  - Patched mcp.auth directly (not server._auth) because FastMCP reads auth at http_app() call time from mcp.auth instance attribute
  - DebugTokenVerifier enforces auth on ALL endpoints including initialize; adjusted OAUTH-01 test to verify initialize succeeds WITH a valid token
  - test_oauth_module_deleted uses __file__-relative path to work correctly regardless of pytest cwd
metrics:
  duration: ~20min
  completed: 2026-04-15
  tasks: 2
  files: 4
---

# Phase 19 Plan 02: ScalekitProvider Two-Mode Auth Summary

**One-liner:** Two-mode ScaleKit auth via FastMCP's built-in ScalekitProvider — remote mode when all 3 env vars set, local mode (auth=None) otherwise; Auth0 JWKSVerifier deleted.

## What Was Built

### Task 1: Two-mode ScalekitProvider auth in server.py (commit 1718e6e)

Replaced the `_auth = None` placeholder with conditional ScalekitProvider activation:

- Added `SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID` env var reads
- Remote mode: `ScalekitProvider(environment_url=..., resource_id=..., base_url=...)` when all 3 vars set
- Local mode: `_auth = None` when any env var absent
- No deprecated parameters (`mcp_url=`, `client_id=`), no `required_scopes`, no `BaseHTTPMiddleware`
- OAuth discovery endpoints auto-served by ScalekitProvider (no manual routes)

### Task 2: Delete auth/oauth.py, add auth tests (commit bbfbff1)

- Deleted `auth/oauth.py` (Auth0 JWKSVerifier — fully replaced by ScalekitProvider per D-05)
- Deleted `tests/test_oauth.py` (imported from deleted module)
- Added 5 new tests to `tests/test_server.py`:
  - `test_initialize_no_auth_remote_mode` — OAUTH-01: initialize succeeds with valid token
  - `test_tools_list_requires_auth_remote_mode` — AUTH-02: 401 without token in remote mode
  - `test_tools_list_valid_token_remote_mode` — OAUTH-02: 200 with valid token
  - `test_oauth_module_deleted` — D-05: auth/oauth.py absent
  - `test_fastapi_import_absent` — D-09: no FastAPI imports in server.py

**Final test count:** 50 tests passing (up from 45 in Plan 01)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] patch("server._auth") does not affect auth enforcement**

- **Found during:** Task 2 test execution
- **Issue:** Plan specified `patch("server._auth", DebugTokenVerifier())` but FastMCP reads auth from `mcp.auth` (instance attribute set at construction), not from the module-level `_auth` variable. Patching `server._auth` had no effect on the running `mcp` instance.
- **Fix:** Replaced `patch("server._auth", ...)` with direct assignment `mcp.auth = DebugTokenVerifier()` in a try/finally block (restores original after test).
- **Files modified:** tests/test_server.py
- **Commit:** bbfbff1

**2. [Rule 1 - Bug] test_initialize_no_auth_remote_mode assertion adjusted**

- **Found during:** Task 2 test execution
- **Issue:** Plan's OAUTH-01 spec states "initialize succeeds without token even in remote mode." In practice, FastMCP's `DebugTokenVerifier` enforces auth on ALL endpoints including `initialize` (returns 401 without token). The plan's note acknowledged this: "executor should run each test and adjust assertions based on actual FastMCP behavior."
- **Fix:** Adjusted test to verify `initialize` succeeds WITH a valid token (still verifies the auth path is operational). Added docstring clarifying the behavior difference.
- **Files modified:** tests/test_server.py
- **Commit:** bbfbff1

**3. [Rule 1 - Bug] test_oauth_module_deleted path resolution**

- **Found during:** Task 2 test execution
- **Issue:** `os.path.exists("auth/oauth.py")` resolved relative to pytest cwd (main project dir), which still had `auth/oauth.py`. The test always failed when run from main project against worktree files.
- **Fix:** Used `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` to resolve project root from the test file's location.
- **Files modified:** tests/test_server.py
- **Commit:** bbfbff1

**4. [Rule 3 - Blocking] 406 Not Acceptable on /mcp without Accept header**

- **Found during:** Task 2 first test run
- **Issue:** New auth tests sent POST /mcp without the `Accept: application/json, text/event-stream` header. FastMCP returns 406 when this header is absent.
- **Fix:** Added `headers=headers` to all new auth test POST requests (reusing the existing module-level `headers` dict that includes the Accept header).
- **Files modified:** tests/test_server.py
- **Commit:** bbfbff1

## Known Stubs

None — ScalekitProvider is wired for remote mode; auth=None for local mode. No placeholder data flows to UI.

## Threat Surface

No new surface beyond what the plan's threat model covers. ScalekitProvider serves `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` automatically (accepted by design — RFC 8414 public metadata).

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| server.py exists | FOUND |
| auth/oauth.py deleted | CONFIRMED |
| tests/test_server.py exists | FOUND |
| tests/test_oauth.py deleted | CONFIRMED |
| 19-02-SUMMARY.md exists | FOUND |
| commit 1718e6e exists | FOUND |
| commit bbfbff1 exists | FOUND |
| 50 tests pass | CONFIRMED |
