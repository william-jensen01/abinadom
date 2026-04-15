# Phase 19: FastMCP + ScaleKit MCP Server — Research

**Researched:** 2026-04-15 (rewritten — supersedes prior research; CONTEXT.md updated to built-in ScalekitProvider)
**Domain:** FastMCP 3.2.4 built-in `ScalekitProvider`, lifespan context, custom routes, `DebugTokenVerifier`, test patterns
**Confidence:** HIGH — all claims verified by inspecting installed package source at runtime

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Full replacement, not an experiment. New FastMCP + ScaleKit server replaces `server.py` in place. Existing file overwritten.
- **D-02:** New server file is `server.py` — same location, clean cutover.
- **D-03:** Use `fastmcp.server.auth.providers.scalekit.ScalekitProvider`. Do NOT use `BaseHTTPMiddleware`. Do NOT use `scalekit-sdk-python` SDK — `ScalekitProvider` performs JWKS/JWT verification internally without it.
- **D-04:** Two-mode auth: local mode (`SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID`, or `MCP_BASE_URL` absent) → `auth=None`; remote mode (all three set) → `auth=ScalekitProvider(...)`. `initialize` is unauthenticated; `tools/list` and `tools/call` require a valid JWT.
- **D-05:** `auth/oauth.py` (JWKSVerifier) is deleted. No `auth/scalekit_verifier.py` is created.
- **D-06:** `ScalekitProvider` automatically serves `/.well-known/oauth-protected-resource` (via `RemoteAuthProvider` base class) and `/.well-known/oauth-authorization-server` (via `ScalekitProvider.get_routes()`). No manual route registration needed.
- **D-07:** MCP-Session-ID header behavior and session tracking retained (handled natively by FastMCP).
- **D-08:** No `required_scopes` enforcement — any valid ScaleKit JWT accepted.
- **D-09:** `scalekit-sdk-python` and `fastapi` removed from Pipfile.
- **D-10:** Use `DebugTokenVerifier` from `fastmcp.server.auth.providers.debug` for auth-related unit tests (NOTE: CONTEXT.md D-10 says "DebugAuthProvider" — this class does NOT exist; correct name verified as `DebugTokenVerifier`).
- **D-11:** Full feature parity: `search` and `get_talk` tools, `GET /health`, startup validation (ChromaDB + Ollama + 4-collection warmup), session management, lifespan.
- **D-12:** ScaleKit Dashboard operator setup required: create MCP Server resource, note Resource ID, set env vars.

### Claude's Discretion

- Whether `auth/oauth.py` is deleted or emptied in-file (deletion preferred)
- Exact lifespan context access pattern (`ctx.lifespan_context["app"]`)
- CORS middleware configuration
- How existing tool function signatures map to native `@mcp.tool()` decorators

### Deferred Ideas (OUT OF SCOPE)

- Required scopes enforcement (D-08)
- Per-user rate limiting (AUTH-05)
- Usage admin endpoint (AUTH-06)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRANS-01 | User can connect any MCP client via Streamable HTTP URL | FastMCP `http_app(transport="http")` / `run_http_async()` serves streamable HTTP on `/mcp` by default |
| TRANS-02 | Operator can verify server health via GET /health | `@mcp.custom_route("/health", methods=["GET"])` — API verified at runtime |
| AUTH-02 | Server rejects requests without valid bearer token with 401 (remote mode); local mode unauthenticated | `ScalekitProvider` + FastMCP's `RequireAuthMiddleware` returns 401; `auth=None` passes all requests |
| OAUTH-01 | OAuth 2.1 handshake against MCP server via ScaleKit | `ScalekitProvider` built-in to FastMCP 3.2.4; advertises ScaleKit as AS via OAuth discovery endpoints |
| OAUTH-02 | Server validates ScaleKit-issued JWTs | `ScalekitProvider` creates internal `JWTVerifier(jwks_uri="{env_url}/keys", issuer="{env_url}", algorithm="RS256", audience=resource_id)` |
| DEPLOY-02 | All secrets configurable via .env — no hardcoded values | `SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID`, `MCP_BASE_URL`, `FASTMCP_HOST`, `FASTMCP_PORT` all env-var driven |
</phase_requirements>

---

## Summary

Phase 19 replaces the existing FastAPI + manual JSON-RPC dispatcher (`server.py`) with a native FastMCP 3.2.4 server. FastMCP is already installed in the virtualenv at version 3.2.4. The `ScalekitProvider` is a built-in class in `fastmcp.server.auth.providers.scalekit` — it handles JWKS discovery, RS256 JWT validation via an internal `JWTVerifier`, and serves both OAuth discovery endpoints automatically through `get_routes()`. No custom verifier class is needed; the `scalekit-sdk-python` SDK is explicitly excluded (D-03).

