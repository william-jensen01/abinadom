# Phase 19: FastMCP + ScaleKit MCP Server — Research

**Researched:** 2026-04-15
**Domain:** FastMCP (mcp==1.26.0), ScaleKit JWT validation, MCP server replacement
**Confidence:** HIGH (all major claims verified against installed packages)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** This is a replacement, not a side-by-side alternative. The new FastMCP + ScaleKit server replaces `server.py` in place. The existing file is overwritten.
- **D-02:** New server file is named `server.py` — same location, clean cutover.
- **D-03:** Use FastMCP's built-in auth support to integrate ScaleKit as the OAuth provider. Do NOT use `BaseHTTPMiddleware` — that was the root cause of Phase 16.2's task group failures. ScaleKit acts as the OIDC/OAuth provider; FastMCP's native auth hooks handle the protocol layer.
- **D-04:** Two-mode auth model carries forward:
  - Local mode (`SCALEKIT_*` env vars absent): No authentication required on any endpoint. All requests pass through without any token check.
  - Remote/hosted mode (`SCALEKIT_*` env vars set): ScaleKit JWT validation is the sole auth path. `initialize` is unauthenticated; `tools/list` and `tools/call` require a valid JWT.
- **D-05:** `auth/oauth.py` (JWKSVerifier) is replaced with ScaleKit's SDK. Auth0 dependency is removed entirely.
- **D-06:** Full feature parity:
  - Include: `search` and `get_talk` tools, ChromaDB integration, `GET /health`, startup validation (ChromaDB + Ollama health check, 4-collection warmup), session management, lifespan pattern.
  - Exclude: `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` — ScaleKit/the provider handles these.
- **D-07:** MCP-Session-ID header behavior and session tracking are retained.

### Claude's Discretion

- Exact ScaleKit SDK usage pattern (which classes/methods) — researcher should investigate the SDK
- Whether `auth/oauth.py` is deleted or replaced in-file
- FastMCP version compatibility with mcp==1.26.0 and its auth API
- Env var names for ScaleKit credentials (researcher should confirm from ScaleKit docs)
- Whether any existing tests in `tests/test_server.py` can be adapted or need full rewrite

### Deferred Ideas (OUT OF SCOPE)

None stated in CONTEXT.md.
</user_constraints>

---

## Summary

The existing `server.py` is a hand-rolled FastAPI + JSON-RPC dispatcher (Phase 16.2) that replaced an earlier FastMCP attempt abandoned due to `BaseHTTPMiddleware` causing anyio task group failures. Phase 19 reverses that decision and brings FastMCP back, but with ScaleKit instead of Auth0 and using FastMCP's **native** auth system (`TokenVerifier` protocol + Starlette's `AuthenticationMiddleware`) which does NOT use `BaseHTTPMiddleware`.

The installed `mcp==1.26.0` package includes a complete FastMCP implementation with lifespan support, `custom_route` decorator for `/health`, and a `TokenVerifier` protocol for custom JWT verification. ScaleKit's Python SDK (`scalekit-sdk-python==2.7.1`) provides synchronous JWT validation via `ScalekitClient.validate_token()` which must be wrapped in `asyncio.to_thread()` for use in async `TokenVerifier.verify_token()`.

**Primary recommendation:** Implement a `ScalekitTokenVerifier` class satisfying the `TokenVerifier` protocol. In local mode (no `SCALEKIT_*` vars), pass `token_verifier=None` and `auth=None` to FastMCP — all endpoints are open. In remote mode, pass the verifier with `AuthSettings`; FastMCP enforces auth at the HTTP level for all `/mcp` requests. Tool logic (`search`, `get_talk`) migrates unchanged; the `ctx` parameter must be annotated as `Context` (not `ctx=None`) for automatic injection.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mcp (FastMCP) | 1.26.0 | MCP server framework + protocol handling | Already installed; FastMCP is the submodule of mcp |
| scalekit-sdk-python | 2.7.1 | ScaleKit OAuth JWT validation | Official Python SDK for ScaleKit; latest as of 2026-04-15 |
| uvicorn | 0.42.0 | ASGI server | Already installed; used by FastMCP |
| starlette | 1.0.0 | ASGI routing + auth middleware | FastMCP's internal framework |

[VERIFIED: pip list on virtualenv]

