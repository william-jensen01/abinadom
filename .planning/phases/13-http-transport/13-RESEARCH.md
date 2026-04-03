# Phase 13: HTTP Transport - Research

**Researched:** 2026-04-03
**Domain:** FastMCP Streamable HTTP transport, Starlette custom routes, health endpoint design
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Swap `mcp.run(transport="stdio")` to `mcp.run(transport="streamable-http")`. No uvicorn invocation needed — FastMCP handles it internally via `run_streamable_http_async`.
- **D-02:** MCP endpoint path stays at `/mcp` (FastMCP default for streamable-http). No `streamable_http_path` override.
- **D-03:** Remove all stdio references — update module docstring, entry-point comment, and any inline references to stdio transport. Clean break, no fallback.
- **D-04:** Pass `MCP_HOST` and `MCP_PORT` env vars into the `FastMCP(...)` constructor at module initialization. Defaults: `host="0.0.0.0"`, `port=8000`.
- **D-05:** `0.0.0.0` default is intentional — Docker-ready from day one. FastMCP's auto DNS-rebinding protection (localhost-only) is not needed here since Caddy + Cloudflare Tunnel handle perimeter security in Phase 16.
- **D-06:** Only `MCP_HOST` and `MCP_PORT` are wired in this phase. All other env-var wiring (`CHROMADB_PATH`, `OLLAMA_URL`, secrets) is Phase 15's scope.
- **D-07:** Add a `GET /health` route to the Starlette app that FastMCP exposes for streamable-http. Returns 200 with a JSON payload confirming both Ollama and ChromaDB are reachable.
- **D-08:** Health payload: `{"status": "ok", "ollama": "reachable", "chromadb": "reachable"}`
- **D-09:** `/health` performs live checks — not a static response. Ollama check: attempt an embedding call (same as startup `_check_ollama`). ChromaDB check: confirm the client can connect and collections exist (reuse startup guard logic without full count validation).
- **D-10:** If either dependency is down at `/health` call time, return 503 (not 200) with the failing dependency flagged. Exact error shape: Claude's discretion.

### Claude's Discretion

- How `/health` is mounted on the Starlette app (custom_routes parameter vs `streamable_http_app()` patching vs a separate ASGI mount)
- Whether `_check_ollama` and `_check_chromadb` logic is refactored into a shared helper or called inline in the health handler
- 503 error shape when a dependency fails

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRANS-01 | User can connect any MCP client (Claude.ai, ChatGPT, etc.) via Streamable HTTP URL | D-01 through D-05: FastMCP `transport="streamable-http"` exposes `/mcp` endpoint; uvicorn is bundled and invoked internally |
| TRANS-02 | Operator can verify server health via GET /health endpoint | D-07 through D-10: `@mcp.custom_route("/health", methods=["GET"])` decorator is the correct FastMCP 1.26.0 API |
</phase_requirements>

---

## Summary

Phase 13 is a targeted transport swap: replace `mcp.run(transport="stdio")` with `mcp.run(transport="streamable-http")`, add two env var params to the `FastMCP(...)` constructor, and register a `/health` route with live dependency checks. The existing server logic (tools, lifespan, startup validation, ChromaDB/Ollama helpers) is entirely unchanged.

FastMCP 1.26.0 (the installed version) handles the full HTTP stack internally. `mcp.run(transport="streamable-http")` calls `run_streamable_http_async()`, which builds a Starlette app via `streamable_http_app()` and passes it to uvicorn. uvicorn 0.42.0 is already installed as a transitive dependency — no new package installs required for the transport layer.

The `/health` endpoint is registered via `@mcp.custom_route("/health", methods=["GET"])` — a first-class FastMCP decorator that appends a Starlette `Route` to `_custom_starlette_routes`. This list is merged into the Starlette app inside `streamable_http_app()`, so the route is live when the server starts. The decorator is documented explicitly for health check use cases.

**Primary recommendation:** Use `@mcp.custom_route("/health", methods=["GET"])` for the health endpoint. Pass `host=` and `port=` directly to `FastMCP(...)`. Change only three lines of the entry-point block, add ~30 lines for the health handler.

---

## Standard Stack

