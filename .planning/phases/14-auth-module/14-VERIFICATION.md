---
phase: 14-auth-module
verified: 2026-04-04T08:30:00Z
status: passed
score: 18/18 must-haves verified
re_verification: false
---

# Phase 14: Auth Module Verification Report

**Phase Goal:** Every request to the server is authenticated and logged by user identity
**Verified:** 2026-04-04T08:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

#### Plan 01 Must-Haves (AUTH-01, AUTH-03 — Storage Layer)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | KeyStore ABC defines verify_token and log_request abstract methods | VERIFIED | auth/store.py lines 38, 46 — both decorated @abstractmethod |
| 2 | SqliteKeyStore creates auth.db with keys and usage_log tables on init | VERIFIED | _init_db() creates both tables via CREATE TABLE IF NOT EXISTS; test_init_creates_tables passes |
| 3 | create_key generates a cryptographically random token and stores only the SHA-256 hash | VERIFIED | secrets.token_urlsafe(32) at line 124; hashlib.sha256(...).hexdigest() at line 125 — raw token returned, hash stored |
| 4 | verify_token returns key name for valid tokens and None for invalid tokens | VERIFIED | test_verify_token_valid and test_verify_token_invalid both pass |
| 5 | log_request inserts a row into usage_log with key_name, tool_name, and ISO 8601 UTC timestamp | VERIFIED | test_log_request verifies exact row values in usage_log |
| 6 | revoke_key removes a key and list_keys returns names and dates without tokens | VERIFIED | test_revoke_key_existing, test_list_keys pass; token_hash never returned from list_keys |

#### Plan 02 Must-Haves (AUTH-02, AUTH-03 — Middleware + Server Wiring)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 7 | A request to /health without a token returns 200 (not 401) | VERIFIED | test_health_bypass passes; PUBLIC_PATHS = {"/health"} in middleware.py |
| 8 | A request to /mcp without a token returns 401 with JSON error body | VERIFIED | test_no_token_returns_401 passes; "Missing bearer token" confirmed |
| 9 | A request to /mcp with an invalid token returns 401 with JSON error body | VERIFIED | test_invalid_token_returns_401 passes; "Invalid token" confirmed |
| 10 | A request to /mcp with a valid token passes through to FastMCP | VERIFIED | test_valid_token_passes_through passes (status != 401) |
| 11 | Every authenticated request creates a row in usage_log with tool_name extracted from MCP JSON-RPC body | VERIFIED | test_usage_logged_on_valid_request passes; rows[0][1] == "search" for tools/call |
| 12 | server.py entry point uses mcp.streamable_http_app() + uvicorn.run() instead of mcp.run() | VERIFIED | server.py lines 451-455 confirmed; grep for mcp.run returns 0 matches |
| 13 | Existing search and get_talk tools work unchanged for authenticated requests | VERIFIED | Full suite of 470 tests passes — no regressions |

#### Plan 03 Must-Haves (AUTH-01 — CLI)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 14 | Operator can run manage_keys.py create --name alice and receive a bearer token printed to stdout | VERIFIED | test_create_command passes; "it will not be shown again" in stdout |
| 15 | Operator can run manage_keys.py revoke --name alice and the key is removed | VERIFIED | test_revoke_command passes; verify_token returns None after revoke |
| 16 | Operator can run manage_keys.py list and see key names and creation dates but never tokens | VERIFIED | test_list_command passes; token_hash excluded from list_keys() |
| 17 | Running create with a duplicate name fails with a clear error (not a traceback) | VERIFIED | test_create_duplicate passes; "Traceback" not in stderr assertion passes |
| 18 | Running revoke with a nonexistent name prints error to stderr and exits 1 | VERIFIED | test_revoke_nonexistent passes; returncode == 1 and "No key named" in stderr |

**Score:** 18/18 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `auth/__init__.py` | Package exports for KeyStore, SqliteKeyStore, BearerAuthMiddleware | VERIFIED | Exports all three; 4 lines |
| `auth/store.py` | KeyStore ABC and SqliteKeyStore implementation | VERIFIED | 200 lines; full implementation with all methods |
| `auth/middleware.py` | BearerAuthMiddleware Starlette middleware | VERIFIED | 109 lines; full dispatch + _extract_tool_name |
| `server.py` | Updated entry point with middleware injection | VERIFIED | AUTH_DB_PATH, SqliteKeyStore, BearerAuthMiddleware, uvicorn.run all present |
| `scripts/manage_keys.py` | CLI for API key management | VERIFIED | 68 lines; create/revoke/list subcommands fully implemented |
| `tests/test_auth.py` | Unit + integration tests covering all behaviors | VERIFIED | 454 lines; 26 tests covering store, middleware, CLI |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| auth/store.py | auth.db (SQLite) | sqlite3.connect in _connect() | WIRED | Line 84: `conn = sqlite3.connect(self._db_path)` |
| auth/store.py | secrets stdlib | secrets.token_urlsafe(32) in create_key | WIRED | Line 124: `token = secrets.token_urlsafe(32)` |
| auth/store.py | hmac stdlib | hmac.compare_digest in verify_token | WIRED | Line 157: `if hmac.compare_digest(row["token_hash"], token_hash)` |
| auth/middleware.py | auth/store.py | KeyStore interface (verify_token + log_request) | WIRED | Lines 69, 80: `self._store.verify_token(raw_token)`, `self._store.log_request(...)` |
| server.py | auth/middleware.py | app.add_middleware(BearerAuthMiddleware, store=store) | WIRED | Line 454: `app.add_middleware(BearerAuthMiddleware, store=store)` |
| server.py | auth/store.py | SqliteKeyStore(AUTH_DB_PATH) instantiation | WIRED | Line 452: `store = SqliteKeyStore(AUTH_DB_PATH)` |
| scripts/manage_keys.py | auth/store.py | SqliteKeyStore import and method calls | WIRED | Line 16: `from auth.store import SqliteKeyStore`; lines 37-38, 42, 49, 53, 57 |
| scripts/manage_keys.py | AUTH_DB_PATH env var | os.environ.get with Path(__file__) default | WIRED | Lines 18-21: `AUTH_DB_PATH = os.environ.get("AUTH_DB_PATH", ...)` |

