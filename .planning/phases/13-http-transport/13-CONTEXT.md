# Phase 13: HTTP Transport - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Swap the existing `stdio` transport for Streamable HTTP using FastMCP's native `transport="streamable-http"` support. Expose a `/health` endpoint with live dependency checks. Wire `MCP_HOST` and `MCP_PORT` env vars for 12-factor config.

This phase does NOT add authentication (Phase 14), containerization (Phase 15), or TLS/tunneling (Phase 16). The server runs as a plain HTTP process — no reverse proxy yet.

</domain>

<decisions>
## Implementation Decisions

### Transport

- **D-01:** Swap `mcp.run(transport="stdio")` to `mcp.run(transport="streamable-http")`. No uvicorn invocation needed — FastMCP handles it internally via `run_streamable_http_async`.
- **D-02:** MCP endpoint path stays at `/mcp` (FastMCP default for streamable-http). No `streamable_http_path` override.
- **D-03:** Remove all stdio references — update module docstring, entry-point comment, and any inline references to stdio transport. Clean break, no fallback.

### Host/Port Configuration

- **D-04:** Pass `MCP_HOST` and `MCP_PORT` env vars into the `FastMCP(...)` constructor at module initialization. Defaults: `host="0.0.0.0"`, `port=8000`.
- **D-05:** `0.0.0.0` default is intentional — Docker-ready from day one. FastMCP's auto DNS-rebinding protection (localhost-only) is not needed here since Caddy + Cloudflare Tunnel handle perimeter security in Phase 16.
- **D-06:** Only `MCP_HOST` and `MCP_PORT` are wired in this phase. All other env-var wiring (`CHROMADB_PATH`, `OLLAMA_URL`, secrets) is Phase 15's scope.

### Health Endpoint

- **D-07:** Add a `GET /health` route to the Starlette app that FastMCP exposes for streamable-http. Returns 200 with a JSON payload confirming both Ollama and ChromaDB are reachable.
- **D-08:** Health payload:
  ```json
  {
    "status": "ok",
    "ollama": "reachable",
    "chromadb": "reachable"
  }
  ```
- **D-09:** `/health` performs live checks — not a static response. Ollama check: attempt an embedding call (same as startup `_check_ollama`). ChromaDB check: confirm the client can connect and collections exist (reuse startup guard logic without full count validation).
- **D-10:** If either dependency is down at `/health` call time, return 503 (not 200) with the failing dependency flagged. Exact error shape: Claude's discretion.

### Claude's Discretion

- How `/health` is mounted on the Starlette app (custom_routes parameter vs `streamable_http_app()` patching vs a separate ASGI mount)
- Whether `_check_ollama` and `_check_chromadb` logic is refactored into a shared helper or called inline in the health handler
- 503 error shape when a dependency fails

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### MCP Transport
- `server.py` — Existing server; all transport changes land here

### Requirements
- `.planning/REQUIREMENTS.md` §TRANS-01, TRANS-02 — Transport and health requirements for this phase

### Roadmap
- `.planning/ROADMAP.md` §Phase 13 — Success criteria (3 items: MCP client works over HTTP, /health returns 200, stdio removed)

No external specs — FastMCP 1.26.0 is already installed and its `transport="streamable-http"` API is confirmed working. No docs URL needed.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_check_ollama()` in `server.py` — existing Ollama health check via live embedding call; reusable or refactorable for the `/health` handler
- `_load_collections()` in `server.py` — existing ChromaDB validation; can inform the ChromaDB reachability check in `/health`
- `AppContext` dataclass — carries live `client` and `collections` references that `/health` can use without re-initializing

### Established Patterns
- Env var resolution via `os.environ.get("VAR", default)` — used for `CHROMADB_PATH` and `OLLAMA_URL`; same pattern for `MCP_HOST` / `MCP_PORT`
- `FastMCP(name, lifespan=lifespan, instructions=...)` constructor pattern — add `host=` and `port=` parameters here
- All logging to `sys.stderr` only — preserve in health handler

### Integration Points
- `mcp = FastMCP(...)` at module level — `host` and `port` params added here
- `if __name__ == "__main__": mcp.run(transport="stdio")` — change to `transport="streamable-http"`, remove stdio references
- FastMCP's internal Starlette app (accessible via `mcp.streamable_http_app()`) — where `/health` route is registered

</code_context>

<specifics>
## Specific Ideas

- The `/health` endpoint should function as a Docker Compose `healthcheck` target in Phase 15 — keep it fast and dependency-accurate
- Collection counts are NOT needed in the health payload (user confirmed) — just reachability signals

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 13-http-transport*
*Context gathered: 2026-04-03*
