# Phase 19: FastMCP + ScaleKit MCP Server — Research

**Researched:** 2026-04-15
**Domain:** standalone `fastmcp` package (PyPI), ScaleKit SDK, MCP server replacement
**Confidence:** HIGH — all claims verified against installed packages via `pipenv run python`

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Full replacement, not an experiment. New `server.py` becomes the canonical server.
- **D-02:** New server file is `server.py` — same location, clean cutover.
- **D-03:** Use FastMCP's built-in auth support. Do NOT use `BaseHTTPMiddleware` — it caused anyio task group failures in Phase 16.2. FastMCP native auth hooks only.
- **D-04:** Two-mode auth: local (SCALEKIT_* vars absent → no auth), remote (SCALEKIT_* vars set → JWT validation required). `initialize` is unauthenticated; `tools/list` and `tools/call` require a valid JWT.
- **D-05:** `auth/oauth.py` (JWKSVerifier) replaced with ScaleKit SDK. Auth0 dependency removed entirely.
- **D-06:** Feature parity EXCEPT `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` endpoints — ScaleKit/the provider handles these; the server does not serve them.
- **D-07:** MCP-Session-ID header behavior and session tracking are retained.

### Claude's Discretion

- Exact ScaleKit SDK usage pattern (which classes/methods)
- Whether `auth/oauth.py` is deleted or replaced in-file
- FastMCP version compatibility with `mcp==1.26.0`
- Env var names for ScaleKit credentials
- Whether existing tests can be adapted or need full rewrite

### Deferred Ideas (OUT OF SCOPE)

- None specified
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRANS-01 | User can connect any MCP client via Streamable HTTP URL | FastMCP `run_http_async(transport="http", host=..., port=...)` — built-in streamable HTTP transport |
| TRANS-02 | Operator can verify server health via GET /health endpoint | `@mcp.custom_route("/health", methods=["GET"])` — native custom route decorator |
| AUTH-02 | Server rejects requests without a valid bearer token with 401 — remote mode; local mode unauthenticated | `RemoteAuthProvider` + custom `TokenVerifier` subclass wrapping ScaleKit SDK; `None` return → 401 via `RequireAuthMiddleware` |
| OAUTH-01 | OAuth 2.1 handshake — client completes token acquisition against authorization server | `RemoteAuthProvider(authorization_servers=[scalekit_env_url])` advertises ScaleKit as AS via RFC 9728 metadata |
| OAUTH-02 | Server validates ScaleKit-issued JWTs | `ScalekitTokenVerifier` subclasses `TokenVerifier`, wraps `ScalekitClient.validate_token()` in `anyio.to_thread.run_sync()` |
| DEPLOY-02 | All secrets configurable via .env — no hardcoded values | `SCALEKIT_ENV_URL`, `SCALEKIT_CLIENT_ID`, `SCALEKIT_CLIENT_SECRET`, `MCP_HOST`, `MCP_PORT` all from env |
</phase_requirements>

---

## Summary

The standalone `fastmcp` package (version 3.2.4 on PyPI, now installed) is a major upgrade over the `mcp.server.fastmcp` submodule. It ships with a complete auth system (`RemoteAuthProvider`, `TokenVerifier`, `AccessToken`) designed exactly for the resource-server-with-external-OAuth pattern this phase requires. The `mcp` package (1.26.0) remains a dependency — `fastmcp` pins `mcp>=1.24.0,<2.0` and does not replace it.

The ScaleKit SDK (`scalekit-sdk-python==2.7.1`, already installed) is fully synchronous. `ScalekitClient.validate_token()` makes network calls (JWKS fetch) on first use, then uses cached keys for subsequent calls. In an async FastMCP context, these sync calls must be wrapped with `anyio.to_thread.run_sync()` to avoid blocking the event loop.

The two-mode auth model from Phase 18 maps cleanly: local mode = no `auth=` argument on `FastMCP()`; remote mode = `auth=RemoteAuthProvider(token_verifier=ScalekitTokenVerifier(...), ...)`. The `custom_route` decorator handles `GET /health`. The `lifespan` parameter accepts an async context manager that yields a dict (or any object accessible via `ctx.lifespan_context`).

**Primary recommendation:** Build a `ScalekitTokenVerifier(TokenVerifier)` subclass in `auth/scalekit_verifier.py` that wraps `ScalekitClient.validate_token()` in a thread, then wire it into `RemoteAuthProvider`. Use `mcp.custom_route("/health", methods=["GET"])` for the health endpoint. Call `mcp.run(transport="http", host=..., port=...)` as the entry point.

