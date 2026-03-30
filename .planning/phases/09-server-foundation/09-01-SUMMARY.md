---
phase: 09-server-foundation
plan: 01
subsystem: infra
tags: [mcp, fastmcp, chromadb, ollama, stdio, python]

# Dependency graph
requires:
  - phase: v1.0-pipeline
    provides: "4 ChromaDB collections (talks, paragraphs, citations, footnotes) populated with 5,838 talks"
  - phase: v1.0-pipeline
    provides: "extractors/phase6_chromadb_loader.py with get_embedding_function() and get_chromadb_client()"
  - phase: v1.0-pipeline
    provides: "config/pipeline_config.py with CHROMADB_COLLECTION_NAMES"
provides:
  - "server.py: FastMCP server with lifespan startup validation (CORE-01, CORE-02, CORE-03, INTG-01)"
  - "mcp SDK installed in virtualenv (Pipfile updated)"
  - "tests/test_server.py: 5 unit tests covering startup validation contracts"
affects: [10-tools, 11-integration]

# Tech tracking
tech-stack:
  added: [mcp]
  patterns:
    - "FastMCP lifespan pattern via @asynccontextmanager for startup validation"
    - "_resolve_chromadb_path() uses Path(__file__).parent.resolve() for __file__-relative absolute paths"
    - "get_collection() not get_or_create_collection() as startup guard against silent empty DB"
    - "logging.basicConfig(stream=sys.stderr) before FastMCP init for stdio transport"

key-files:
  created:
    - server.py
    - tests/test_server.py
  modified:
    - Pipfile
    - Pipfile.lock
    - CLAUDE.md

key-decisions:
  - "Used FastMCP lifespan @asynccontextmanager rather than inline __main__ startup — integrates with server async loop"
  - "Startup order: path resolution → Ollama check → collection warmup (fail fast on cheapest checks first)"
  - "Broad Exception catch in _load_collections/_check_ollama — avoids brittle chromadb.errors.InvalidCollectionException import"

patterns-established:
  - "Pattern: AppContext dataclass carries all live resources for tool calls (client + collections dict)"
  - "Pattern: All error messages to sys.stderr, never bare print() — preserves MCP JSON-RPC stdout"
  - "Pattern: SystemExit(1) on any startup failure — gives Claude Desktop a clear failure signal"

requirements-completed: [CORE-01, CORE-02, CORE-03, INTG-01]

# Metrics
duration: 15min
completed: 2026-03-30
---

# Phase 9 Plan 01: Server Foundation Summary

**FastMCP server with lifespan startup validation: absolute ChromaDB path resolution, Ollama health check via live embedding, and 4-collection warmup guard using get_collection() not get_or_create_collection()**

## Performance

- **Duration:** 15 min
- **Started:** 2026-03-30T23:37:52Z
- **Completed:** 2026-03-30T23:52:05Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Installed `mcp` SDK (1.26.0) via pipenv and updated Pipfile.lock
- Created `server.py` with FastMCP lifespan startup validation satisfying CORE-01, CORE-02, CORE-03, INTG-01
- Created `tests/test_server.py` with 5 unit tests, all passing; full test suite has no new regressions
- Updated CLAUDE.md project structure index with server.py and test_server.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Install mcp SDK and create test stubs** - `b20a6ab` (chore)
2. **Task 2: Create server.py with startup validation** - `dc1845a` (feat)
3. **Task 3: Update CLAUDE.md project structure index** - `4251c60` (chore)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `server.py` — MCP server entry point; FastMCP with lifespan, _resolve_chromadb_path, _check_ollama, _load_collections
- `tests/test_server.py` — 5 unit tests for CORE-01 (path resolution + collection guard), CORE-02 (Ollama failure), CORE-03 (4-collection warmup)
- `Pipfile` — Added `mcp = "*"` under [packages]
- `Pipfile.lock` — Updated with mcp 1.26.0 dependency tree
- `CLAUDE.md` — Added ### Root section and tests/test_server.py entry

## Decisions Made

- FastMCP lifespan (@asynccontextmanager) chosen over inline __main__ startup because it runs inside the server's async loop and integrates cleanly with server lifecycle
- Startup order: path resolution first (free), Ollama check second (most likely failure at runtime, also warms model), collection warmup last — fail fastest on cheapest checks
- Broad `except Exception` catch in collection guard — avoids brittle dependency on `chromadb.errors.InvalidCollectionException` internal class name

## Deviations from Plan

None — plan executed exactly as written. The pre-existing test failure in `tests/test_phase1.py::TestTalkMetadataDDL` (3 tests) was confirmed to be pre-existing before Task 1 (DB file `core.52.db` not present in this worktree environment) and is out of scope.

## Issues Encountered

- `pipenv install mcp` hung in a loop after successful install — verified mcp was installed correctly via `pipenv run py -c "from mcp.server.fastmcp import FastMCP; print('ok')"` and confirmed Pipfile was updated before proceeding. The background command eventually completed.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `server.py` skeleton is ready for Phase 10 tool implementation
- `AppContext.collections` dict provides direct access to all 4 ChromaDB collections for tool handlers
- `AppContext.client` available for any additional collection queries in Phase 10
- Phase 10 can add `@mcp.tool()` decorated functions; no server.py changes needed beyond adding the tool decorators

## Self-Check: PASSED

- FOUND: server.py
- FOUND: tests/test_server.py
- FOUND: .planning/phases/09-server-foundation/09-01-SUMMARY.md
- FOUND commit b20a6ab: chore(09-01): install mcp SDK and create test stubs
- FOUND commit dc1845a: feat(09-01): create server.py with FastMCP startup validation
- FOUND commit 4251c60: chore(09-01): update CLAUDE.md project structure index

---
*Phase: 09-server-foundation*
*Completed: 2026-03-30*
