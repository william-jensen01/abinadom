# Phase 19: FastMCP + ScaleKit MCP Server — Context

**Gathered:** 2026-04-15 (updated 2026-04-15)
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

- **D-01:** This is a **replacement**, not a side-by-side alternative. The new FastMCP + ScaleKit server replaces `server.py` in place. The existing file is overwritten.

- **D-02:** New server file is named `server.py` — same location, clean cutover.

### Auth Integration

- **D-03:** Use **FastMCP's built-in `ScalekitProvider`** from `fastmcp.server.auth.providers.scalekit`. Do NOT use `BaseHTTPMiddleware` (root cause of Phase 16.2 anyio task group failures). Do NOT use the `scalekit-sdk-python` SDK — `ScalekitProvider` performs JWKS/JWT verification internally without it.

  ```python
  from fastmcp.server.auth.providers.scalekit import ScalekitProvider

  _auth = ScalekitProvider(
      environment_url=SCALEKIT_ENVIRONMENT_URL,
      resource_id=SCALEKIT_RESOURCE_ID,
      base_url=MCP_BASE_URL,
  )
  mcp = FastMCP("lds-scripture-index", auth=_auth)
  ```

- **D-04:** Two-mode auth model:
  - **Local mode** (`SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID`, or `MCP_BASE_URL` absent): `auth=None` — no authentication on any endpoint. Intended for localhost use.
  - **Remote/hosted mode** (all three env vars set): `auth=ScalekitProvider(...)` — ScaleKit JWT validation required. `initialize` is unauthenticated; `tools/list` and `tools/call` require a valid JWT.
  - Detection condition: `SCALEKIT_ENVIRONMENT_URL and SCALEKIT_RESOURCE_ID and MCP_BASE_URL`

- **D-05:** `auth/oauth.py` (JWKSVerifier) is deleted. No `auth/scalekit_verifier.py` is created — the built-in `ScalekitProvider` eliminates the need for a custom verifier class.

- **D-06 (updated):** `ScalekitProvider` automatically serves the required OAuth discovery endpoints:
  - `/.well-known/oauth-protected-resource` — served natively by `RemoteAuthProvider` (parent class)
  - `/.well-known/oauth-authorization-server` — proxied from ScaleKit by `ScalekitProvider.get_routes()`
  
  These endpoints are required for OAuth 2.1 (OAUTH-01) to work. The server DOES serve them via FastMCP — this is correct and expected. The earlier restriction ("ScaleKit handles these; server does not serve them") applied to the old manual implementation; FastMCP's native handling supersedes it.

- **D-07:** MCP-Session-ID header behavior and session tracking are retained (required by MCP protocol).

- **D-08:** No `required_scopes` enforcement — any valid ScaleKit JWT is accepted. Scope enforcement deferred to future phases.

### Dependencies

- **D-09:** `scalekit-sdk-python` is removed from Pipfile. `ScalekitProvider` performs JWKS-based JWT verification without the ScaleKit SDK. `fastapi` is also removed — the new server.py does not use it.

### Testing

- **D-10:** Use FastMCP's built-in `DebugAuthProvider` (`from fastmcp.server.auth.providers.debug import DebugAuthProvider`) for auth-related unit tests. This issues test tokens without requiring real ScaleKit credentials. No live ScaleKit instance needed in CI.

### Feature Completeness

- **D-11:** Full feature parity with the current `server.py`:
  - **Include:** `search` and `get_talk` tools with all filters, ChromaDB integration, `GET /health` endpoint, startup validation (ChromaDB + Ollama health check, 4-collection warmup), session management, lifespan pattern.
  - **OAuth endpoints:** Served automatically by `ScalekitProvider` (see D-06).

### ScaleKit Setup Requirements