---

## Standard Stack

### Core

| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| `fastmcp` | 3.2.4 | MCP server framework — tools, lifespan, auth, HTTP transport | [VERIFIED: pip install] |
| `mcp` | 1.26.0 | Low-level MCP protocol (fastmcp depends on it) | [VERIFIED: pip show] |
| `scalekit-sdk-python` | 2.7.1 | JWT validation via ScaleKit | [VERIFIED: pip show] |
| `uvicorn` | 0.42.0 | ASGI server (fastmcp calls uvicorn internally) | [VERIFIED: Pipfile.lock] |
| `starlette` | (via mcp) | HTTP framework underlying fastmcp | [VERIFIED: pip show mcp dependencies] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `anyio` | (via mcp) | Thread bridging for sync ScaleKit calls | `anyio.to_thread.run_sync(...)` inside async `verify_token` |
| `starlette.middleware.Middleware` | (via starlette) | CORS middleware wrapper | Pass as `Middleware(CORSMiddleware, ...)` to `mcp.run_http_async(middleware=[...])` |
| `starlette.testclient.TestClient` | (via starlette) | Test HTTP endpoints | Use with `mcp.http_app()` for unit tests |

### Installation

```bash
# Add to Pipfile
pipenv install fastmcp
# scalekit-sdk-python already in Pipfile; mcp already present
```

Add `fastmcp = "*"` to `[packages]` in Pipfile. `fastmcp` pins `mcp<2.0,>=1.24.0` so both coexist; `mcp` package is NOT removed.

**fastmcp vs mcp.server.fastmcp:**

| | Old (mcp submodule) | New (standalone fastmcp) |
|--|--|--|
| Import | `from mcp.server.fastmcp import FastMCP` | `from fastmcp import FastMCP` |
| Auth | None built-in | `AuthProvider`, `TokenVerifier`, `RemoteAuthProvider` |
| Custom routes | Not supported | `@mcp.custom_route("/path", methods=["GET"])` |
| Middleware | BaseHTTPMiddleware (broken) | Starlette `Middleware(...)` passed to `run_http_async` |
| Lifespan context access | `ctx.request_context.lifespan_context` | `ctx.lifespan_context` (direct property, no `.request_context` step needed in tools) |

---

## Architecture Patterns

### Project Structure (changes only)

```
server.py                  # Rewritten: FastMCP-based, replaces FastAPI dispatcher
auth/
  oauth.py                 # DELETED or emptied — JWKSVerifier no longer used
  scalekit_verifier.py     # NEW: ScalekitTokenVerifier(TokenVerifier) subclass
Pipfile                    # Add fastmcp = "*"
tests/
  test_server.py           # REWRITTEN: new patterns for fastmcp-based server
```

### Pattern 1: FastMCP Server Setup (Two-Mode Auth)

```python
# server.py skeleton
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
import anyio
from fastmcp import FastMCP, Context
from fastmcp.server.auth import RemoteAuthProvider
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from auth.scalekit_verifier import ScalekitTokenVerifier

SCALEKIT_ENV_URL    = os.environ.get("SCALEKIT_ENV_URL", "")
SCALEKIT_CLIENT_ID  = os.environ.get("SCALEKIT_CLIENT_ID", "")
SCALEKIT_CLIENT_SECRET = os.environ.get("SCALEKIT_CLIENT_SECRET", "")
MCP_BASE_URL        = os.environ.get("MCP_BASE_URL", "")
MCP_HOST            = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT            = int(os.environ.get("MCP_PORT", "7363"))

# Build auth provider only when ScaleKit env vars are all set
_auth: RemoteAuthProvider | None = None
if SCALEKIT_ENV_URL and SCALEKIT_CLIENT_ID and SCALEKIT_CLIENT_SECRET and MCP_BASE_URL:
    _verifier = ScalekitTokenVerifier(
        env_url=SCALEKIT_ENV_URL,
        client_id=SCALEKIT_CLIENT_ID,
        client_secret=SCALEKIT_CLIENT_SECRET,
    )
    _auth = RemoteAuthProvider(
        token_verifier=_verifier,
        authorization_servers=[SCALEKIT_ENV_URL],
        base_url=MCP_BASE_URL,
    )

@dataclass
class AppContext:
    client: ...
    collections: dict

@asynccontextmanager
async def lifespan(server: FastMCP):
    ctx = _startup()          # same startup logic as current server.py
    yield {"app": ctx}        # yield a dict; tools access via ctx.lifespan_context["app"]

mcp = FastMCP(
    "lds-scripture-index",
    instructions=MCP_INSTRUCTIONS,
    auth=_auth,               # None in local mode, RemoteAuthProvider in remote mode
    lifespan=lifespan,
)

@mcp.tool()
async def search(query: str, ..., ctx: Context) -> str:
    app: AppContext = ctx.lifespan_context["app"]
    ...

@mcp.tool()
async def get_talk(talk_id: str, ctx: Context) -> str:
    app: AppContext = ctx.lifespan_context["app"]
    ...

@mcp.custom_route("/health", methods=["GET"])
async def health_endpoint(request: Request) -> JSONResponse:
    ...

if __name__ == "__main__":
    cors = Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    mcp.run(
        transport="http",
        host=MCP_HOST,
        port=MCP_PORT,
        middleware=[cors],
    )
```