### Core (all already installed — zero new packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mcp (FastMCP) | 1.26.0 | MCP server + HTTP transport | Already installed; `transport="streamable-http"` confirmed available |
| uvicorn | 0.42.0 | ASGI server invoked internally by FastMCP | Transitive dep; FastMCP calls it directly inside `run_streamable_http_async` |
| starlette | 1.0.0 | HTTP routing, Request/Response types for health handler | Transitive dep; `custom_route` decorator produces Starlette `Route` objects |
| httpx | 0.28.1 | HTTP client for testing health endpoint | Transitive dep; used by Starlette TestClient |

### No Installation Needed

All required packages are present as transitive dependencies of `mcp`. Running `pipenv install` is not required for this phase.

---

## Architecture Patterns

### How FastMCP Streamable HTTP Works (verified from source)

```
mcp.run(transport="streamable-http")
  └─> anyio.run(self.run_streamable_http_async)
        └─> starlette_app = self.streamable_http_app()
              # Builds Starlette app with:
              #   - Route("/mcp", endpoint=StreamableHTTPASGIApp)
              #   - routes from self._custom_starlette_routes (appended last)
        └─> uvicorn.Config(starlette_app, host=..., port=...)
        └─> uvicorn.Server(...).serve()
```

**Key finding:** `_custom_starlette_routes` is populated by `@mcp.custom_route(...)` calls, and is merged into the Starlette app inside `streamable_http_app()`. The decorator must be called at module level (before `mcp.run`) so the route is registered before the Starlette app is built.

### DNS Rebinding Protection Auto-Behavior (CRITICAL)

FastMCP 1.26.0 automatically enables `TransportSecuritySettings` when `host` is `127.0.0.1`, `localhost`, or `::1`. This protection restricts `Host` headers to localhost-only patterns.

With `host="0.0.0.0"` (D-05), FastMCP does NOT auto-enable this protection — `transport_security` stays `None`. This is the correct behavior for a Docker-ready server behind a reverse proxy.

**Confirmed from source (line 177-183):**
```python
if transport_security is None and host in ("127.0.0.1", "localhost", "::1"):
    transport_security = TransportSecuritySettings(...)
```
`"0.0.0.0"` is not in that list — protection is not activated.

### Pattern 1: Transport Swap (entry point)

```python
# Source: FastMCP server.py constructor (verified from source)

MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))

mcp = FastMCP(
    "lds-scripture-index",
    lifespan=lifespan,
    host=MCP_HOST,
    port=MCP_PORT,
    instructions=(...),
)

# Entry point — streamable-http transport
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

### Pattern 2: Health Endpoint Registration

```python
# Source: FastMCP server.py @custom_route decorator (verified from source, line 732-734)
# Must be defined at module level, after mcp = FastMCP(...) but before mcp.run()

from starlette.requests import Request
from starlette.responses import JSONResponse

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    ...
```

**Important:** The decorator is documented (in source) as intended for "health check endpoints" and explicitly noted as not requiring authorization.

### Pattern 3: Health Handler Logic (recommended shape)

The health handler needs live checks for Ollama and ChromaDB. Two implementation approaches are viable:

**Option A — Inline calls using AppContext (recommended)**

Access `mcp.session_manager` is not straightforward from a health handler without the lifespan context. Instead, perform independent lightweight checks — the health endpoint should not depend on the lifespan context being accessible.

```python
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    status = {"ollama": "reachable", "chromadb": "reachable"}
    http_status = 200

    # Ollama check: live embedding call (matches D-09)
    try:
        ollama_url = resolve_ollama_url()
        ef = get_embedding_function(url=ollama_url)
        ef(["health"])
    except Exception:
        status["ollama"] = "unreachable"
        http_status = 503

    # ChromaDB check: connect and verify collections exist (matches D-09)
    try:
        path = _resolve_chromadb_path()
        client = chromadb.PersistentClient(path=path)
        for name in CHROMADB_COLLECTION_NAMES.values():
            client.get_collection(name=name)
    except Exception:
        status["chromadb"] = "unreachable"
        http_status = 503

    payload = {"status": "ok" if http_status == 200 else "degraded", **status}
    return JSONResponse(payload, status_code=http_status)