The lifespan context pattern changes from FastAPI's `app.state.ctx` to FastMCP's `ctx.lifespan_context` dict. Tool functions decorated with `@mcp.tool()` receive a `Context` parameter (type-annotated) and access lifespan state via `ctx.lifespan_context["key"]`. The old `_FakeMCPCtx` bridge class, the `_sessions` dict, and the entire JSON-RPC dispatcher (~500 lines) are eliminated — FastMCP's built-in protocol handling replaces them.

**Critical naming correction:** CONTEXT.md D-10 references `DebugAuthProvider` — this class does **not** exist in fastmcp 3.2.4. The correct class is `DebugTokenVerifier` from `fastmcp.server.auth.providers.debug`. Verified by runtime import: `from fastmcp.server.auth.providers.debug import DebugAuthProvider` raises `ImportError`.

**Primary recommendation:** Rewrite `server.py` as a clean FastMCP server. Preserve all pure helper functions (`_build_where_filter`, `_matches_speaker`, `_format_search_result`, `_parse_talk_id`, `AppContext` dataclass, `_startup()`, `_check_ollama()`, `_load_collections()`, `_resolve_chromadb_client()`) unchanged — they have no framework dependencies. Rewrite only the framework-layer code (lifespan, tool registration, route registration, entry point). Delete `auth/oauth.py`. Remove `fastapi` and `scalekit-sdk-python` from Pipfile.

---

## Standard Stack

### Core

| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| `fastmcp` | 3.2.4 | MCP server framework with built-in auth, tools, lifespan, HTTP transport | [VERIFIED: `pipenv run py -c "import fastmcp; print(fastmcp.__version__)"` → 3.2.4] |
| `fastmcp.server.auth.providers.scalekit.ScalekitProvider` | (built-in to 3.2.4) | ScaleKit JWT validation + OAuth discovery endpoint serving | [VERIFIED: source inspected via `inspect.getsource`] |
| `fastmcp.server.auth.providers.debug.DebugTokenVerifier` | (built-in to 3.2.4) | Test token verifier (accepts all non-empty tokens by default) | [VERIFIED: source inspected; `DebugAuthProvider` confirmed absent] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `starlette.testclient.TestClient` | (starlette dep via fastmcp) | Sync HTTP test client | Unit tests — `TestClient(mcp.http_app())` works [VERIFIED: runtime test] |
| `fastmcp.utilities.tests.run_server_async` | (built-in) | In-process async server | Integration tests needing real HTTP + full OAuth flow |

### Removed Dependencies (per D-09)

| Package | Why Removed |
|---------|------------|
| `scalekit-sdk-python` (2.7.1 currently installed) | `ScalekitProvider` performs JWT verification internally; SDK not needed |
| `fastapi` (currently in Pipfile) | New `server.py` uses no FastAPI — Starlette only via FastMCP |

**Installation:**
```bash
# fastmcp already installed at 3.2.4 — no install needed
# Remove from Pipfile:
pipenv uninstall fastapi scalekit-sdk-python
# Remove entries from Pipfile [packages] section
```

[VERIFIED: `pipenv run pip show fastmcp scalekit-sdk-python` — both present; fastmcp 3.2.4, scalekit-sdk-python 2.7.1]

---

## Architecture Patterns

### Project Structure (changes only)

```
server.py                  # REWRITE: FastMCP-based, replaces FastAPI dispatcher
auth/
  __init__.py              # KEEP unchanged
  middleware.py            # KEEP unchanged (Phase 14 bearer token middleware, harmless)
  store.py                 # KEEP unchanged
  oauth.py                 # DELETE (JWKSVerifier replaced by ScalekitProvider)
Pipfile                    # REMOVE fastapi, scalekit-sdk-python
tests/
  test_server.py           # REWRITE: FastMCP test patterns
```

### Pattern 1: FastMCP Server Initialization with Two-Mode Auth

```python
# Source: CONTEXT.md D-03/D-04; ScalekitProvider signature verified via inspect.getsource
import os
import logging
import sys
from contextlib import asynccontextmanager
from fastmcp import FastMCP, Context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

SCALEKIT_ENVIRONMENT_URL = os.environ.get("SCALEKIT_ENVIRONMENT_URL", "")
SCALEKIT_RESOURCE_ID = os.environ.get("SCALEKIT_RESOURCE_ID", "")
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", "")
MCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")   # fallback for logging
MCP_PORT = int(os.environ.get("FASTMCP_PORT", "7363"))  # fallback for logging

# Two-mode auth detection (D-04): ALL THREE must be set for remote mode
_auth = None
if SCALEKIT_ENVIRONMENT_URL and SCALEKIT_RESOURCE_ID and MCP_BASE_URL:
    from fastmcp.server.auth.providers.scalekit import ScalekitProvider
    _auth = ScalekitProvider(
        environment_url=SCALEKIT_ENVIRONMENT_URL,
        resource_id=SCALEKIT_RESOURCE_ID,
        base_url=MCP_BASE_URL,
    )
    logger.info("ScaleKit auth enabled (remote mode)")
else:
    logger.info("Auth disabled (local mode — SCALEKIT env vars not fully set)")

@asynccontextmanager
async def _lifespan(server: FastMCP):
    app_ctx = _startup()   # raises SystemExit(1) on failure
    yield {"app": app_ctx}

mcp = FastMCP("lds-scripture-index", auth=_auth, lifespan=_lifespan)
```