**Critical difference from old code:** In the old server, tool functions accessed `ctx.request_context.lifespan_context` (the `_FakeMCPCtx` bridge pattern). In native FastMCP, tools access `ctx.lifespan_context` directly — no bridge needed. The lifespan function yields a dict and the dict is available as `ctx.lifespan_context`.

### Pattern 2: ScalekitTokenVerifier Implementation

```python
# auth/scalekit_verifier.py
import anyio
from scalekit import ScalekitClient
from scalekit.common.scalekit import TokenValidationOptions
from fastmcp.server.auth import TokenVerifier, AccessToken

class ScalekitTokenVerifier(TokenVerifier):
    """Wraps ScalekitClient.validate_token() for use as a FastMCP TokenVerifier.
    
    ScaleKit SDK is fully synchronous. validate_token() is called in a thread
    via anyio.to_thread.run_sync() to avoid blocking the event loop.
    
    ScalekitClient is constructed at import time (module level) so the 
    __authenticate_client() network call happens before the event loop starts.
    """

    def __init__(self, env_url: str, client_id: str, client_secret: str):
        super().__init__()
        # ScalekitClient calls __authenticate_client() synchronously during init.
        # Construct at startup (before event loop) to avoid blocking async context.
        self._client = ScalekitClient(
            env_url=env_url,
            client_id=client_id,
            client_secret=client_secret,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a ScaleKit JWT. Returns AccessToken or None on failure."""
        try:
            payload = await anyio.to_thread.run_sync(
                lambda: self._client.validate_token(token)
            )
        except Exception:
            return None
        
        # Build FastMCP AccessToken from JWT payload
        # ScaleKit JWTs: 'sub' = subject, 'exp' = expiry, 'azp'/'client_id' = client
        scopes_raw = payload.get("scope", "")
        scopes = scopes_raw.split() if isinstance(scopes_raw, str) else []
        
        return AccessToken(
            token=token,
            client_id=payload.get("client_id") or payload.get("azp") or payload.get("sub", ""),
            scopes=scopes,
            expires_at=payload.get("exp"),
            claims=payload,
        )
```

**Why `anyio.to_thread.run_sync()`:** ScaleKit's `validate_token()` calls `get_jwks()` (sync `requests.get`) on first invocation. After JWKS is cached in `self._client.core_client.keys`, subsequent calls are CPU-only. Either way, the method is synchronous and must not run in the event loop thread.

**Why construct `ScalekitClient` at module level:** Its `__init__` calls `__authenticate_client()` which does a sync HTTP POST to ScaleKit's `/oauth/token` endpoint. This cannot happen inside an `async def` without a thread wrapper. Constructing at startup (before `mcp.run()`) is the clean solution.

### Pattern 3: Custom Route for Health Endpoint

```python
# Source: fastmcp.FastMCP.custom_route verified via inspect
@mcp.custom_route("/health", methods=["GET"])
async def health_endpoint(request: Request) -> JSONResponse:
    """Live health check — Ollama + ChromaDB reachability."""
    status = {"ollama": "reachable", "chromadb": "reachable"}
    http_status = 200
    # ... same health logic as current server.py health_check() ...
    return JSONResponse({"status": "ok" if http_status == 200 else "degraded", **status},
                        status_code=http_status)
```