```

**Option B — Refactor shared helpers**

Extract `_check_ollama_reachable() -> bool` and `_check_chromadb_reachable() -> bool` from existing startup functions and call them from both `_startup()` and the health handler. Reduces duplication but adds refactor surface.

Either option satisfies D-09. The planner should choose based on desired task scope.

### Anti-Patterns to Avoid

- **Calling `mcp.streamable_http_app()` before the entry-point block:** `_session_manager` is `None` until `streamable_http_app()` is called; the decorator approach populates `_custom_starlette_routes` before the app is built, which is correct.
- **Returning a static 200 from `/health`:** D-09 requires live checks. A static response fails the Docker Compose healthcheck intent (Phase 15).
- **`sys.exit(1)` inside the health handler:** The startup functions use `sys.exit(1)` on failure; the health handler must NOT replicate this — it must return 503 and continue serving.
- **Importing `MCP_HOST`/`MCP_PORT` as module-level constants before `os.environ.get`:** Both must be resolved at module import time, not inside `if __name__ == "__main__"`, because `FastMCP(...)` is at module level.
- **Overriding `streamable_http_path`:** D-02 says keep `/mcp` default. Do not pass `streamable_http_path=` to the constructor.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP server / ASGI runner | Custom uvicorn setup | `mcp.run(transport="streamable-http")` | FastMCP already wires uvicorn internally |
| Custom route registration | Patching `streamable_http_app()` return value | `@mcp.custom_route(...)` | First-class FastMCP API, documented for health endpoints, no monkeypatching |
| JSON response formatting | Manual `json.dumps` + `Response` | `starlette.responses.JSONResponse` | Handles Content-Type and encoding; already in dep tree |

---

## Common Pitfalls

### Pitfall 1: `sys.exit(1)` in the Health Handler

**What goes wrong:** The existing `_check_ollama()` calls `sys.exit(1)` on failure. If the health handler calls `_check_ollama()` directly, a failed Ollama call kills the entire server process instead of returning 503.

**Why it happens:** Startup and health endpoint have different failure semantics. Startup failure is fatal; health failure is informational.

**How to avoid:** Do not call `_check_ollama()` (the startup version) from the health handler. Either inline the check with try/except, or create a new boolean-returning helper that wraps the same logic without `sys.exit`.

**Warning signs:** Health endpoint calls cause the uvicorn process to exit rather than returning a response.

### Pitfall 2: `chromadb.PersistentClient` in Health Handler Creates a Second Client

**What goes wrong:** The health handler instantiates a new `PersistentClient` for each request. ChromaDB's PersistentClient uses SQLite; multiple concurrent clients can cause lock contention.

**Why it happens:** The health handler does not have direct access to the `AppContext` that holds the already-initialized client from startup.

**How to avoid:** The health check frequency is low (operator monitoring), so a fresh client per call is acceptable for this phase. For higher-frequency use, consider accessing the lifespan context — but that requires threading the session context through to the handler, which is more complex. For Phase 13 scope, a fresh client on each `/health` call is safe.

**Warning signs:** SQLite lock errors in logs when `/health` is polled frequently.

### Pitfall 3: `MCP_PORT` Type Conversion

**What goes wrong:** `os.environ.get("MCP_PORT", "8000")` returns a string. Passing a string to `FastMCP(port=...)` raises a `pydantic` validation error since `Settings.port` is typed as `int`.

**Why it happens:** Environment variables are always strings.

**How to avoid:** Always wrap with `int()`: `port=int(os.environ.get("MCP_PORT", "8000"))`.

**Warning signs:** `pydantic_core.ValidationError` at import time when `MCP_PORT` is set.

### Pitfall 4: `@mcp.custom_route` Must Be Called After `mcp = FastMCP(...)`

**What goes wrong:** Decorating a function before `mcp` is defined causes a `NameError`.

**Why it happens:** Python evaluates decorators at import time in order.

**How to avoid:** Place the `@mcp.custom_route("/health", ...)` decorated function after the `mcp = FastMCP(...)` line. Module-level order matters.

### Pitfall 5: stdio Docstring Residue Breaks Phase 15 Docs

**What goes wrong:** The module docstring currently says "exposes ... via stdio transport" and the entry-point comment says "stdio transport". Leaving these as-is creates misleading documentation that will confuse Phase 15/17 work.

**How to avoid:** D-03 explicitly requires cleaning all stdio references. Three locations to update:
1. Module docstring (top of `server.py`) — "via stdio transport" + "Stdout is reserved for MCP JSON-RPC"
2. Entry-point section comment — "stdio transport, no stdout output before MCP loop (INTG-01)"
3. `mcp.run(transport="stdio")` call itself

---

## Code Examples

### Full Entry-Point Pattern (after swap)

```python
# Source: FastMCP constructor signature (server.py lines 161-162, verified from source)

MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))

mcp = FastMCP(
    "lds-scripture-index",
    lifespan=lifespan,
    host=MCP_HOST,
    port=MCP_PORT,
    instructions=(...),
)

# [tool definitions here]

# [health route here]

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

### Health Route Registration (verified pattern)

```python
# Source: FastMCP server.py lines 732-734 (example in decorator docstring)
from starlette.requests import Request
from starlette.responses import JSONResponse

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    # Live checks — see Pitfall 1 before calling startup helpers directly
    ...
    return JSONResponse({"status": "ok", "ollama": "reachable", "chromadb": "reachable"})
```

### 503 Error Shape (Claude's discretion — recommended)

```python
# When one or both dependencies fail:
return JSONResponse(
    {
        "status": "degraded",
        "ollama": "unreachable",     # or "reachable"
        "chromadb": "reachable",     # or "unreachable"
    },
    status_code=503,
)
```

This shape is symmetric with the 200 payload (D-08) and machine-readable for Docker Compose healthcheck parsing.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `mcp.run(transport="stdio")` | `mcp.run(transport="streamable-http")` | Phase 13 | Any HTTP-capable MCP client can connect; stdio desktop use retired |
| No host/port config | `MCP_HOST` / `MCP_PORT` env vars | Phase 13 | 12-factor config; Docker Compose override ready |
| No health endpoint | `GET /health` with live dependency checks | Phase 13 | Docker Compose healthcheck target available for Phase 15 |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uvicorn | `mcp.run(transport="streamable-http")` internal ASGI runner | Yes | 0.42.0 | — |
| starlette | Route/Request/JSONResponse types for health handler | Yes | 1.0.0 | — |
| httpx | Starlette TestClient (test-time only) | Yes | 0.28.1 | — |
| pytest-asyncio | Async test functions | No | — | Use `asyncio.run()` (pattern already used in test_server.py) |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:**
- `pytest-asyncio`: Not installed and not needed. The existing test pattern (`asyncio.run(...)` in synchronous test functions) works correctly and should be continued in new health endpoint tests.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (no ini file — discovered from Pipfile dev-packages) |
| Config file | None |
| Quick run command | `pipenv run py -m pytest tests/test_server.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRANS-01 | `mcp` instance has `host="0.0.0.0"` and `port=8000` by default | unit | `pipenv run py -m pytest tests/test_server.py::test_mcp_host_port_defaults -x` | No — Wave 0 |
| TRANS-01 | `MCP_HOST` / `MCP_PORT` env vars override defaults | unit | `pipenv run py -m pytest tests/test_server.py::test_mcp_host_port_env_override -x` | No — Wave 0 |
| TRANS-01 | `mcp.run()` entry point uses `transport="streamable-http"` (source inspection) | unit | `pipenv run py -m pytest tests/test_server.py::test_entry_point_transport -x` | No — Wave 0 |
| TRANS-01 | No stdio references remain in module docstring or comments | unit | `pipenv run py -m pytest tests/test_server.py::test_no_stdio_references -x` | No — Wave 0 |
| TRANS-02 | `GET /health` returns 200 with correct JSON when both deps up | unit | `pipenv run py -m pytest tests/test_server.py::test_health_returns_200 -x` | No — Wave 0 |
| TRANS-02 | `GET /health` returns 503 when Ollama is unreachable | unit | `pipenv run py -m pytest tests/test_server.py::test_health_ollama_down -x` | No — Wave 0 |
| TRANS-02 | `GET /health` returns 503 when ChromaDB is unreachable | unit | `pipenv run py -m pytest tests/test_server.py::test_health_chromadb_down -x` | No — Wave 0 |

### Testing Approach for Health Endpoint

The health handler makes live calls to Ollama and ChromaDB. Tests must mock these, matching the existing test_server.py pattern.

Use `starlette.testclient.TestClient` with `mcp.streamable_http_app()` to exercise the health route without starting a real uvicorn server. TestClient is synchronous and available via the `starlette` transitive dep.

```python
# Pattern for health endpoint tests (no new deps required)
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