[VERIFIED: `ScalekitProvider.__init__(*, environment_url, resource_id, base_url, mcp_url=None, client_id=None, required_scopes=None, ...)` — source inspected; `base_url` is the correct current parameter name (not `mcp_url` which is deprecated)]

### Pattern 2: FastMCP Lifespan — Context Dict and Tool Access

FastMCP lifespans yield a dict. Tools access it via `ctx.lifespan_context["key"]` — a direct property on `Context`.

```python
# Source: Context.lifespan_context property inspected from installed source
from fastmcp import FastMCP, Context
from dataclasses import dataclass

@dataclass
class AppContext:
    client: ...       # chromadb.ClientAPI
    collections: dict # str -> chromadb.Collection

@asynccontextmanager
async def _lifespan(server: FastMCP):
    app_ctx = _startup()
    yield {"app": app_ctx}   # yield a dict

@mcp.tool()
async def search(
    query: str,
    speaker: str | None = None,
    year: int | None = None,
    season: str | None = None,
    collection: str = "paragraphs",
    limit: int = 5,
    ctx: Context = None,
) -> str:
    """Search LDS General Conference content by meaning. ..."""
    app: AppContext = ctx.lifespan_context["app"]  # direct dict access
    ...

@mcp.tool()
async def get_talk(talk_id: str, ctx: Context = None) -> str:
    """Retrieve the full text of a General Conference talk by ID. ..."""
    app: AppContext = ctx.lifespan_context["app"]
    ...
```

**Key change:** The old `_FakeMCPCtx` bridge used `ctx.request_context.lifespan_context`. With native FastMCP, `ctx.lifespan_context` is a direct property returning the dict yielded by the lifespan function. No bridge needed.

[VERIFIED: `Context.lifespan_context` property exists and returns `rc.lifespan_context` — from installed source; `ctx.lifespan_context["app"]` pattern confirmed in FastMCP docs embedded in Context source]

### Pattern 3: Custom Health Route

```python
# Source: FastMCP.custom_route(path, methods, name=None, include_in_schema=True) — verified at runtime
from starlette.requests import Request
from starlette.responses import JSONResponse

@mcp.custom_route("/health", methods=["GET"])
async def health_handler(request: Request) -> JSONResponse:
    """Live health check — Ollama + ChromaDB reachability."""
    status = {"ollama": "reachable", "chromadb": "reachable"}
    http_status = 200
    try:
        ollama_url = resolve_ollama_url()
        ef = get_embedding_function(url=ollama_url)
        ef(["health"])
    except Exception:
        status["ollama"] = "unreachable"
        http_status = 503
    try:
        client = get_chromadb_client()
        for name in CHROMADB_COLLECTION_NAMES.values():
            client.get_collection(name=name)
    except Exception:
        status["chromadb"] = "unreachable"
        http_status = 503
    payload = {"status": "ok" if http_status == 200 else "degraded", **status}
    return JSONResponse(payload, status_code=http_status)
```

Custom routes are registered via FastMCP's internal route list. They are NOT behind the MCP auth middleware — `GET /health` is always unauthenticated (correct behavior, same as current implementation).

[VERIFIED: `FastMCP.custom_route` signature confirmed via `inspect.signature` at runtime]

### Pattern 4: OAuth Discovery Endpoints (Automatic — D-06)

No manual route registration needed. `ScalekitProvider.get_routes()` provides both:

```
GET /.well-known/oauth-protected-resource   → RemoteAuthProvider base class (RFC 9728)
GET /.well-known/oauth-authorization-server → ScalekitProvider: proxies from
    {environment_url}/.well-known/oauth-authorization-server/resources/{resource_id}
```

The old `_protected_resource_metadata()` and `_auth_server_metadata()` functions in `server.py` are completely replaced.

[VERIFIED: `ScalekitProvider.get_routes()` source inspected — adds `/.well-known/oauth-authorization-server` route; `RemoteAuthProvider.get_routes()` adds `/.well-known/oauth-protected-resource`]

### Pattern 5: Entry Point

FastMCP settings use `FASTMCP_` env prefix (verified by live test):

```python
# Source: fastmcp.settings source — env_prefix="FASTMCP_"; host default "127.0.0.1", port default 8000
if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_http_async(
        host=os.environ.get("FASTMCP_HOST", "0.0.0.0"),  # must override: default is 127.0.0.1
        port=int(os.environ.get("FASTMCP_PORT", "7363")), # must override: default is 8000
        transport="http",
    ))
```