- **D-12:** Before deploying in remote mode, the operator must:
  1. Create an "MCP Server" resource in the ScaleKit Dashboard (navigate to MCP Servers section)
  2. Note the `Resource ID` — this becomes `SCALEKIT_RESOURCE_ID`
  3. Set `SCALEKIT_ENVIRONMENT_URL` to the ScaleKit environment URL (e.g., `https://your-env.scalekit.com`)
  4. Set `MCP_BASE_URL` to the public server URL (e.g., Cloudflare tunnel URL)

### Claude's Discretion

- Whether `auth/oauth.py` is deleted or emptied in-file (deletion preferred)
- Exact lifespan context access pattern (`ctx.lifespan_context["app"]`)
- CORS middleware configuration
- How existing tool function signatures map to native `@mcp.tool()` decorators

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### FastMCP Built-in ScaleKit Provider

- `fastmcp.server.auth.providers.scalekit` — Built-in `ScalekitProvider` class. Constructor params: `environment_url`, `resource_id`, `base_url`. Inspect source at runtime: `python -c "import inspect, fastmcp.server.auth.providers.scalekit as m; print(inspect.getsource(m))"`
- `fastmcp.server.auth.providers.debug` — `DebugAuthProvider` for unit tests

### Current Server (to be replaced)

- `server.py` — existing FastAPI + manual JSON-RPC dispatcher (Phase 16.2 implementation)
- `auth/oauth.py` — JWKSVerifier (Auth0-specific, to be deleted)

### Prior Phase Context

- `.planning/phases/16.2-fastapi-mcp-protocol-rewrite/16.2-CONTEXT.md` — documents WHY BaseHTTPMiddleware was abandoned (anyio task group error); new implementation must avoid the same pattern
- `.planning/phases/18-cleanup-of-previous-phases-in-this-milestone/18-CONTEXT.md` — two-mode auth model (local passthrough / remote OAuth) that carries forward

### Tests

- `tests/test_server.py` — existing server tests; full rewrite required for FastMCP patterns

### ScaleKit Documentation

- https://docs.scalekit.com/mcp/overview/ — ScaleKit MCP Server setup guide (operator reference)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `config/chromadb_client.py` — `get_chromadb_client()` factory used in `_startup()`; no changes needed
- `config/ollama.py` — `resolve_ollama_url()` and `get_embedding_function()`; no changes needed
- `auth/__init__.py` — keep; `auth/oauth.py` delete

### Established Patterns

- **Lifespan**: Current server uses FastAPI lifespan context manager pattern. FastMCP uses the same `@asynccontextmanager` pattern but yields a dict; tools access via `ctx.lifespan_context["app"]` (not `ctx.request_context.lifespan_context` — that was the old bridge pattern)
- **Logging**: stderr-only, established across all phases; carry forward unchanged
- **Custom routes**: `@mcp.custom_route("/health", methods=["GET"])` replaces the old FastAPI route

### Integration Points

- `server.py` → `config/chromadb_client.py` via `get_chromadb_client()`
- `server.py` → `config/ollama.py` via `resolve_ollama_url()` / `get_embedding_function()`
- `tests/test_server.py` → `server.py` via `TestClient(mcp.http_app())`
- `docker-compose.yml` → `.env` for `SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID`, `MCP_BASE_URL`

</code_context>

<specifics>
## Specific Ideas

- Use `ScalekitProvider` directly — no wrapper class, no custom verifier
- `DebugAuthProvider` for all auth-path unit tests in `tests/test_server.py`
- Remove both `fastapi` and `scalekit-sdk-python` from Pipfile in Plan 03

</specifics>

<deferred>
## Deferred Ideas

- Required scopes enforcement — deferred to future phases (D-08)
- Per-user rate limiting — out of scope (AUTH-05, Future Requirements)
- Usage admin endpoint — out of scope (AUTH-06, Future Requirements)

</deferred>

---

*Phase: 19-create-an-alternative-mcp-server-using-fastmcp-and-scalekit*
*Context gathered: 2026-04-15*
