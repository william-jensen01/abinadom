# Phase 19: FastMCP + ScaleKit MCP Server — Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the existing manual FastAPI + JSON-RPC server (`server.py`) with a FastMCP-based MCP server, using ScaleKit as the OAuth provider in place of Auth0.

This is a **full replacement**, not an experiment. The new `server.py` becomes the canonical server.

No changes to tools, ChromaDB, pipeline, or data model.

</domain>

<decisions>
## Implementation Decisions

### Scope

- **D-01:** This is a **replacement**, not a side-by-side alternative. The new FastMCP + ScaleKit server replaces `server.py` in place. The existing file is overwritten; user will decide what to do with the old code when the time comes.

- **D-02:** New server file is named `server.py` — same location, clean cutover.

### Auth Integration

- **D-03:** Use **FastMCP's built-in auth support** to integrate ScaleKit as the OAuth provider. Do not use `BaseHTTPMiddleware` — that was the root cause of Phase 16.2's task group failures. ScaleKit acts as the OIDC/OAuth provider; FastMCP's native auth hooks handle the protocol layer.

- **D-04:** The two-mode auth model from Phase 18 carries forward:
  - **Local mode** (`SCALEKIT_*` env vars absent): No authentication required on any endpoint. All requests to `initialize`, `tools/list`, and `tools/call` pass through without any token check. Intended for localhost use.
  - **Remote/hosted mode** (`SCALEKIT_*` env vars set): ScaleKit JWT validation is the sole auth path. `initialize` is unauthenticated; `tools/list` and `tools/call` require a valid JWT.

- **D-05:** `auth/oauth.py` (`JWKSVerifier`) is replaced with ScaleKit's SDK. Auth0 dependency is removed entirely.

### Feature Completeness

- **D-06:** Full feature parity with the current `server.py`, with one exception:
  - **Include:** `search` and `get_talk` tools with all filters, ChromaDB integration, health endpoint (`GET /health`), startup validation (ChromaDB + Ollama health check, 4-collection warmup), session management, lifespan pattern.
  - **Exclude:** `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` endpoints — ScaleKit/the provider handles these; the server does not need to serve them.

- **D-07:** MCP-Session-ID header behavior and session tracking are retained (required by MCP protocol).

### Claude's Discretion

- Exact ScaleKit SDK usage pattern (which classes/methods) — researcher should investigate the SDK
- Whether `auth/oauth.py` is deleted or replaced in-file
- FastMCP version compatibility with mcp==1.26.0 and its auth API
- Env var names for ScaleKit credentials (researcher should confirm from ScaleKit docs)
- Whether any existing tests in `tests/test_server.py` can be adapted or need full rewrite

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Current Server (to be replaced)

- `server.py` — existing FastAPI + manual JSON-RPC dispatcher (Phase 16.2 implementation)
- `auth/oauth.py` — JWKSVerifier (Auth0-specific, to be replaced with ScaleKit)

### Prior Phase Context

- `.planning/phases/16.2-fastapi-mcp-protocol-rewrite/16.2-CONTEXT.md` — documents WHY FastMCP was abandoned (anyio task group error); the new implementation must avoid the same pattern
- `.planning/phases/18-cleanup-of-previous-phases-in-this-milestone/18-CONTEXT.md` — two-mode auth model (local passthrough / remote OAuth) that carries forward

### Tests

- `tests/test_server.py` — existing server tests; assess what carries over vs needs rewrite

</canonical_refs>