### Supporting (unchanged from current server)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| chromadb | 1.5.5 | Vector database client | All tool calls |
| httpx | 0.28.1 | Async HTTP client | Health checks |
| PyJWT | 2.12.1 | JWT parsing (used by scalekit-sdk-python) | Already pulled in by scalekit |

### Packages to ADD

```bash
pipenv install scalekit-sdk-python
```

[VERIFIED: pip install dry-run confirmed compatibility with existing virtualenv]

### Packages to REMOVE from Pipfile

- `fastapi` — FastMCP uses Starlette directly; FastAPI is no longer needed [VERIFIED: FastMCP uses `starlette.routing.Route`, not FastAPI]

Note: `fastapi` can remain installed (unused) without harm, but should be removed from Pipfile per clean-cutover intent.

### Version verification

| Package | Verified Version | Date |
|---------|-----------------|------|
| mcp | 1.26.0 | 2026-04-15 |
| scalekit-sdk-python | 2.7.1 | 2026-04-15 (latest) |
| starlette | 1.0.0 | 2026-04-15 |

[VERIFIED: `pipenv run pip show` and `pipenv run pip list`]

---

## Architecture Patterns

### FastMCP Instantiation (Two-Mode Auth)

```python
# Source: verified via inspect of mcp.server.fastmcp.FastMCP.__init__

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.provider import TokenVerifier, AccessToken

# Local mode — no auth
mcp = FastMCP(
    name="lds-scripture-index",
    instructions=MCP_INSTRUCTIONS,
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",   # or "/" for backward compat — see Open Questions
    lifespan=lifespan,
)

# Remote mode — auth enabled
mcp = FastMCP(
    name="lds-scripture-index",
    instructions=MCP_INSTRUCTIONS,
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",
    lifespan=lifespan,
    token_verifier=ScalekitTokenVerifier(sk_client, audience=SCALEKIT_RESOURCE_ID),
    auth=AuthSettings(
        issuer_url=SCALEKIT_ENVIRONMENT_URL,
        resource_server_url=MCP_BASE_URL,  # Your server's public URL
    ),
)
```

[VERIFIED: mcp==1.26.0 FastMCP.__init__ signature]

### Custom ScalekitTokenVerifier

```python
# Source: verified via inspect of mcp.server.auth.provider.TokenVerifier + scalekit.ScalekitClient

import asyncio
from mcp.server.auth.provider import TokenVerifier, AccessToken
from scalekit import ScalekitClient

class ScalekitTokenVerifier:
    """TokenVerifier implementation backed by ScalekitClient.validate_token."""

    def __init__(self, client: ScalekitClient, audience: str | None = None):
        self._client = client
        self._audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate a bearer token via ScaleKit JWKS. Returns AccessToken or None."""
        try:
            payload = await asyncio.to_thread(
                self._client.validate_token,
                token,
                audience=self._audience,
            )
            return AccessToken(
                token=token,
                client_id=payload.get("sub", ""),
                scopes=payload.get("scp", payload.get("scope", "")).split()
                if isinstance(payload.get("scp", payload.get("scope", "")), str)
                else payload.get("scp", []),
                expires_at=payload.get("exp"),
            )
        except Exception:
            return None
```

**Key details verified by inspection:**
- `ScalekitClient.validate_token(token, audience=...)` is **synchronous** (uses `requests.get` internally). Must use `asyncio.to_thread()` in async context. [VERIFIED: scalekit/core.py source]
- `validate_token` fetches JWKS from `{SCALEKIT_ENVIRONMENT_URL}/keys` on first call, then caches. [VERIFIED: scalekit/core.py `JWKS_ENDPOINT = "/keys"`]
- Returns the JWT payload dict on success, raises `ScalekitValidateTokenFailureException` on failure. [VERIFIED: scalekit/client.py]
- `TokenVerifier.verify_token` must be `async` per the protocol. [VERIFIED: mcp.server.auth.provider.TokenVerifier source]
- `AccessToken` requires `token`, `client_id`, `scopes` fields. [VERIFIED: mcp.server.auth.provider.AccessToken source]

### Tool Functions (Context Injection Pattern)

FastMCP injects `Context` by **type annotation**, not by parameter name.

```python
# Source: verified via mcp.server.fastmcp.utilities.context_injection.find_context_parameter

from mcp.server.fastmcp import FastMCP, Context

@mcp.tool()
async def search(
    query: str,
    speaker: str | None = None,
    year: int | None = None,
    season: str | None = None,
    collection: str = "paragraphs",
    limit: int = 5,
    ctx: Context,  # MUST be annotated as Context — not ctx=None
) -> str:
    app_ctx: AppContext = ctx.request_context.lifespan_context  # VERIFIED works
    ...
```