`run_http_async` wraps uvicorn internally. Passing `host=` and `port=` explicitly is required — defaults are wrong for Docker deployment.

[VERIFIED: `fastmcp.settings.host` defaults to `"127.0.0.1"`; `fastmcp.settings.port` defaults to `8000`; setting `FASTMCP_HOST="0.0.0.0"` before import changes the value — live test confirmed]

### Pattern 6: TestClient Pattern for Tests

```python
# Source: TestClient compatibility verified by runtime test
from starlette.testclient import TestClient
from unittest.mock import patch

def test_tools_list_local_mode():
    """Local mode: tools/list succeeds without token when auth=None."""
    with patch("server._startup", return_value=_mock_startup()), \
         patch("server._auth", None):
        from server import mcp
        app = mcp.http_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        })
    assert resp.status_code == 200

def test_tools_list_with_debug_token():
    """DebugTokenVerifier: any non-empty token is accepted."""
    from fastmcp.server.auth.providers.debug import DebugTokenVerifier
    with patch("server._startup", return_value=_mock_startup()), \
         patch("server._auth", DebugTokenVerifier()):
        from server import mcp
        client = TestClient(mcp.http_app(), raise_server_exceptions=False)
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        }, headers={"Authorization": "Bearer any-token"})
    assert resp.status_code == 200
```

[VERIFIED: `TestClient(FastMCP("test").http_app())` succeeds at runtime; `mcp.http_app()` returns `StarletteWithLifespan` (Starlette subclass)]

### Anti-Patterns to Avoid

- **`DebugAuthProvider`:** Does not exist in fastmcp 3.2.4. Use `DebugTokenVerifier`.
- **`ctx.request_context.lifespan_context`:** Old bridge pattern. Use `ctx.lifespan_context` directly.
- **`BaseHTTPMiddleware`:** Banned (D-03). Root cause of Phase 16.2 anyio failures. FastMCP auth is `FastMCP(auth=...)`, not middleware.
- **`mcp_url=` parameter:** Deprecated in `ScalekitProvider`; use `base_url=` (logs deprecation warning).
- **`client_id=` parameter in `ScalekitProvider`:** Deprecated; logs warning and will be removed.
- **`streamable_http_app()`:** Old API name. Current method is `http_app(transport="http")`.
- **Passing auth as middleware:** Auth is handled by FastMCP's protocol layer; never add it as ASGI middleware.
- **Hardcoding `host="127.0.0.1"` or `port=8000`:** FastMCP defaults are wrong for Docker. Always override.
- **`from fastapi.testclient import TestClient`:** Will break after fastapi is removed. Use `from starlette.testclient import TestClient`.
- **`from mcp.server.fastmcp import FastMCP`:** Old import (mcp submodule). Use `from fastmcp import FastMCP`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWKS fetch + JWT validation | Custom verifier (old `auth/oauth.py`) | `ScalekitProvider` (built-in) | Handles RS256, JWKS caching, expiry, audience |
| OAuth discovery endpoints | Manual `/.well-known/...` routes | `ScalekitProvider.get_routes()` | Both endpoints served automatically |
| Bearer token 401 rejection | Manual auth check in dispatcher | FastMCP built-in auth enforcement | Returns standards-compliant 401 with `WWW-Authenticate` |
| MCP protocol dispatch | Manual JSON-RPC router (current server.py) | `@mcp.tool()` + FastMCP dispatch | ~500 lines of dispatcher eliminated |
| ASGI server startup | `uvicorn.run(app, ...)` directly | `mcp.run_http_async(host, port, transport)` | Handles lifespan, signal handling, banner |
| JSON Schema from tool args | Manual `inputSchema` dicts | `@mcp.tool()` + type annotations | FastMCP generates schema automatically from Python types |

---

## Reusable Code from Current `server.py`

The following functions and class are **pure** (no FastAPI/FastMCP dependency) and can be copy-pasted verbatim into the new `server.py`:

| Symbol | Lines (approx) | Status |
|--------|----------------|--------|
| `AppContext` dataclass | 2 | Copy unchanged |
| `_resolve_chromadb_client()` | ~10 | Copy unchanged |
| `_check_ollama()` | ~15 | Copy unchanged |
| `_load_collections()` | ~20 | Copy unchanged |
| `_startup()` | ~10 | Copy unchanged |
| `_build_where_filter()` | ~10 | Copy unchanged |
| `_matches_speaker()` | ~5 | Copy unchanged |
| `_format_search_result()` | ~10 | Copy unchanged |
| `_parse_talk_id()` | ~8 | Copy unchanged |
| `MCP_INSTRUCTIONS` constant | ~6 | Copy unchanged |