Custom routes are registered via `mcp._additional_http_routes` (a `list[Route]`). They are appended AFTER the MCP protocol route in `create_streamable_http_app`. They do NOT go through the MCP auth middleware — health endpoint is always unauthenticated, which is correct (same as current implementation).

### Pattern 4: CORS Middleware

```python
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

cors = Middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "HEAD", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "MCP-Protocol-Version", "MCP-Session-Id"],
    expose_headers=["MCP-Protocol-Version", "MCP-Session-Id", "WWW-Authenticate"],
)

mcp.run(transport="http", host=MCP_HOST, port=MCP_PORT, middleware=[cors])
```

The `middleware` parameter to `run_http_async` (called by `mcp.run`) accepts `list[starlette.middleware.Middleware]`. These are Starlette `Middleware` wrappers (NOT `fastmcp.server.middleware.Middleware` — same import name but different class). Confirmed via `create_base_app` which uses `Middleware(RequestContextMiddleware)` from `starlette.middleware`.

### Pattern 5: Lifespan Context Access in Tools

Old pattern (broken with native FastMCP):
```python
# OLD — requires _FakeMCPCtx bridge
app: AppContext = ctx.request_context.lifespan_context
```

New pattern (native FastMCP):
```python
# NEW — ctx.lifespan_context returns whatever the lifespan yields
app: AppContext = ctx.lifespan_context["app"]
```

The lifespan function should yield a dict. The dict is stored as `_lifespan_result` on the `FastMCP` instance. `ctx.lifespan_context` returns this dict directly (or falls back to `{}` if no lifespan).

### Anti-Patterns to Avoid

- **BaseHTTPMiddleware:** D-03 — banned. FastMCP's `auth=` parameter handles auth at the protocol layer, not ASGI middleware layer.
- **`from mcp.server.fastmcp import FastMCP`:** Always use `from fastmcp import FastMCP` (standalone package).
- **Constructing `ScalekitClient` inside `verify_token`:** This would make a network call on every auth check. Construct once at startup.
- **`ctx.request_context.lifespan_context`:** Old bridge pattern. With native FastMCP, use `ctx.lifespan_context` directly.
- **Blocking sync calls in async context:** `ScalekitClient.validate_token()` uses `requests` (sync). Always wrap with `anyio.to_thread.run_sync()`.
- **Yielding a non-dict from lifespan:** `Context.lifespan_context` type hint is `dict[str, Any]`. Yield a dict from the lifespan function to avoid type confusion.
- **`.well-known` routes:** D-06 prohibits serving these. `RemoteAuthProvider` serves the RFC 9728 protected resource metadata automatically via its `get_routes()`. No manual `.well-known` route needed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol dispatch | Manual JSON-RPC router (current server.py) | `from fastmcp import FastMCP` + `@mcp.tool()` | FastMCP handles initialize, tools/list, tools/call, session management automatically |
| Auth middleware / 401 responses | Custom bearer token extraction | `RemoteAuthProvider` + `TokenVerifier` | `RequireAuthMiddleware` handles 401, WWW-Authenticate header, and RFC 9728 metadata |
| JWT validation | PyJWKClient + jwt.decode | `ScalekitClient.validate_token()` | ScaleKit handles JWKS caching and RS256 decode |
| RFC 9728 metadata endpoint | Manual `/.well-known/oauth-protected-resource` route | `RemoteAuthProvider.get_routes()` | Built-in; registered automatically when `auth=` is set |
| Custom HTTP routes | Full FastAPI app | `@mcp.custom_route("/health", methods=["GET"])` | One-line decorator; registers into the Starlette app |
| CORS | Custom middleware class | `Middleware(CORSMiddleware, ...)` from starlette | Pass to `mcp.run(middleware=[...])` |

---

## ScaleKit SDK Reference

### Constructor

```python
from scalekit import ScalekitClient

client = ScalekitClient(
    env_url="https://<tenant>.scalekit.app",   # SCALEKIT_ENV_URL
    client_id="<client_id>",                    # SCALEKIT_CLIENT_ID  
    client_secret="<client_secret>",            # SCALEKIT_CLIENT_SECRET
)
```

`__init__` immediately calls `__authenticate_client()` (sync HTTP POST to `/oauth/token`) and `__grpc_secure_channel()`. Must be called at module level or in a thread.

### Token Validation

```python
from scalekit.common.scalekit import TokenValidationOptions

# Simple validation (audience NOT verified by default)
payload = client.validate_token(token)  # returns dict with JWT claims

# With audience validation
payload = client.validate_token(
    token,
    options=TokenValidationOptions(
        issuer="https://<tenant>.scalekit.app",
        audience=["https://your-mcp-server.com/mcp"],
    )
)
```