---

### Data-Flow Trace (Level 4)

No components in this phase render dynamic UI data — all artifacts are storage layer, middleware, and CLI. Level 4 trace is not applicable. The data flow that matters is:

- Token creation path: `secrets.token_urlsafe` → `hashlib.sha256` → `INSERT INTO keys` — all confirmed in store.py
- Auth enforcement path: `Authorization` header → `verify_token` → `log_request` → `INSERT INTO usage_log` — all confirmed in middleware.py and verified by test_usage_logged_on_valid_request
- Server wiring path: `SqliteKeyStore(AUTH_DB_PATH)` → `app.add_middleware(BearerAuthMiddleware, store=store)` → `uvicorn.run(app)` — confirmed in server.py lines 451-455

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Auth test suite passes | pipenv run py -m pytest tests/test_auth.py -x -q | 26 passed in 3.14s | PASS |
| Full test suite passes (no regressions) | pipenv run py -m pytest tests/ -x -q | 470 passed in 26.24s | PASS |
| Auth package imports cleanly | pipenv run py -c "from auth.store import ...; from auth.middleware import ..." | "imports OK" | PASS |
| CLI help exits 0 | pipenv run py scripts/manage_keys.py --help | shows usage with create/revoke/list | PASS |
| Old mcp.run() is removed | grep -c "mcp.run" server.py | 0 | PASS |
| Middleware wiring present | grep "add_middleware" server.py | line 454: app.add_middleware(BearerAuthMiddleware, store=store) | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| AUTH-01 | 14-01, 14-03 | Operator can issue a named API key for a user | SATISFIED | SqliteKeyStore.create_key() returns raw token; manage_keys.py create --name prints token once |
| AUTH-02 | 14-02 | Server rejects requests without a valid bearer token with 401 | SATISFIED | BearerAuthMiddleware returns 401 JSON for missing/invalid tokens; test_no_token_returns_401 and test_invalid_token_returns_401 pass |
| AUTH-03 | 14-01, 14-02 | Server logs tool name, timestamp, and user for every authenticated request | SATISFIED | log_request() inserts (key_name, tool_name, timestamp) into usage_log; middleware calls it on every successful auth; test_usage_logged_on_valid_request verifies exact values |

**All three required requirement IDs (AUTH-01, AUTH-02, AUTH-03) are satisfied.**

No orphaned requirements: REQUIREMENTS.md maps AUTH-01, AUTH-02, AUTH-03 to Phase 14 and all three are claimed and fulfilled across the three plans.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | None found |

Stub scan results:
- No TODO/FIXME/HACK/PLACEHOLDER comments in auth/ or scripts/manage_keys.py
- No `return null` / `return {}` / `return []` patterns in auth implementations
- No hardcoded empty data flows to rendering
- No console.log-only implementations
- All abstract methods have concrete implementations in SqliteKeyStore

---

### Human Verification Required

None. All behaviors verifiable programmatically:

- 401/200 responses are covered by integration tests with Starlette TestClient
- Usage log population is verified by direct SQLite inspection in test_usage_logged_on_valid_request
- Token shown-once guarantee is structural (raw token returned from create_key, never stored)
- CLI error handling tested via subprocess with returncode and stderr assertions

The only behavior that would benefit from a live-server test — verifying the real MCP server enforces auth end-to-end before tools execute — is deferred to Phase 15 when Docker Compose brings up the full stack. This is acceptable because the middleware integration is fully tested against the Starlette ASGI layer and the server.py wiring is verified by code inspection and test_server.py assertions.

---

## Summary

Phase 14 fully achieves its goal: **every request to the server is authenticated and logged by user identity.**

The three-layer implementation is complete and wired:

1. **Storage layer** (Plan 01): KeyStore ABC + SqliteKeyStore with SHA-256 hashing, hmac constant-time comparison, per-operation connections, and auto-created schema.
2. **Enforcement layer** (Plan 02): BearerAuthMiddleware intercepts all non-/health requests, returns 401 on missing/invalid tokens, logs (key_name, tool_name, timestamp) on success. Server entry point replaced with streamable_http_app() + uvicorn to enable middleware injection.
3. **Operator interface** (Plan 03): manage_keys.py CLI with create/revoke/list subcommands, clean error handling, and token-shown-once guarantee.

All 26 auth tests pass. All 470 total tests pass (no regressions). AUTH-01, AUTH-02, and AUTH-03 are fully satisfied.

---

_Verified: 2026-04-04T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
