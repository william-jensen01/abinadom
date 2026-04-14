# Phase 18: Cleanup of Previous Phases — Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Close out the v3.0 milestone by removing dead code left over from the FastMCP→FastAPI rewrite and the now-obsolete static bearer token path. Fix broken test collection errors. Update Phase 17 docs to reflect the final auth model. Update requirements traceability.

No new server features. No changes to OAuth flow, ChromaDB, or tool logic.

</domain>

<decisions>
## Implementation Decisions

### Two-Mode Auth Model

- **D-01:** The server supports two deployment modes, distinguished solely by whether `AUTH0_DOMAIN` is set:
  - **Local mode** (`AUTH0_DOMAIN` not set): No authentication required on any endpoint. `initialize`, `tools/list`, and `tools/call` all pass through without any token check. Intended for technical users running the server on `localhost`.
  - **Remote/hosted mode** (`AUTH0_DOMAIN` set): OAuth via Auth0 is the sole auth path. JWKSVerifier (`auth/oauth.py`) handles token validation. Intended for the operator's singleton hosted deployment.

- **D-02:** There is no bearer token fallback. The current `server.py` fallback block (when `AUTH0_DOMAIN` is unset, fall back to `SqliteKeyStore` bearer token check) is replaced with a plain passthrough — no auth check at all in local mode.

### Dead Code Removal

- **D-03:** Remove `auth/middleware.py` (`BearerAuthMiddleware`) entirely. It was already not wired up after Phase 16.2; it references `mcp.streamable_http_app()` which no longer exists.

- **D-04:** Remove `scripts/manage_keys.py`. Static API key issuance has no role in either deployment mode.

- **D-05:** Remove `auth/store.py` (`KeyStore` ABC and `SqliteKeyStore`). No bearer token path = no key store needed. Usage logging was tied to this module; Auth0 provides equivalent logging for the remote case.

- **D-06:** Remove `tests/test_auth.py`. It tests `BearerAuthMiddleware` and `SqliteKeyStore` which are being deleted.

- **D-07:** Keep `auth/oauth.py` (`JWKSVerifier`) — this is the active auth path for remote mode.

### Broken Test Fixes

- **D-08:** Fix `tests/test_phase6.py` and `tests/test_phase6_orchestrator.py` collection errors. Both import `get_chromadb_client` from `extractors.phase6_chromadb_loader` but the function was moved to `config/chromadb_client.py` in Phase 9. Update the import.

- **D-09:** Fix `tests/test_server.py::test_health_returns_200` which fails with 503 because the health endpoint makes live calls to ChromaDB and Ollama. The test should mock those dependency checks.

### Documentation Updates (Phase 17)

- **D-10:** Delete `docs/KEY-MANAGEMENT.md`. It documents `manage_keys.py` commands and `auth.db` inspection — both removed. The README link to it is also removed.

- **D-11:** Update `docs/DEPLOY.md` to remove all references to `auth.db`, `manage_keys.py`, `AUTH_DATA_PATH`, and the key issuance step. The deploy guide covers Docker Compose + Caddy + Cloudflare Tunnel only.

- **D-12:** Update `README.md` to remove the Key Management row from the guides table.

- **D-13:** `docs/CONNECTION.md` stays intact. The `Authorization: Bearer YOUR_ACCESS_TOKEN` references are OAuth access tokens from Auth0 — they remain valid and correct.

### Requirements Traceability

- **D-14:** Update `REQUIREMENTS.md` to correctly reflect final state:
  - AUTH-01 (issue API key) → mark as removed (bearer token path deleted)
  - AUTH-02 (reject invalid tokens) → mark complete (FastAPI per-method auth handles this in remote mode)
  - AUTH-03 (usage log) → mark removed (SqliteKeyStore deleted; Auth0 handles logging)
  - OAUTH-01, OAUTH-02, OAUTH-03 → mark complete (Phase 16.2 delivered these)
  - DOCS-01, DOCS-02, DOCS-03 → mark complete (Phase 17 delivered these)

### Claude's Discretion

- Exact wording of REQUIREMENTS.md status entries
- Whether to archive `docs/KEY-MANAGEMENT.md` to `.planning/` or just delete it
- Order of cleanup tasks within plans

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Active Auth Path

- `auth/oauth.py` — JWKSVerifier, kid-based token routing, `_validate_via_userinfo()` — keep intact
- `server.py` — FastAPI app, per-method auth dispatch, local-mode fallback block (target for D-02 change)

### Dead Code Targets

- `auth/middleware.py` — BearerAuthMiddleware (D-03: delete)
- `scripts/manage_keys.py` — static key CLI (D-04: delete)
- `auth/store.py` — KeyStore ABC + SqliteKeyStore (D-05: delete)
- `tests/test_auth.py` — tests for deleted modules (D-06: delete)

### Broken Tests

- `tests/test_phase6.py` — imports `get_chromadb_client` from wrong module (D-08: fix import)
- `tests/test_phase6_orchestrator.py` — same import error (D-08: fix import)
- `tests/test_server.py::test_health_returns_200` — hits live services (D-09: mock)

### Docs to Update

- `docs/KEY-MANAGEMENT.md` — delete (D-10)
- `docs/DEPLOY.md` — remove bearer token/key management steps (D-11)
- `README.md` — remove Key Management table row (D-12)
- `docs/CONNECTION.md` — no changes needed (D-13)

### Requirements

- `.planning/REQUIREMENTS.md` — traceability update (D-14)

</canonical_refs>

<code_context>
## Existing Code Insights

### What Phase 16.2 Left Behind

- `BearerAuthMiddleware` in `auth/middleware.py` is not imported or instantiated anywhere in `server.py` after the FastAPI rewrite. Confirmed dead.
- `server.py` has a fallback block referencing `SqliteKeyStore` for when `AUTH0_DOMAIN` is unset. This is the target for D-02.

### Test Suite State (as of 2026-04-14)

- 1 failing test: `test_server.py::test_health_returns_200` (503, live deps not running)
- 2 collection errors: `test_phase6.py`, `test_phase6_orchestrator.py` (import path stale)
- All other tests: 421 passing

### ChromaDB Client Import Fix

- `get_chromadb_client` lives in `config/chromadb_client.py`
- Both phase6 test files import it from `extractors.phase6_chromadb_loader` — wrong path since Phase 9 refactor

</code_context>

<specifics>
## Specific Decisions from Discussion

- Local mode = no auth at all (not "optional bearer" — zero auth checks)
- Remote mode = Auth0 OAuth only (no static bearer token fallback)
- `docs/KEY-MANAGEMENT.md` → delete, not repurpose
- Connection guide stays as-is (OAuth access tokens in curl examples are correct)
- Phase 17 docs need updating to reflect the removal of the key management workflow

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 18-cleanup-of-previous-phases-in-this-milestone*
*Context gathered: 2026-04-14*