`validate_token()` returns `dict[str, Any]` on success, raises `ScalekitValidateTokenFailureException` or `Exception` on failure. Caller wraps in `try/except` and returns `None` to FastMCP on failure.

### JWKS Endpoint

ScaleKit JWKS: `{env_url}/keys` (constant `JWKS_ENDPOINT = "/keys"` in `scalekit.core`). Keys are cached in `client.core_client.keys` after first fetch. Subsequent `validate_token()` calls skip the network call if keys are already loaded.

### Environment Variable Names (recommended)

| Env Var | Description |
|---------|-------------|
| `SCALEKIT_ENV_URL` | ScaleKit tenant URL, e.g. `https://tenant.scalekit.app` |
| `SCALEKIT_CLIENT_ID` | OAuth client ID from ScaleKit dashboard |
| `SCALEKIT_CLIENT_SECRET` | OAuth client secret from ScaleKit dashboard |
| `MCP_BASE_URL` | Public URL of this MCP server, e.g. `https://mcp.yourdomain.com` |
| `MCP_HOST` | Bind host (default: `0.0.0.0`) |
| `MCP_PORT` | Bind port (default: `7363`) |

---

## FastMCP API Reference

### FastMCP Constructor

```python
FastMCP(
    name="lds-scripture-index",       # Server name
    instructions="...",               # Tool-level instructions
    auth=_auth,                       # AuthProvider | None
    lifespan=lifespan_fn,             # async context manager callable
)
```

### Tool Decorator

```python
@mcp.tool()
async def my_tool(param: str, ctx: Context) -> str:
    ...
```

`ctx: Context` is injected by FastMCP when the parameter name is `ctx` and type is `Context`. No change from the `mcp` package pattern for tool signatures, except `ctx.lifespan_context` replaces `ctx.request_context.lifespan_context`.

### Run / HTTP App

```python
# Simple entry point:
mcp.run(transport="http", host=MCP_HOST, port=MCP_PORT, middleware=[cors])

# For TestClient in tests:
app = mcp.http_app()                          # Returns StarletteWithLifespan
client = TestClient(app, raise_server_exceptions=False)
```

`http_app()` returns a `StarletteWithLifespan` (Starlette subclass). `TestClient` from `starlette.testclient` works directly.

### Default Path

FastMCP serves MCP at `/mcp` by default (`fastmcp.settings.streamable_http_path = "/mcp"`). The current `server.py` serves at `/` and `/mcp`. With FastMCP, `/mcp` is the canonical path. The `path=` argument to `http_app()` or `run()` can override this.

### RemoteAuthProvider

```python
from fastmcp.server.auth import RemoteAuthProvider, TokenVerifier, AccessToken

auth = RemoteAuthProvider(
    token_verifier=verifier,              # TokenVerifier subclass
    authorization_servers=["https://..."], # ScaleKit env URL
    base_url="https://mcp.domain.com",    # This server's public URL
)
```

`RemoteAuthProvider` automatically serves the RFC 9728 protected resource metadata at `/.well-known/oauth-protected-resource` via its `get_routes()` method — no manual route needed.

---

## Common Pitfalls

### Pitfall 1: ScalekitClient Blocking the Event Loop

**What goes wrong:** `ScalekitClient.__init__()` calls `requests.get()` and `requests.post()` synchronously. If constructed inside an `async def` or in a FastMCP lifespan, it blocks uvicorn's event loop thread.

**How to avoid:** Construct `ScalekitClient` at module level (before `mcp.run()` is called). The blocking network calls complete before the event loop starts.

**Warning signs:** Server hangs at startup; uvicorn health probe never responds.

### Pitfall 2: Wrong lifespan_context Access Pattern

**What goes wrong:** Code copied from the current server.py uses `ctx.request_context.lifespan_context` (the `_FakeMCPCtx` bridge pattern). In native FastMCP, `ctx.request_context` is a `RequestContext` object (not fake), and the lifespan result is at `ctx.lifespan_context` directly.

**How to avoid:** Use `ctx.lifespan_context["app"]` where the lifespan yields `{"app": app_context}`.

**Warning signs:** `AttributeError: 'RequestContext' object has no attribute 'lifespan_context'` (if structure differs) or `KeyError` on dict access.

