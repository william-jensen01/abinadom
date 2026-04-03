---
phase: 13-http-transport
plan: "02"
subsystem: mcp-server
tags: [health-endpoint, http-transport, starlette, tdd, trans-02]

dependency_graph:
  requires:
    - "13-01"  # HTTP transport foundation (streamable-http, MCP_HOST/MCP_PORT)
  provides:
    - "GET /health route with live Ollama and ChromaDB dependency checks"
  affects:
    - server.py
    - tests/test_server.py

tech_stack:
  added:
    - "starlette.requests.Request — request type for custom route handler"
    - "starlette.responses.JSONResponse — response type for /health payload"
  patterns:
    - "@mcp.custom_route decorator for non-MCP HTTP routes on FastMCP instance"
    - "TDD RED/GREEN: failing tests committed before implementation"
    - "Live dependency checks (not static): actual embedding call + PersistentClient per health request"

key_files:
  created: []
  modified:
    - path: server.py
      changes: "Add starlette imports; add @mcp.custom_route('/health') handler with live Ollama + ChromaDB checks"
    - path: tests/test_server.py
      changes: "Add # TRANS-02 section with 3 health endpoint tests using TestClient"

decisions:
  - "Health handler uses try/except + return 503 (not sys.exit) to avoid killing the process on dependency failure"
  - "Fresh chromadb.PersistentClient per health call — acceptable at health-check frequency (not high-traffic)"
  - "Live embedding call ef(['health']) used for Ollama check — confirms model loaded, not just daemon running"

metrics:
  duration_minutes: 6
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_modified: 2
---

# Phase 13 Plan 02: Health Endpoint Summary

**One-liner:** GET /health with live Ollama embedding call and ChromaDB PersistentClient check, returning 200/503 JSON payloads.

## What Was Built

Added a `/health` HTTP endpoint to the FastMCP server using the `@mcp.custom_route` decorator. The endpoint performs live dependency checks:

- **Ollama check**: Calls `get_embedding_function(url=ollama_url)` then invokes `ef(["health"])` — confirms the model is loaded and responsive, not just that the daemon is running.
- **ChromaDB check**: Creates a fresh `chromadb.PersistentClient(path=path)` and calls `get_collection(name=name)` for each of the 4 collection names — confirms collections exist and are accessible.

Both checks catch exceptions silently and set the corresponding status to `"unreachable"`, returning HTTP 503. When both succeed, the response is HTTP 200 `{"status": "ok", "ollama": "reachable", "chromadb": "reachable"}`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Add failing health endpoint tests | c0018b4 | tests/test_server.py |
| 2 (GREEN) | Implement /health endpoint | 451f44c | server.py |

## Test Results

- 42 pre-existing tests: all pass (unchanged)
- 3 new TRANS-02 tests: all pass
- **Total: 45/45 tests green**

## Verification

```
grep 'custom_route.*health' server.py
  → @mcp.custom_route("/health", methods=["GET"])

grep 'JSONResponse' server.py
  → from starlette.responses import JSONResponse
  → async def health_check(request: Request) -> JSONResponse:
  → return JSONResponse(payload, status_code=http_status)

grep -c 'sys.exit' server.py  → 6  (unchanged from pre-plan)
```

The `/health` handler contains no `sys.exit` calls — the single mention is in a comment.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- [x] `server.py` exists and contains `@mcp.custom_route("/health"`, `JSONResponse`, `ef(["health"])`, `client.get_collection(name=name)`
- [x] `tests/test_server.py` contains `test_health_returns_200`, `test_health_ollama_down`, `test_health_chromadb_down`, `# TRANS-02`
- [x] Commit `c0018b4` exists (TDD RED — failing tests)
- [x] Commit `451f44c` exists (GREEN — implementation)
- [x] All 45 `tests/test_server.py` tests pass