**BREAKING CHANGE from current server.py:** The current tools have `ctx=None` with no type annotation. FastMCP finds the context parameter by looking for a `Context` type annotation. Without it, no injection occurs. Both `search()` and `get_talk()` must have `ctx: Context` added to their signatures.

**The `_FakeMCPCtx` bridge class is deleted.** FastMCP's native `Context` provides `ctx.request_context.lifespan_context` directly when `lifespan` is configured. [VERIFIED: mcp.server.lowlevel.server.RequestContext has `lifespan_context` field]

### Health Endpoint via custom_route

```python
# Source: verified via inspect of FastMCP.custom_route

@mcp.custom_route("/health", methods=["GET"])
async def health_endpoint(request: Request) -> JSONResponse:
    """GET /health — live dependency checks."""
    ...
```

**Key:** `custom_route` routes are explicitly documented as **not requiring authorization**. [VERIFIED: FastMCP.custom_route docstring]

### Lifespan Pattern

```python
# Source: verified via FastMCP.__init__ and lifespan_wrapper source

from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP

@asynccontextmanager
async def lifespan(server: FastMCP):
    ctx = _startup()        # same _startup() function, unchanged
    yield ctx               # yields AppContext — accessible as ctx.request_context.lifespan_context in tools
```

FastMCP wraps this via `lifespan_wrapper()` which adapts it for the low-level MCPServer. The `yield`ed value becomes `lifespan_context` in `RequestContext`. [VERIFIED: lifespan_wrapper source]

### Auth Enforcement Behavior (CRITICAL DESIGN FINDING)

When `token_verifier` is set, `FastMCP.streamable_http_app()` wraps the entire `/mcp` endpoint with `RequireAuthMiddleware`. This means **all** JSON-RPC methods sent to `/mcp` — including `initialize` — require a valid bearer token in remote mode.

This differs from the current `server.py` where `initialize` is explicitly unauthenticated at the dispatcher level.

**The middleware chain is:**
1. `AuthenticationMiddleware` (Starlette, NOT BaseHTTPMiddleware) — reads bearer token, calls `BearerAuthBackend`
2. `AuthContextMiddleware` — stores auth user in contextvar
3. `RequireAuthMiddleware` — gates the `/mcp` ASGI endpoint, returns 401 if unauthenticated

[VERIFIED: mcp.server.fastmcp.server streamable_http_app source, mcp.server.auth.middleware.bearer_auth source]

**IMPORTANT:** None of these use `BaseHTTPMiddleware`. They are pure ASGI middleware using the `__call__(scope, receive, send)` protocol. The Phase 16.2 failure was specific to `BaseHTTPMiddleware` + anyio task groups — that class is not present here.

**Implication for D-04:** In remote mode with FastMCP auth, `initialize` will require a token. This deviates from D-04's "initialize is unauthenticated." The planner must decide: accept this deviation (FastMCP always-auth remote mode) or implement a workaround. See Open Questions.

### ScalekitClient Initialization

```python
# Source: verified via scalekit.ScalekitClient.__init__ signature

from scalekit import ScalekitClient

client = ScalekitClient(
    env_url=os.environ["SCALEKIT_ENVIRONMENT_URL"],
    client_id=os.environ["SCALEKIT_CLIENT_ID"],
    client_secret=os.environ["SCALEKIT_CLIENT_SECRET"],
)
```

**Env var names (from GitHub example + PyPI docs):**

| Env Var | Purpose |
|---------|---------|
| `SCALEKIT_ENVIRONMENT_URL` | ScaleKit tenant URL (e.g., `https://your-env.scalekit.com`) |
| `SCALEKIT_CLIENT_ID` | OAuth client ID |
| `SCALEKIT_CLIENT_SECRET` | OAuth client secret |
| `SCALEKIT_RESOURCE_ID` | Resource identifier / audience (used as `audience` param in validate_token) |