### Pitfall 3: auth= None vs Missing

**What goes wrong:** Setting `auth=None` explicitly vs not setting `auth=` at all both disable auth. But the two-mode logic requires `_auth` to be `None` when SCALEKIT_* vars are absent. The `if SCALEKIT_ENV_URL and ...` guard at module level handles this correctly.

**How to avoid:** Build `_auth` conditionally. Pass `auth=_auth` always — FastMCP treats `None` as no auth.

**Warning signs:** Remote mode has no auth (forgot the `if` guard), or local mode fails with auth errors (env vars partially set).

### Pitfall 4: ScaleKit validate_token Audience Verification

**What goes wrong:** `ScalekitClient.validate_token(token)` with no options does NOT verify the audience claim by default (`verify_aud=False` in the source). Tokens from any ScaleKit tenant could pass.

**How to avoid:** Pass `TokenValidationOptions(issuer=SCALEKIT_ENV_URL, audience=[MCP_BASE_URL])` to `validate_token()`. This enables both issuer and audience verification.

**Warning signs:** Tokens from other ScaleKit tenants accepted by the verifier.

### Pitfall 5: FastMCP Default MCP Path is /mcp

**What goes wrong:** The old server dispatches MCP at `/` and `/mcp`. FastMCP defaults to `/mcp` only. Clients configured for `/` will fail.

**How to avoid:** Either accept `/mcp` as the new canonical path (update client configs and docs), or set `path="/"` in `mcp.run(path="/", ...)`. The `/mcp` default is correct per FastMCP convention.

**Warning signs:** MCP clients connect but get 404 on POST requests.

### Pitfall 6: ScalekitClient Not Handling Unknown kid

**What goes wrong:** If ScaleKit rotates keys, `get_jwks()` early-returns when `self.keys` is non-empty. A token with a new `kid` will cause `KeyError: kid_value` in `validate_token()`.

**How to avoid:** Catch `KeyError` (and all exceptions) in `ScalekitTokenVerifier.verify_token()`, return `None`. The planner may add a key-refresh path (call `client.core_client.keys = {}` then re-fetch) but the safe minimum is graceful failure → 401.

### Pitfall 7: CORS Middleware Ordering

**What goes wrong:** CORS middleware must wrap the MCP endpoint. FastMCP's `create_base_app` inserts `RequestContextMiddleware` at index 0 (outermost). User-supplied middleware is appended after the auth middleware. Starlette processes middleware in reverse order (outermost first), so CORS should be passed via the `middleware=` argument to `mcp.run()`, not inserted manually.

**How to avoid:** Pass `Middleware(CORSMiddleware, ...)` in the `middleware` list to `mcp.run()`. FastMCP handles ordering internally.

---

## Test Rewrite Analysis

### Tests That Carry Over (pure unit tests, no server dependency)

These tests import standalone helper functions and do not depend on the server framework:

| Test Class / Function | Carries Over | Note |
|-----------------------|-------------|------|
| `TestBuildWhereFilter` | YES | `_build_where_filter` is copied to new server.py unchanged |
| `TestMatchesSpeaker` | YES | `_matches_speaker` is copied unchanged |
| `TestFormatSearchResult` | YES | `_format_search_result` is copied unchanged |
| `TestParseTalkId` | YES | `_parse_talk_id` is copied unchanged |
| `test_chromadb_client_default_host` | YES | Tests `config/chromadb_client.py` (unchanged) |
| `test_chromadb_client_env_override` | YES | Tests `config/chromadb_client.py` (unchanged) |
| `test_ollama_url_env_override` | YES | Tests `config/ollama.py` (unchanged) |
| `test_get_embedding_function_*` | YES | Tests `config/ollama.py` (unchanged) |
| `test_search_docstring_*` | YES | Tool docstrings still needed |
| `test_get_talk_docstring_*` | YES | Tool docstrings still needed |

### Tests That Need Rewriting