**What is eliminated entirely:**
- `_FakeMCPCtx` class (bridge artifact)
- `_sessions` dict and all session management
- `_mcp_response()`, `_error_response()`, `_unauthorized_response()`
- `_handle_initialize()`, `_handle_tools_list()`, `_handle_tools_call()`
- `_verify_auth()`, `_jwt_verifier` module-level variable
- `build_app()` factory function
- `health_check()` standalone function (replaced by `@mcp.custom_route` handler)
- `_protected_resource_metadata()`, `_auth_server_metadata()` (replaced by `ScalekitProvider`)
- All `fastapi` imports

---

## Common Pitfalls

### Pitfall 1: Wrong Debug Provider Class Name

**What goes wrong:** `ImportError: cannot import name 'DebugAuthProvider'` — CONTEXT.md D-10 uses the wrong name.
**Why it happens:** The class is named `DebugTokenVerifier` (it's a `TokenVerifier`, not an `AuthProvider`).
**How to avoid:** Always import `from fastmcp.server.auth.providers.debug import DebugTokenVerifier`.
**Warning signs:** ImportError on first test run.

[VERIFIED: `from fastmcp.server.auth.providers.debug import DebugAuthProvider` → `ImportError` at runtime]

### Pitfall 2: Old Lifespan Context Access Pattern

**What goes wrong:** `AttributeError` or wrong value when tools use `ctx.request_context.lifespan_context`.
**Why it happens:** `_FakeMCPCtx` bridge is gone; native FastMCP puts lifespan dict directly on `ctx.lifespan_context`.
**How to avoid:** Use `ctx.lifespan_context["app"]` in all tool functions.
**Warning signs:** Tool functions raising AttributeError; tests passing but production failing.

### Pitfall 3: FastMCP Default Host is Localhost

**What goes wrong:** Server starts but is unreachable from Docker host / Cloudflare Tunnel.
**Why it happens:** `fastmcp.settings.host` defaults to `"127.0.0.1"`.
**How to avoid:** Pass `host="0.0.0.0"` (or read from `FASTMCP_HOST`) explicitly to `run_http_async()`.
**Warning signs:** Server logs show bind on `127.0.0.1`; Caddy proxy gets connection refused.

[VERIFIED: Default host confirmed `"127.0.0.1"` from settings source; `FASTMCP_HOST` env var overrides it]

### Pitfall 4: FastMCP Default Port is 8000

**What goes wrong:** Server starts on port 8000 instead of project's 7363.
**Why it happens:** `fastmcp.settings.port` defaults to `8000`.
**How to avoid:** Pass `port=7363` (or read from `FASTMCP_PORT`) explicitly to `run_http_async()`.
**Warning signs:** Caddy proxy can't connect; logs show binding on 8000.

### Pitfall 5: ScalekitProvider `mcp_url` vs `base_url`

**What goes wrong:** Deprecation warning logged at every startup.
**Why it happens:** `mcp_url` was the original parameter name; renamed to `base_url` in current version.
**How to avoid:** Use `base_url=MCP_BASE_URL` in `ScalekitProvider(...)`.
**Warning signs:** Log message `"ScalekitProvider parameter 'mcp_url' is deprecated"`.

[VERIFIED: Deprecation warning path confirmed in `ScalekitProvider.__init__` source]

### Pitfall 6: `test_fastmcp_removed` test will pass trivially but is outdated

**What goes wrong:** The existing `test_fastmcp_removed` asserts `"from mcp.server.fastmcp import FastMCP" not in source`. The new `server.py` imports `from fastmcp import FastMCP` — different path — so the test passes but is testing the wrong thing.
**How to avoid:** In the test rewrite, replace this test with a positive assertion: `"from fastmcp import FastMCP" in source` and `"from fastapi" not in source`.

### Pitfall 7: TestClient import after fastapi removal

**What goes wrong:** `ImportError: No module named 'fastapi'` on test run.
**Why it happens:** Existing tests may use `from fastapi.testclient import TestClient`.
**How to avoid:** All test files must use `from starlette.testclient import TestClient`.
**Warning signs:** ImportError on `from fastapi.testclient`.

---

## Test Rewrite Analysis

### Tests That Carry Over (pure unit tests, no server framework dependency)

| Test Class / Function | Action | Note |
|-----------------------|--------|------|
| `TestBuildWhereFilter` | KEEP | Tests `_build_where_filter` — pure function, unchanged |
| `TestMatchesSpeaker` | KEEP | Tests `_matches_speaker` — pure function, unchanged |
| `TestFormatSearchResult` | KEEP | Tests `_format_search_result` — pure function, unchanged |
| `TestParseTalkId` | KEEP | Tests `_parse_talk_id` — pure function, unchanged |
| `test_chromadb_client_*` | KEEP | Tests `config/chromadb_client.py` — unchanged |
| `test_ollama_*` | KEEP | Tests `config/ollama.py` — unchanged |
| `test_chromadb_missing_collection_exits` | KEEP | `_load_collections` still exists |
| `test_ollama_failure_is_non_fatal` | KEEP | `_check_ollama` still exists |
| `test_all_collections_warmed` | KEEP | `_load_collections` still exists |
| `test_check_ollama_passes_resolved_url` | KEEP | `_check_ollama` still exists |

### Tests That Need Rewriting

| Test | Why | New Approach |
|------|-----|-------------|
| `TestSearchTool` | Context pattern changes | `ctx.lifespan_context["app"]` instead of `_FakeMCPCtx` |
| `TestGetTalkTool` | Same | Same |
| `_make_mock_ctx()` helper | Bridge pattern gone | New helper yields dict directly |
| All dispatcher tests | FastAPI → FastMCP; `build_app()` gone | `TestClient(mcp.http_app())` + `/mcp` endpoint |
| `test_health_*` | `build_app()` gone | `TestClient(mcp.http_app()); client.get("/health")` |
| `test_fastmcp_removed` | Wrong assertion | Flip: assert FastMCP import present, FastAPI absent |
| Auth tests | `AUTH0_DOMAIN`/`_jwt_verifier` → `_auth` + `DebugTokenVerifier` | Patch `server._auth` with `DebugTokenVerifier()` |
| `test_protected_resource_metadata` | Manual route gone | Use `ScalekitProvider` + verify auto-served endpoint |
| `test_no_stdio_references` | Still valid | Keep as-is |
| `test_head_returns_protocol_version` | Endpoint is now `/mcp` not `/` | Update to `client.head("/mcp")` |
| `test_get_root_returns_405` | FastMCP may handle `GET /mcp` differently | Verify FastMCP behavior and update |
| `test_delete_session_cleanup` | FastMCP native sessions | FastMCP handles DELETE; verify behavior |

### New Tests Needed

| Test | What It Verifies | Req |
|------|-----------------|-----|
| `test_mcp_tools_list_local_mode` | No auth when `_auth=None` | AUTH-02 |
| `test_mcp_tools_list_requires_auth` | 401 without token with `DebugTokenVerifier` as auth | AUTH-02 |
| `test_mcp_tools_list_valid_token` | 200 with valid token via `DebugTokenVerifier` | OAUTH-02 |
| `test_initialize_no_auth_required` | `initialize` succeeds without token in remote mode | OAUTH-01 |
| `test_env_vars_configurable` | No hardcoded URLs in server.py source | DEPLOY-02 |
| `test_fastapi_absent` | `from fastapi` not in server.py source | D-09 |

---

## Code Examples

### Minimal FastMCP + ScalekitProvider Server

```python
# Verified from installed fastmcp 3.2.4 source + CONTEXT.md decisions
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

import chromadb
from fastmcp import FastMCP, Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from config.chromadb_client import get_chromadb_client
from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from config.ollama import resolve_ollama_url, get_embedding_function

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

@dataclass
class AppContext:
    client: chromadb.ClientAPI
    collections: dict

# ... _resolve_chromadb_client, _check_ollama, _load_collections, _startup ...
# (copy verbatim from existing server.py)

# ... _build_where_filter, _matches_speaker, _format_search_result, _parse_talk_id ...
# (copy verbatim from existing server.py)

SCALEKIT_ENVIRONMENT_URL = os.environ.get("SCALEKIT_ENVIRONMENT_URL", "")
SCALEKIT_RESOURCE_ID = os.environ.get("SCALEKIT_RESOURCE_ID", "")
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", "")

_auth = None
if SCALEKIT_ENVIRONMENT_URL and SCALEKIT_RESOURCE_ID and MCP_BASE_URL:
    from fastmcp.server.auth.providers.scalekit import ScalekitProvider
    _auth = ScalekitProvider(
        environment_url=SCALEKIT_ENVIRONMENT_URL,
        resource_id=SCALEKIT_RESOURCE_ID,
        base_url=MCP_BASE_URL,
    )
    logger.info("ScaleKit auth enabled (remote mode)")
else:
    logger.info("Auth disabled (local mode)")

@asynccontextmanager
async def _lifespan(server: FastMCP):
    app_ctx = _startup()
    yield {"app": app_ctx}

MCP_INSTRUCTIONS = (
    "LDS General Conference corpus: 5,838 talks (1971-present) across 4 collections "
    "..."
)

mcp = FastMCP("lds-scripture-index", instructions=MCP_INSTRUCTIONS, auth=_auth, lifespan=_lifespan)

@mcp.tool()
async def search(
    query: str,
    speaker: str | None = None,
    year: int | None = None,
    season: str | None = None,
    collection: str = "paragraphs",
    limit: int = 5,
    ctx: Context = None,
) -> str:
    """Search LDS General Conference content by meaning. ..."""
    app: AppContext = ctx.lifespan_context["app"]
    # ... business logic unchanged from current server.py ...

@mcp.tool()
async def get_talk(talk_id: str, ctx: Context = None) -> str:
    """Retrieve the full text of a General Conference talk by ID. ..."""
    app: AppContext = ctx.lifespan_context["app"]
    # ... business logic unchanged from current server.py ...

@mcp.custom_route("/health", methods=["GET"])
async def health_handler(request: Request) -> JSONResponse:
    # ... same logic as current health_check() ...

if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_http_async(
        host=os.environ.get("FASTMCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("FASTMCP_PORT", "7363")),
        transport="http",
    ))
```

### Test Helper Pattern (New)

```python
# Replace old _make_mock_ctx helper that used _FakeMCPCtx
from unittest.mock import MagicMock
from server import AppContext

def _make_mock_app_ctx(collections: dict) -> AppContext:
    """Build an AppContext with given mock collections."""
    return AppContext(client=MagicMock(), collections=collections)

# In tool tests, patch ctx.lifespan_context directly:
def test_search_basic():
    from server import search
    mock_col = MagicMock()
    mock_col.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]]}
    app_ctx = _make_mock_app_ctx({"paragraphs": mock_col})
    
    mock_ctx = MagicMock()
    mock_ctx.lifespan_context = {"app": app_ctx}  # dict access, not .lifespan_context attribute chain
    
    result = asyncio.run(search(query="test", ctx=mock_ctx))
    assert result == "No results found."
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastAPI + manual JSON-RPC dispatcher | FastMCP native MCP handling | Phase 19 | Eliminates ~500 lines of protocol boilerplate |
| Auth0 + custom `JWKSVerifier` (PyJWT) | ScaleKit + `ScalekitProvider` (built-in) | Phase 19 | No custom verifier class; full provider replacement |
| `mcp.streamable_http_app()` | `mcp.http_app(transport="http")` | fastmcp 3.x | Old method name no longer exists |
| `ctx.request_context.lifespan_context` | `ctx.lifespan_context` | fastmcp 3.x | Simpler direct property |
| `DebugAuthProvider` | `DebugTokenVerifier` | fastmcp 3.2.4 | Class implements `TokenVerifier`, not `AuthProvider` |
| Manual OAuth discovery routes | `ScalekitProvider.get_routes()` auto-serves | Phase 19 | Zero manual implementation |
| `scalekit-sdk-python` for JWT validation | Not used | Phase 19 (D-03) | `ScalekitProvider` handles JWKS/JWT internally |
| `fastapi` as server framework | Not used | Phase 19 (D-09) | Starlette only (via FastMCP) |

**Deprecated/removed from new server.py:**
- `_FakeMCPCtx` class
- `_sessions` dict and session management code
- `_mcp_response()`, `_error_response()`, `_unauthorized_response()`
- `_handle_initialize()`, `_handle_tools_list()`, `_handle_tools_call()`
- `_verify_auth()` function and `_jwt_verifier` module variable
- `build_app()` factory
- `health_check()` standalone function
- `_protected_resource_metadata()`, `_auth_server_metadata()`
- All `from fastapi import ...` imports
- `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `AUTH0_CLIENT_SECRET` env vars

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Existing helper functions are copy-paste safe with no framework deps | Reusable Code section | Low — functions use only stdlib + chromadb/ollama |
| A2 | FastMCP's `DELETE /mcp` handling satisfies D-07 session cleanup | Test Rewrite section | Low — FastMCP's session management is protocol-compliant |
| A3 | CORS middleware (if needed) works via `mcp.run_http_async(middleware=[...])` | Anti-patterns | Medium — not verified via live test; Claude's discretion area |

**All other claims are VERIFIED** by direct Python inspection of installed fastmcp 3.2.4 packages.

---

## Open Questions

1. **CORS middleware**
   - What we know: `run_http_async(middleware=[...])` accepts a list. Current server uses CORSMiddleware.
   - What's unclear: Whether CORS is needed for MCP clients (typically not browser-based).
   - Recommendation: Omit CORS initially (Claude's discretion); add if needed for browser-based clients.

2. **MCP path: `/` vs `/mcp`**
   - What we know: FastMCP defaults to `/mcp`. Old server handled both `/` and `/mcp`.
   - What's unclear: Whether client configs need updating.
   - Recommendation: Accept `/mcp` as the canonical path per FastMCP convention. Update any references.

3. **`test_head_returns_protocol_version` behavior**
   - What we know: `HEAD /` returned `MCP-Protocol-Version` in old server. FastMCP serves MCP at `/mcp`.
   - What's unclear: Whether FastMCP responds to `HEAD /mcp` or `HEAD /` with protocol version header.
   - Recommendation: Test empirically in Plan 02 test rewrite.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `fastmcp` | Server framework | Yes | 3.2.4 | — |
| `ScalekitProvider` | Auth (remote mode) | Yes (built-in to fastmcp) | 3.2.4 | `auth=None` (local mode) |
| `DebugTokenVerifier` | Unit tests | Yes (built-in to fastmcp) | 3.2.4 | — |
| `scalekit-sdk-python` | Nothing — to be removed | Yes (2.7.1 installed) | 2.7.1 | Remove from Pipfile |
| `fastapi` | Nothing — to be removed | Yes (in Pipfile) | — | Remove from Pipfile |
| `starlette` | TestClient | Yes (fastmcp dep) | — | — |
| ScaleKit tenant (network) | Remote mode JWT validation | Unknown | — | Local mode (no SCALEKIT_* vars) |

**Missing dependencies with no fallback:** None — all required packages present.
**To remove:** `scalekit-sdk-python` and `fastapi` per D-09. `scalekit-sdk-python` 2.7.1 is currently installed and must be uninstalled + removed from Pipfile.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | None (discovered automatically) |
| Quick run command | `pipenv run py -m pytest tests/test_server.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRANS-01 | MCP client connects via Streamable HTTP on `/mcp` | integration | `pytest tests/test_server.py::test_initialize_no_auth -x` | Rewrite |
| TRANS-02 | GET /health returns 200/503 with correct JSON | unit | `pytest tests/test_server.py::test_health_returns_200 -x` | Rewrite |
| AUTH-02 | 401 without token (remote); 200 without token (local) | unit | `pytest tests/test_server.py::test_tools_list_requires_auth -x` | Rewrite |
| OAUTH-01 | `initialize` succeeds without auth in remote mode | unit | `pytest tests/test_server.py::test_initialize_no_auth -x` | Rewrite |
| OAUTH-02 | Valid token accepted; invalid token returns 401 | unit | `pytest tests/test_server.py::test_tools_list_valid_token -x` | New |
| DEPLOY-02 | No hardcoded values; all from env | code-scan | `pytest tests/test_server.py::test_env_vars_configurable -x` | New |

### Sampling Rate

- **Per task commit:** `pipenv run py -m pytest tests/test_server.py -x -q`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_server.py` — full rewrite required (Wave 1 of Plan 02); existing tests reference `build_app()`, `AUTH0_DOMAIN`, `_jwt_verifier`, `_FakeMCPCtx` — all removed
- [ ] No new files needed in Wave 0 — all implementation goes into existing `server.py` and `tests/test_server.py`

*(Existing test infrastructure (pytest, test discovery) covers the phase — no framework install needed)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `ScalekitProvider` (JWKS RS256 JWT validation via internal `JWTVerifier`) |
| V3 Session Management | yes | FastMCP native session handling (MCP-Session-Id) |
| V4 Access Control | no | No RBAC in scope (D-08 — deferred) |
| V5 Input Validation | yes | FastMCP type annotation → JSON Schema validation; tool params sanitized |
| V6 Cryptography | yes | `ScalekitProvider` uses RS256 — never hand-rolled |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Forged JWT tokens | Spoofing | `ScalekitProvider` verifies against ScaleKit JWKS (`{env_url}/keys`) |
| Tool injection via `query` param | Tampering | ChromaDB query is parameterized (embedding call); results read-only |
| Unauthenticated tool access (remote) | Elevation of Privilege | FastMCP auth layer enforces JWT before dispatching tools/list, tools/call |
| Local mode accidentally exposed publicly | Info Disclosure | All THREE env vars must be set for remote mode — partial config stays local |

---

## Sources

### Primary (HIGH confidence — verified via installed package source)

- Installed `C:\Users\wbjen\.virtualenvs\LDS_MCP-4gXzNxfn\Lib\site-packages\fastmcp` (fastmcp 3.2.4):
  - `ScalekitProvider.__init__` signature and `get_routes()` implementation
  - `DebugTokenVerifier` class — confirmed `DebugAuthProvider` does not exist (ImportError)
  - `Context.lifespan_context` property
  - `FastMCP.custom_route`, `FastMCP.http_app`, `FastMCP.run_http_async` signatures
  - `fastmcp.settings.host` default = `"127.0.0.1"`, `fastmcp.settings.port` default = `8000`
  - `FASTMCP_HOST`/`FASTMCP_PORT` env var override — live test confirmed

### Secondary (MEDIUM confidence)

- https://docs.scalekit.com/mcp/overview/ — ScaleKit operator dashboard setup steps (D-12)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — package versions verified from installed source; class names confirmed by runtime import attempts
- Architecture patterns: HIGH — all method signatures verified via `inspect.signature` and `inspect.getsource`
- Pitfalls: HIGH — class name error (`DebugAuthProvider`) confirmed by live ImportError; default host/port confirmed by settings inspection
- Test patterns: MEDIUM — TestClient creation verified; specific FastMCP dispatcher behavior for auth paths inferred from source but not tested end-to-end

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (fastmcp 3.2.4 is current; re-verify if fastmcp is upgraded)
