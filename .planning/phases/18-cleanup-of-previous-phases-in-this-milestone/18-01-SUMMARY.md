---
phase: 18-cleanup-of-previous-phases-in-this-milestone
plan: "01"
subsystem: auth
tags: [cleanup, dead-code, auth, oauth, local-mode]
dependency_graph:
  requires: []
  provides: [two-mode-auth-server]
  affects: [server.py, auth/__init__.py]
tech_stack:
  added: []
  patterns: [local-mode-passthrough, oauth-remote-mode]
key_files:
  created: []
  modified:
    - server.py
    - auth/__init__.py
  deleted:
    - auth/middleware.py
    - auth/store.py
    - scripts/manage_keys.py
    - tests/test_auth.py
decisions:
  - "Local mode passthrough: _verify_auth() returns {sub: local} when AUTH0_DOMAIN unset — no token check, all requests pass"
  - "auth/__init__.py updated to export only JWKSVerifier — dead KeyStore/BearerAuthMiddleware exports removed"
metrics:
  duration: 12m
  completed: "2026-04-14"
  tasks_completed: 2
  files_changed: 5
---

# Phase 18 Plan 01: Dead Code Removal and Two-Mode Auth Summary

Remove the static bearer token auth path, implement no-auth local mode in server.py, and delete all dead code files left over from the FastMCP→FastAPI rewrite.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Delete dead code files | 7fbe696 | auth/middleware.py (D), auth/store.py (D), scripts/manage_keys.py (D), tests/test_auth.py (D), auth/__init__.py (M) |
| 2 | Update server.py — local-mode passthrough and SqliteKeyStore removal | f589dd3 | server.py |

## What Was Built

Two-mode auth dispatch in server.py using AUTH0_DOMAIN env var as the selector. When unset, `_verify_auth()` returns `{"sub": "local"}` without any token check (local mode). When set, `_verify_auth()` validates via JWKSVerifier (remote/OAuth mode). The static SqliteKeyStore bearer token path and all associated files are fully removed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated auth/__init__.py to remove dead imports**
- **Found during:** Task 1
- **Issue:** `auth/__init__.py` imported from `auth.store` and `auth.middleware` — both deleted. Would cause ImportError for any code importing from the `auth` package.
- **Fix:** Replaced `auth/__init__.py` contents to export only `JWKSVerifier` from `auth.oauth`.
- **Files modified:** `auth/__init__.py`
- **Commit:** 7fbe696

**2. [Rule 1 - Bug] Removed forbidden strings from module docstring**
- **Found during:** Task 2 acceptance criteria check
- **Issue:** Module docstring contained the literal strings `AUTH_DB_PATH` and `SqliteKeyStore` in a sentence saying they were removed. Acceptance criteria require zero occurrences of these strings in server.py.
- **Fix:** Rephrased docstring line to "Static bearer token path and key store are removed."
- **Files modified:** `server.py`
- **Commit:** f589dd3

## Known Stubs

None — no placeholder data flows to UI rendering.

## Threat Flags

None — this plan removes attack surface (T-18-02, T-18-03 in plan threat model) and adds no new network endpoints or trust boundaries.

## Self-Check: PASSED

- [x] auth/middleware.py deleted: confirmed
- [x] auth/store.py deleted: confirmed
- [x] scripts/manage_keys.py deleted: confirmed
- [x] tests/test_auth.py deleted: confirmed
- [x] server.py contains `if not AUTH0_DOMAIN:` and `return {"sub": "local"}`: confirmed
- [x] server.py contains no `SqliteKeyStore`, `AUTH_DB_PATH`, `_key_store`, `from auth.store`, `from auth.middleware`: confirmed
- [x] server.py syntax valid: confirmed (ast.parse passes)
- [x] Commits exist: 7fbe696, f589dd3 — confirmed via git log