| Test | Why It Changes |
|------|---------------|
| `TestSearchTool` | `ctx` is no longer a `_FakeMCPCtx` — use real `ctx.lifespan_context` dict pattern |
| `TestGetTalkTool` | Same: new ctx pattern |
| `test_chromadb_missing_collection_exits` | `_load_collections` import path same, test same |
| `test_ollama_failure_is_non_fatal` | `_check_ollama` import path same, test same |
| `test_all_collections_warmed` | Same |
| `test_check_ollama_passes_resolved_url` | Same |
| Dispatcher tests (`test_initialize_no_auth`, etc.) | Full rewrite: use `TestClient(mcp.http_app())` + FastMCP protocol; no manual JSON-RPC dispatch |
| `test_health_returns_200` | Use `TestClient(mcp.http_app()); client.get("/health")` |
| `test_fastmcp_removed` | Rewrite: assert `from mcp.server.fastmcp import FastMCP` NOT present; assert `from fastmcp import FastMCP` IS present |
| `test_protected_resource_metadata` | FastMCP serves this at `/.well-known/oauth-protected-resource` automatically when `auth=RemoteAuthProvider(...)` |
| Auth tests (`test_tools_list_requires_auth`, etc.) | Rewrite: patch `ScalekitTokenVerifier.verify_token`, not `_jwt_verifier` |

### New Tests Needed