[CITED: https://github.com/scalekit-inc/fastmcp-scalekit-example] [VERIFIED: ScalekitClient.__init__ signature via inspect]

**ScaleKit JWKS endpoint:** `{SCALEKIT_ENVIRONMENT_URL}/keys` [VERIFIED: scalekit/core.py `JWKS_ENDPOINT = "/keys"`]

### Entry Point

```python
# Source: FastMCP.run_streamable_http_async source

if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_streamable_http_async())
```

Or equivalently:

```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

FastMCP internally uses uvicorn with the Starlette app from `streamable_http_app()`.

### Recommended Project Structure

No structural changes required. All module paths stay the same:

```
server.py            # FastMCP-based replacement (was FastAPI+JSON-RPC)
auth/
  oauth.py           # DELETE or gut (JWKSVerifier replaced by ScalekitTokenVerifier in server.py)
config/              # unchanged
extractors/          # unchanged
tests/
  test_server.py     # significant rewrite required
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bearer token extraction from headers | Custom header parsing | `mcp.server.auth.middleware.bearer_auth.BearerAuthBackend` | Already wired into FastMCP auth flow |
| JWKS key fetching and caching | Manual requests + key cache | `ScalekitClient` (caches JWKS on first call) | SDK handles key caching automatically |
| JWT signature verification | `jwt.decode()` manually | `ScalekitClient.validate_token()` | Handles JWKS fetch, kid lookup, RS256 decode |
| ASGI middleware for auth | `BaseHTTPMiddleware` subclass | FastMCP's `TokenVerifier` protocol | BaseHTTPMiddleware breaks anyio (Phase 16.2 lesson) |
| Protected resource metadata endpoint | Custom route | ScaleKit handles this — D-06 says EXCLUDE it | Provider serves well-known endpoints |
| Session management | Custom dict | FastMCP handles MCP session lifecycle internally | StreamableHTTPSessionManager in FastMCP |

---

## Runtime State Inventory

Phase 19 is a code replacement, not a rename/rebrand. No runtime state affected.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — ChromaDB data stays unchanged | None |
| Live service config | None — Docker Compose config unchanged | None |
| OS-registered state | None | None |
| Secrets/env vars | Auth0 vars (`AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `AUTH0_CLIENT_SECRET`, `MCP_BASE_URL`) replaced with ScaleKit vars | Update `.env` + Compose `.env.example` |
| Build artifacts | `requirements.txt` committed to git from Pipfile.lock (Docker build) | Regenerate after `pipenv install scalekit-sdk-python` |

**Env var migration:**

| Old (Auth0) | New (ScaleKit) | Notes |
|-------------|---------------|-------|
| `AUTH0_DOMAIN` | `SCALEKIT_ENVIRONMENT_URL` | Detection var for remote mode |
| `AUTH0_AUDIENCE` | `SCALEKIT_RESOURCE_ID` | Used as JWT audience |
| `AUTH0_CLIENT_SECRET` | `SCALEKIT_CLIENT_SECRET` | Part of ScalekitClient init |
| — | `SCALEKIT_CLIENT_ID` | New, required |
| `MCP_BASE_URL` | `MCP_BASE_URL` | Unchanged |

---

## Common Pitfalls

### Pitfall 1: BaseHTTPMiddleware (Phase 16.2 Root Cause)
**What goes wrong:** `RuntimeError: Task group is not initialized` at runtime under asyncio/anyio.
**Why it happens:** FastMCP uses anyio task groups internally; `BaseHTTPMiddleware.call_next()` wraps downstream in a new async scope, severing the task group context.
**How to avoid:** Never use `BaseHTTPMiddleware`. FastMCP's auth uses `AuthenticationMiddleware` (Starlette, pure ASGI `__call__`) and `RequireAuthMiddleware` (custom ASGI, also pure `__call__`). Neither is `BaseHTTPMiddleware`. [VERIFIED: starlette.middleware.authentication.AuthenticationMiddleware import confirmed in FastMCP source]
**Warning signs:** Any `BaseHTTPMiddleware` import in server.py.

### Pitfall 2: Missing Context Type Annotation in Tools
**What goes wrong:** `ctx` receives `None` at runtime; `ctx.request_context.lifespan_context` raises `AttributeError`.
**Why it happens:** FastMCP injects `Context` by scanning type annotations via `get_type_hints()`. Parameter named `ctx=None` with no annotation is treated as a normal tool argument.
**How to avoid:** Always annotate: `ctx: Context` (not `ctx=None`, not `ctx: Context | None`).
**Warning signs:** Tool tests that construct `_FakeMCPCtx` and pass it directly still pass, but integration tests fail.

### Pitfall 3: Calling Synchronous ScalekitClient in Async Context
**What goes wrong:** `ScalekitClient.validate_token()` calls `requests.get()` (blocking I/O). Running it directly in an async function blocks the event loop.
**Why it happens:** `scalekit-sdk-python` uses synchronous `requests`, not `httpx`.
**How to avoid:** Always wrap in `asyncio.to_thread()`:
```python
payload = await asyncio.to_thread(self._client.validate_token, token, audience=audience)
```
**Warning signs:** High latency on first token validation (JWKS fetch), or event loop blocking detected in profiling.

### Pitfall 4: FastMCP Auth Enforces Token on ALL /mcp Requests
**What goes wrong:** MCP `initialize` (which MCP spec allows unauthenticated) receives 401 in remote mode.
**Why it happens:** `RequireAuthMiddleware` wraps the entire `/mcp` ASGI endpoint at the HTTP level. It cannot distinguish JSON-RPC method names.
**How to avoid:** Planner must decide: (a) accept always-auth in remote mode (requires client to have token before initialize — possible with ScaleKit's auth flow), or (b) configure `token_verifier=None` and do per-tool validation manually (loses initialize protection but matches D-04).
**Warning signs:** MCP client fails at `initialize` step with 401.

### Pitfall 5: streamable_http_path Default is /mcp, not /
**What goes wrong:** Existing MCP clients configured to connect to `https://host/` break after upgrade because FastMCP listens at `/mcp` by default.
**Why it happens:** FastMCP `streamable_http_path` parameter defaults to `"/mcp"`.
**How to avoid:** Set `streamable_http_path="/"` in FastMCP constructor to match current behavior.
**Warning signs:** Client sends `POST /` and receives 404 or 405 from the Starlette router.

### Pitfall 6: DNS Rebinding Protection Auto-Enabled for localhost
**What goes wrong:** FastMCP silently adds transport security settings when `host in ("127.0.0.1", "localhost", "::1")`, blocking requests from Docker network or external hosts.
**Why it happens:** FastMCP.__init__ auto-enables DNS rebinding protection for localhost hosts.
**How to avoid:** Use `host="0.0.0.0"` for Docker deployments (no auto-protection applied). [VERIFIED: FastMCP.__init__ source]

### Pitfall 7: test_fastmcp_removed Must Be Deleted
**What goes wrong:** Existing test `test_fastmcp_removed` asserts `"from mcp.server.fastmcp import FastMCP" not in source`. The new server.py will fail this assertion.
**Why it happens:** Phase 16.2 added this test to guard against bringing FastMCP back.
**How to avoid:** Delete or replace `test_fastmcp_removed` in `tests/test_server.py`.

---

## Code Examples

### Complete Minimal FastMCP Server Pattern (verified)

```python
# Source: verified via FastMCP.__init__, streamable_http_app, custom_route, lifespan_wrapper

from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.provider import TokenVerifier, AccessToken
from starlette.requests import Request
from starlette.responses import JSONResponse
import asyncio
import os

@asynccontextmanager
async def lifespan(server: FastMCP):
    ctx = _startup()   # returns AppContext
    yield ctx

# Build verifier only when ScaleKit env vars are present
_sk_verifier = None
SCALEKIT_ENV_URL = os.environ.get("SCALEKIT_ENVIRONMENT_URL", "")
if SCALEKIT_ENV_URL:
    from scalekit import ScalekitClient
    _sk_client = ScalekitClient(
        env_url=SCALEKIT_ENV_URL,
        client_id=os.environ["SCALEKIT_CLIENT_ID"],
        client_secret=os.environ["SCALEKIT_CLIENT_SECRET"],
    )
    _sk_verifier = ScalekitTokenVerifier(_sk_client, audience=os.environ.get("SCALEKIT_RESOURCE_ID"))

# Mode-conditional construction
mcp_kwargs = dict(
    name="lds-scripture-index",
    instructions=MCP_INSTRUCTIONS,
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/",   # match existing client config
    lifespan=lifespan,
)
if _sk_verifier:
    mcp_kwargs["token_verifier"] = _sk_verifier
    mcp_kwargs["auth"] = AuthSettings(
        issuer_url=SCALEKIT_ENV_URL,
        resource_server_url=MCP_BASE_URL or SCALEKIT_ENV_URL,
    )

mcp = FastMCP(**mcp_kwargs)

@mcp.tool()
async def search(query: str, ctx: Context) -> str:
    app_ctx = ctx.request_context.lifespan_context
    ...

@mcp.custom_route("/health", methods=["GET"])
async def health_endpoint(request: Request) -> JSONResponse:
    ...

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

### ScalekitTokenVerifier (verified)

```python
# Source: verified via scalekit.ScalekitClient.validate_token + TokenVerifier protocol

import asyncio
from mcp.server.auth.provider import TokenVerifier, AccessToken
from scalekit import ScalekitClient

class ScalekitTokenVerifier:
    def __init__(self, client: ScalekitClient, audience: str | None = None):
        self._client = client
        self._audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            payload = await asyncio.to_thread(
                self._client.validate_token, token, audience=self._audience
            )
        except Exception:
            return None
        return AccessToken(
            token=token,
            client_id=payload.get("sub", ""),
            scopes=[],          # ScaleKit M2M tokens may not have scopes
            expires_at=payload.get("exp"),
        )
```

---

## Test Analysis: What Carries Over vs. Full Rewrite

### Tests That Carry Over Unchanged (pure logic, no server dependency)

| Test Class/Function | Reason |
|--------------------|--------|
| `TestBuildWhereFilter` (4 tests) | Pure function, no import change |
| `TestMatchesSpeaker` (5 tests) | Pure function, no import change |
| `TestFormatSearchResult` (3 tests) | Pure function, no import change |
| `TestParseTalkId` (4 tests) | Pure function, no import change |
| `test_chromadb_client_*` (2 tests) | Tests `config.chromadb_client`, unaffected |
| `test_ollama_url_*` (3 tests) | Tests `config.ollama`, unaffected |
| `test_search_docstring_*` | Tests tool docstrings, no change needed |
| `test_get_talk_docstring_*` | Tests tool docstrings, no change needed |

### Tests That Need Adaptation

| Test | Change Required |
|------|----------------|
| `TestSearchTool` (6 tests) | `_make_mock_ctx` must use FastMCP Context, not `_FakeMCPCtx`. Or tools can be tested by calling them with a real mock ctx built via `MagicMock` where `ctx.request_context.lifespan_context` returns `AppContext`. Pattern unchanged — just remove `_FakeMCPCtx`. |
| `TestGetTalkTool` (4 tests) | Same as above |
| `test_chromadb_missing_collection_exits` | Imports `_load_collections` from `server` — function stays |
| `test_ollama_failure_is_non_fatal` | Imports `_check_ollama` from `server` — function stays |
| `test_all_collections_warmed` | Imports `_load_collections` from `server` — function stays |
| `test_check_ollama_passes_resolved_url` | Stays; `_check_ollama` unchanged |

### Tests That Need Full Rewrite

| Test | Reason |
|------|--------|
| `test_fastmcp_removed` | Must be deleted — new server.py imports FastMCP |
| `test_no_stdio_references` | Still valid (should still pass) |
| `test_health_returns_200/503` | `build_app()` → `mcp.streamable_http_app()`; `TestClient` works with Starlette app |
| All dispatcher tests (`test_initialize_no_auth`, `test_tools_list_*`, etc.) | No more `build_app()` or `_startup` mock; use `mcp.streamable_http_app()` + TestClient |
| `test_protected_resource_metadata` | Endpoint excluded (D-06); test deleted |
| `test_head_returns_protocol_version` | FastMCP serves HEAD differently; may need adjustment |
| `test_get_root_returns_405` | May not apply depending on `streamable_http_path` config |
| `test_delete_session_cleanup` | FastMCP handles sessions internally; DELETE may not be a separate endpoint |
| `test_missing_session_returns_400` | FastMCP session management is internal; behavior may differ |

**Test client pattern for FastMCP:**

```python
from starlette.testclient import TestClient

def test_health():
    with patch("server._startup", return_value=mock_ctx()):
        from server import mcp
        app = mcp.streamable_http_app()
        client = TestClient(app)
        resp = client.get("/health")
    assert resp.status_code == 200
```

Note: `TestClient` works with Starlette apps. [VERIFIED: starlette.testclient imported successfully]

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastMCP + BaseHTTPMiddleware | FastMCP + TokenVerifier (ASGI middleware) | mcp 1.x | Phase 16.2 failure was BaseHTTPMiddleware-specific, not FastMCP-specific |
| Auth0 JWKSVerifier | ScaleKit SDK | Phase 19 | Drop-in: both do JWKS RS256 validation |
| Manual JSON-RPC dispatcher | FastMCP native protocol handling | Phase 19 | Session management, tools/list, tools/call handled by FastMCP |

**Deprecated/outdated:**
- `_FakeMCPCtx`: Bridge class used to emulate FastMCP's ctx in the FastAPI dispatcher. Delete — not needed with native FastMCP.
- `build_app()`: FastAPI app factory. Delete — FastMCP provides `mcp.streamable_http_app()`.
- `mcp_dispatcher`, `_handle_initialize`, `_handle_tools_list`, `_handle_tools_call`: Manual JSON-RPC routing. All deleted — FastMCP handles this internally.
- `_sessions` dict: Manual session tracking. Delete — FastMCP's `StreamableHTTPSessionManager` handles sessions.
- `_mcp_response`, `_error_response`, `_unauthorized_response`: Protocol helpers. Delete — FastMCP handles protocol responses.

---

## Open Questions

1. **Does D-04 (initialize unauthenticated) require per-method HTTP auth that FastMCP doesn't support?**
   - What we know: FastMCP's `RequireAuthMiddleware` wraps the entire `/mcp` endpoint. In remote mode with `token_verifier` set, `initialize` will require a token. The current server.py makes `initialize` unconditionally public.
   - What's unclear: Whether ScaleKit's OAuth flow sends a token with `initialize` (which would make this a non-issue), or whether MCP clients expect `initialize` to succeed without a token.
   - Recommendation: Planner should decide: (a) Accept always-auth for remote mode — simplest, may work with ScaleKit's client since they'd have a token before connecting; or (b) Keep `token_verifier=None` and do per-tool auth check manually inside `search()` and `get_talk()` via `ctx.request_context.request.headers` (more complex, closer to D-04).

2. **HTTP path: `/` or `/mcp`?**
   - What we know: Current server.py uses `POST /`. FastMCP default is `/mcp`. Setting `streamable_http_path="/"` in FastMCP constructor restores the old path.
   - What's unclear: Whether existing MCP clients (Claude Desktop, Claude Code CLI) have `/` or `/mcp` in their config.
   - Recommendation: Use `streamable_http_path="/"` to match current client configurations unless confirmed otherwise.

3. **Does `auth/oauth.py` get deleted or emptied?**
   - What we know: D-05 says replace JWKSVerifier with ScaleKit SDK. The `ScalekitTokenVerifier` can live in `server.py` or in a new `auth/scalekit.py`.
   - Recommendation: Delete `auth/oauth.py` entirely; place `ScalekitTokenVerifier` in `server.py` or a new `auth/scalekit_verifier.py`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| mcp (FastMCP) | New server | ✓ | 1.26.0 | — |
| scalekit-sdk-python | JWT validation | ✓ (installed this session) | 2.7.1 | — |
| starlette | FastMCP internal | ✓ | 1.0.0 | — |
| uvicorn | ASGI server | ✓ | 0.42.0 | — |
| chromadb | Tool calls | ✓ | 1.5.5 | — |

**No missing blocking dependencies.**

Note: `scalekit-sdk-python` was installed during research (`pipenv run pip install scalekit-sdk-python`). It must be added to `Pipfile` and `requirements.txt` regenerated for Docker. [VERIFIED: installation succeeded with no dependency conflicts]

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none — test runner discovers `tests/` |
| Quick run command | `pipenv run py -m pytest tests/test_server.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Behavior | Test Type | Automated Command |
|----------|-----------|-------------------|
| FastMCP server starts with lifespan | smoke | `pipenv run py -m pytest tests/test_server.py::test_lifespan_startup -x` |
| GET /health returns 200 when deps reachable | integration | `pipenv run py -m pytest tests/test_server.py::test_health_returns_200 -x` |
| GET /health returns 503 when Ollama down | integration | `pipenv run py -m pytest tests/test_server.py::test_health_ollama_down -x` |
| Local mode: all requests unauthenticated | unit | `pipenv run py -m pytest tests/test_server.py::test_local_mode_no_auth -x` |
| Remote mode: JWT validated via ScaleKit | unit | `pipenv run py -m pytest tests/test_server.py::test_remote_mode_valid_jwt -x` |
| search tool returns 6-field results | unit | `pipenv run py -m pytest tests/test_server.py::TestSearchTool -x` |
| get_talk returns ordered paragraphs | unit | `pipenv run py -m pytest tests/test_server.py::TestGetTalkTool -x` |

### Wave 0 Gaps

- [ ] `test_fastmcp_removed` must be deleted before implementation (will fail with new server.py)
- [ ] New test: `test_scalekit_token_verifier_valid_token` — unit test for `ScalekitTokenVerifier.verify_token()`
- [ ] New test: `test_scalekit_token_verifier_invalid_token` — verifies returns `None` on bad token
- [ ] Dispatcher tests rewritten for `mcp.streamable_http_app()` pattern

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | ScalekitTokenVerifier + FastMCP TokenVerifier protocol |
| V3 Session Management | yes | FastMCP StreamableHTTPSessionManager (internal) |
| V4 Access Control | yes | Two-mode: local (none) / remote (JWT required) |
| V5 Input Validation | yes | Pydantic (FastMCP tool args validated via type annotations) |
| V6 Cryptography | yes | ScaleKit SDK handles RS256 JWKS verification |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Expired/invalid JWT | Spoofing | ScalekitClient.validate_token raises on invalid; returns None in verifier |
| Token replay | Spoofing | ScaleKit JWT has `exp` claim; AccessToken.expires_at checked by BearerAuthBackend |
| JWKS spoofing | Tampering | SDK fetches from fixed `{SCALEKIT_ENV_URL}/keys`; uses TLS |
| anyio task group crash (Phase 16.2) | DoS | Avoided by not using BaseHTTPMiddleware |
| Prompt injection via tool args | Tampering | Not a server concern; ChromaDB query is read-only |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ScaleKit JWKS endpoint is `{env_url}/keys` (from core.py constant `JWKS_ENDPOINT = "/keys"`) | Standard Stack | JWKS fetch fails; token validation always returns None |
| A2 | ScaleKit JWT payload contains `sub` claim for client_id | Code Examples (ScalekitTokenVerifier) | AccessToken.client_id would be empty string; non-blocking |
| A3 | MCP clients send token with `initialize` in remote mode (making always-auth acceptable) | Open Questions | Client fails at initialize step with 401; requires fallback strategy |

Claims A1 and A2 are [VERIFIED: scalekit source code]. A3 is [ASSUMED] — depends on ScaleKit client behavior not tested in this research session.

---

## Sources

### Primary (HIGH confidence)

- mcp==1.26.0 installed package — FastMCP source inspected via `inspect.getsource()` for all claims
- scalekit-sdk-python==2.7.1 installed package — `ScalekitClient`, `CoreClient`, `TokenValidationOptions` source inspected
- `mcp.server.auth.provider.TokenVerifier` — protocol interface verified
- `mcp.server.auth.middleware.bearer_auth` — `RequireAuthMiddleware`, `BearerAuthBackend` verified as pure ASGI (not BaseHTTPMiddleware)
- `mcp.server.lowlevel.server.RequestContext` — `lifespan_context` field verified
- `mcp.server.fastmcp.utilities.context_injection.find_context_parameter` — type-annotation-based injection verified
- scalekit/core.py `JWKS_ENDPOINT = "/keys"` — JWKS URL pattern verified

### Secondary (MEDIUM confidence)

- [GitHub: scalekit-inc/fastmcp-scalekit-example](https://github.com/scalekit-inc/fastmcp-scalekit-example) — env var names (`SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_CLIENT_ID`, `SCALEKIT_CLIENT_SECRET`, `SCALEKIT_RESOURCE_ID`) confirmed vs. what scalekit-sdk-python expects
- [Scalekit blog: securing-fastmcp-with-scalekit](https://www.scalekit.com/blog/securing-fastmcp-with-scalekit) — referenced `ScalekitProvider` (not in `mcp==1.26.0`; that is a separate `fastmcp` package); env var names consistent

### Tertiary (LOW confidence)

- None — all critical claims verified against installed packages.

---

## Metadata

**Confidence breakdown:**

- Standard Stack: HIGH — verified via pip list, package inspect
- Architecture patterns: HIGH — verified via inspect of FastMCP source (mcp==1.26.0)
- ScaleKit integration: HIGH — verified via inspect of installed scalekit-sdk-python==2.7.1
- Auth design (initialize unauthenticated): LOW-MEDIUM — FastMCP behavior is known; MCP client behavior with always-auth is ASSUMED
- Test migration: HIGH — current tests read in full; FastMCP patterns verified

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable library; FastMCP API unlikely to change in 30 days)

---

## RESEARCH COMPLETE