def test_health_returns_200():
    mock_ef = MagicMock(return_value=[[0.1] * 10])
    mock_ef_cls = MagicMock(return_value=mock_ef)
    mock_client = MagicMock()
    mock_client.get_collection.return_value = MagicMock()

    with patch("server.get_embedding_function", mock_ef_cls), \
         patch("server.chromadb.PersistentClient", return_value=mock_client):
        from server import mcp
        client = TestClient(mcp.streamable_http_app())
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ollama"] == "reachable"
    assert data["chromadb"] == "reachable"
```

**Note:** `TestClient` wraps the ASGI app in a synchronous interface, so no `asyncio.run()` is needed for health endpoint tests. This is the standard Starlette testing pattern.

### Sampling Rate

- **Per task commit:** `pipenv run py -m pytest tests/test_server.py -x -q`
- **Per wave merge:** `pipenv run py -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_server.py` — add 7 new test functions listed in the map above (file exists; add to existing file)

---

## Open Questions

1. **ChromaDB health check: new client vs. shared AppContext**
   - What we know: The health handler does not have a direct path to the `AppContext` created in the lifespan. `chromadb.PersistentClient` can create multiple clients pointing to the same path.
   - What's unclear: Whether the planner should thread AppContext access into the health handler (more complex) or use a fresh client per call (simpler, minor lock risk at high poll rates).
   - Recommendation: Use a fresh client per call for Phase 13. The only consumer of `/health` in this phase is a human operator checking manually; Docker Compose polling is Phase 15. Low enough frequency that lock contention is not a practical concern.

2. **`get_embedding_function` call in health handler**
   - What we know: `get_embedding_function` calls `resolve_ollama_url()` internally when `url=` is not passed. The health handler should mirror the startup check pattern.
   - What's unclear: Whether `resolve_ollama_url()` should be called explicitly in the handler (for consistency with `_check_ollama`) or left implicit.
   - Recommendation: Call `resolve_ollama_url()` explicitly then pass `url=` to `get_embedding_function`, matching the Phase 12 decision that `_resolve_ollama_url()` is the single source of truth.

---

## Sources

### Primary (HIGH confidence)

- FastMCP source: `/c/Users/wbjen/.virtualenvs/LDS_MCP-4gXzNxfn/Lib/site-packages/mcp/server/fastmcp/server.py` — constructor signature, `custom_route` decorator, `streamable_http_app()`, `_custom_starlette_routes` merge, DNS rebinding protection logic
- `server.py` (project source) — existing startup helpers, tool patterns, env var resolution pattern, AppContext shape
- `tests/test_server.py` (project source) — existing test patterns (asyncio.run, mock ctx, monkeypatch)
- `Pipfile` + `pipenv pip show` — confirmed installed packages and versions

### Secondary (MEDIUM confidence)

- Starlette TestClient: available via `starlette.testclient.TestClient` (confirmed importable from installed starlette 1.0.0)

### Tertiary (LOW confidence)

None — all findings verified from installed source code.

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 13 |
|-----------|-------------------|
| All Python commands use `pipenv run py` | Test commands must use `pipenv run py -m pytest`, not `pytest` directly |
| `scripts/db_schema_extractor.py` for DB access | Not applicable — health check uses ChromaDB client API, not SQLite directly |
| All logging to `sys.stderr` only | Health handler must log to `sys.stderr`; no `print()` to stdout |
| Project Structure Index must be updated when adding pipeline-related files | No new files added in this phase (changes land in `server.py` and `tests/test_server.py`) |
| Simplicity First / Minimal Impact | Health handler should reuse existing helpers where possible, not introduce new abstractions |
| Verify before marking complete | Run full test suite before closing phase |

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all packages verified from `pipenv pip show` against installed virtualenv
- Architecture: HIGH — `custom_route` decorator, constructor params, DNS rebinding behavior all verified from FastMCP 1.26.0 source code
- Pitfalls: HIGH — `sys.exit` pitfall derived directly from reading existing `_check_ollama` source; type pitfall derived from `Settings.port: int` in FastMCP source
- Test patterns: HIGH — TestClient verified importable; existing `asyncio.run` pattern confirmed working from 38-test suite

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (mcp package pinned to `*` in Pipfile — if version bumps, re-verify `custom_route` API)