| Test | What It Verifies |
|------|-----------------|
| `test_scalekit_verifier_valid_token` | `ScalekitTokenVerifier.verify_token()` returns `AccessToken` for valid token |
| `test_scalekit_verifier_invalid_token` | Returns `None` for tokens that raise exception |
| `test_scalekit_verifier_unknown_kid` | Returns `None` gracefully on `KeyError` |
| `test_mcp_tools_list_local_mode` | No auth when SCALEKIT_* vars absent |
| `test_mcp_tools_list_remote_requires_token` | 401 without token in remote mode |
| `test_mcp_tools_list_valid_token` | 200 with mocked valid token |
| `test_health_custom_route` | `GET /health` is unauthenticated and returns correct JSON |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already installed in dev-packages) |
| Config file | None (pytest discovers by convention) |
| Quick run command | `pipenv run py -m pytest tests/test_server.py -x` |
| Full suite command | `pipenv run py -m pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Status |
|--------|----------|-----------|-------------------|-------------|
| TRANS-01 | MCP client connects via Streamable HTTP | integration | `pytest tests/test_server.py::test_initialize_no_auth -x` | Rewrite |
| TRANS-02 | GET /health returns 200/503 | unit | `pytest tests/test_server.py::test_health_returns_200 -x` | Rewrite |
| AUTH-02 | 401 without token (remote), pass-through (local) | unit | `pytest tests/test_server.py::test_tools_list_requires_auth -x` | Rewrite |
| OAUTH-01 | OAuth discovery metadata served | unit | `pytest tests/test_server.py::test_protected_resource_metadata -x` | Rewrite |
| OAUTH-02 | ScaleKit JWT validated | unit | `pytest tests/test_server.py::test_scalekit_verifier_valid_token -x` | New |
| DEPLOY-02 | No hardcoded values, all from env | code review | `grep -n "auth0\|scalekit\." server.py` should show only env reads | Manual |

### Sampling Rate

- **Per task commit:** `pipenv run py -m pytest tests/test_server.py -x -q`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `auth/scalekit_verifier.py` — new file, no tests yet; create before implementing
- [ ] `tests/test_server.py` — full rewrite needed; existing tests run against old API
- [ ] Pipfile must add `fastmcp = "*"` before Wave 1 implementation begins

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `fastmcp` | All server functionality | NOW (just installed) | 3.2.4 | — |
| `mcp` | fastmcp dep | YES | 1.26.0 | — |
| `scalekit-sdk-python` | JWT validation | YES | 2.7.1 | — |
| `uvicorn` | HTTP server | YES | 0.42.0 | — |
| `starlette` | HTTP framework | YES | (via mcp) | — |
| ScaleKit tenant (network) | Remote mode auth | UNKNOWN | — | Local mode (no SCALEKIT_* vars) |

**Missing dependencies with no fallback:** None — all Python packages are available.

**Note:** ScaleKit tenant connectivity cannot be verified in this environment. The two-mode auth design (D-04) means the server works without ScaleKit connectivity in local mode. Remote mode testing requires either a real ScaleKit tenant or mocking `ScalekitClient.validate_token()`.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| `from mcp.server.fastmcp import FastMCP` | `from fastmcp import FastMCP` (standalone pkg) | New API: auth=, custom_route, different lifespan context access |
| Manual FastAPI JSON-RPC dispatcher | `@mcp.tool()` decorator + native dispatch | No manual session management, no manual method routing |
| `BaseHTTPMiddleware` for auth (Phase 16.1) | `RemoteAuthProvider` in FastMCP | No anyio task group errors |
| `_FakeMCPCtx` bridge | `ctx.lifespan_context["key"]` directly | Cleaner, no fake objects needed |
| Manual `/.well-known/oauth-protected-resource` | `RemoteAuthProvider.get_routes()` auto-serves it | No manual implementation |
| Auth0 JWKS verifier (`auth/oauth.py`) | `ScalekitTokenVerifier(TokenVerifier)` | ScaleKit replaces Auth0 as OAuth provider |

**Deprecated/outdated in new server:**
- `_FakeMCPCtx`: remove entirely
- `build_app()`: no longer needed; `mcp.http_app()` replaces it
- `_handle_initialize()`, `_handle_tools_list()`, `_handle_tools_call()`: replaced by FastMCP dispatch
- `_sessions` dict: FastMCP handles session management internally
- `_mcp_response()`, `_error_response()`, `_unauthorized_response()`: FastMCP protocol layer handles these
- `auth/oauth.py` (JWKSVerifier): replaced by `auth/scalekit_verifier.py`

---

## Open Questions

1. **ScaleKit audience claim format**
   - What we know: ScaleKit JWT payload structure follows standard JWT. `validate_token()` accepts `TokenValidationOptions(audience=[...])`.
   - What's unclear: What does ScaleKit put in the `aud` claim — the MCP base URL, something else? This determines what to pass as `audience=` in `TokenValidationOptions`.
   - Recommendation: In `ScalekitTokenVerifier`, make audience validation optional/configurable. Start without strict audience validation (matches ScaleKit SDK default behavior `verify_aud=False`). Add `SCALEKIT_AUDIENCE` env var when issuer/audience verification is needed.

2. **`/mcp` vs `/` MCP path**
   - What we know: FastMCP defaults to `/mcp`. Current server handles `/` and `/mcp`.
   - What's unclear: Whether MCP clients configured for `/` will need reconfiguration.
   - Recommendation: Use the FastMCP default `/mcp`. Update any client configuration instructions. The `path="/"` override is available if needed.

3. **Session ID header behavior**
   - What we know: D-07 requires MCP-Session-ID behavior to be retained. FastMCP handles session management internally.
   - What's unclear: Whether FastMCP's native session management sends `MCP-Session-Id` headers in the same format as the current manual implementation.
   - Recommendation: Test with `TestClient` and verify `MCP-Session-Id` appears in `initialize` response headers.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ScaleKit JWT `aud` claim matches `MCP_BASE_URL` format | ScaleKit SDK Reference | Audience validation fails if format differs; mitigation: skip audience validation initially |
| A2 | FastMCP's `RequireAuthMiddleware` returns 401 (not 403) for missing token | Anti-Patterns | Tests expecting 401 would need updating to 403 |
| A3 | CORS headers work via `Middleware(CORSMiddleware, ...)` without modification | Pattern 4 | Preflight requests might fail if middleware ordering causes issues |

**All other claims in this document are VERIFIED** by direct Python inspection of installed packages.

---

## Sources

### Primary (HIGH confidence — VERIFIED via installed packages)

- `fastmcp==3.2.4` — inspected via `import fastmcp; inspect.getsource(...)` — FastMCP constructor, `custom_route`, `http_app`, `run_http_async`, `RemoteAuthProvider`, `TokenVerifier`, `AccessToken`, `_lifespan_proxy`, lifespan context chain
- `scalekit-sdk-python==2.7.1` — inspected via `import scalekit; inspect.getsource(...)` — `ScalekitClient.__init__`, `validate_token`, `CoreClient.get_jwks`, `TokenValidationOptions`, exception types
- `mcp==1.26.0` — inspected `mcp.server.auth.provider.AccessToken` fields
- `starlette` — confirmed `Middleware(CORSMiddleware, ...)` pattern via `create_base_app` source

### Secondary (MEDIUM confidence)

- ScaleKit env var naming conventions: inferred from `ScalekitClient.__init__(env_url, client_id, client_secret)` parameter names + industry convention

### Tertiary (LOW confidence — marked `[ASSUMED]` in Assumptions Log)

- ScaleKit JWT `aud` claim format at runtime — A1 above

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages installed and inspected directly
- Architecture: HIGH — API signatures verified via `inspect.signature()` and `inspect.getsource()`
- ScaleKit JWT claim format: MEDIUM — SDK source read but live token not available
- Pitfalls: HIGH — root causes verified in source code

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable library; fastmcp 3.x API unlikely to break)
