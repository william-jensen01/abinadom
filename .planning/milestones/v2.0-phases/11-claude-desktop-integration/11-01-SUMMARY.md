---
phase: 11-claude-desktop-integration
plan: "01"
subsystem: infra
tags: [mcp, fastmcp, chromadb, ollama, env-var, docstrings]

# Dependency graph
requires:
  - phase: 10-tools-normalization
    provides: search and get_talk MCP tools with speaker/year/season filters

provides:
  - OLLAMA_URL env var support in get_embedding_function (backward-compatible)
  - _resolve_ollama_url() helper in server.py
  - FastMCP instructions string (corpus description, collection hints, search-first behavior)
  - search tool docstring with collection selection guidance
  - get_talk tool docstring with search-first workflow hint

affects:
  - 11-claude-desktop-integration (phase 11-02 Claude Desktop config wiring)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "OLLAMA_URL env var read at function call time via os.environ.get with localhost fallback"
    - "FastMCP instructions= param for system-level corpus description"
    - "Tool docstrings as lightweight usage guidance for Claude"

key-files:
  created: []
  modified:
    - extractors/phase6_chromadb_loader.py
    - server.py
    - tests/test_server.py

key-decisions:
  - "mcp.instructions is a direct attribute on FastMCP, not mcp.settings.instructions — fixed test accordingly"
  - "OLLAMA_URL env var read inside get_embedding_function (not at import time) so monkeypatching works correctly in tests"
  - "base_url + '/api/embeddings' suffix pattern: OLLAMA_URL is a base URL (http://host:port), not the full embeddings path"

patterns-established:
  - "Env var pattern: os.environ.get('VAR', 'default') inside function body (not module-level) for testability"
  - "FastMCP instructions describe corpus + collection routing + preferred workflow"

requirements-completed:
  - INTG-02
  - INTG-03

# Metrics
duration: 5min
completed: "2026-04-02"
---

# Phase 11 Plan 01: Claude Desktop Integration — Env Var and Instructions Summary

**OLLAMA_URL env var wired into get_embedding_function with localhost fallback, FastMCP instructions describing the 5,838-talk corpus added, and tool docstrings updated with collection selection and search-first workflow hints**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-02T19:45:22Z
- **Completed:** 2026-04-02T19:50:09Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `get_embedding_function` now accepts optional `url` param and reads `OLLAMA_URL` env var — pipeline callers (no args) unaffected
- FastMCP server has instructions string: corpus size, collection routing, search-first behavior
- `search` docstring guides Claude to correct collection per query type (paragraphs/talks/citations/footnotes)
- `get_talk` docstring adds workflow hint: use search to find talk_id first
- 6 new tests covering all INTG-02/INTG-03 behaviors — 436/436 full suite green

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Wave 0 failing tests (TDD RED)** - `234c278` (test)
2. **Task 2: Implement env var, instructions, docstrings (TDD GREEN)** - `a8f205d` (feat)

_Note: TDD tasks have two commits — RED (failing tests) then GREEN (implementation)_

## Files Created/Modified

- `extractors/phase6_chromadb_loader.py` - Added `import os`; updated `get_embedding_function` signature to `(url: str | None = None)` with OLLAMA_URL env var support
- `server.py` - Added `_resolve_ollama_url()` helper; updated `_check_ollama` error message; added FastMCP `instructions=` param; updated `search` and `get_talk` docstrings
- `tests/test_server.py` - Added 6 new tests: `test_ollama_url_env_override`, `test_get_embedding_function_url_param`, `test_get_embedding_function_default_url`, `test_mcp_has_instructions`, `test_search_docstring_has_collection_hint`, `test_get_talk_docstring_has_workflow_hint`

## Decisions Made

- `mcp.instructions` is the correct attribute path on FastMCP (not `mcp.settings.instructions`). The test was adjusted accordingly during the GREEN phase — this is a deviation tracked below.
- OLLAMA_URL env var represents the base URL (`http://host:port`), not the full embeddings path. The `/api/embeddings` suffix is always appended inside `get_embedding_function`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_mcp_has_instructions to use mcp.instructions not mcp.settings.instructions**
- **Found during:** Task 2 (GREEN phase — running new tests after implementing FastMCP instructions)
- **Issue:** Plan specified `mcp.settings.instructions` but FastMCP stores the instructions string directly on `mcp.instructions`. The `Settings` pydantic model has no `instructions` field.
- **Fix:** Updated test assertion from `mcp.settings.instructions` to `mcp.instructions`
- **Files modified:** tests/test_server.py
- **Verification:** `test_mcp_has_instructions` passes; `mcp.instructions` confirmed via REPL inspection
- **Committed in:** a8f205d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test vs. actual FastMCP API)
**Impact on plan:** Necessary correction to test — the production instruction string was correctly implemented. No scope change.

## Issues Encountered

- FastMCP attribute path for instructions (`mcp.instructions` vs `mcp.settings.instructions`) — resolved by inspecting the live FastMCP object in the REPL.

## User Setup Required

None - no external service configuration required. OLLAMA_URL env var is optional; defaults to `http://localhost:11434`.

## Next Phase Readiness

- OLLAMA_URL env var ready for Claude Desktop `claude_desktop_config.json` env block
- FastMCP instructions in place for conversational Claude behavior
- All tools have collection and workflow hints in docstrings
- Phase 11-02 can wire the Claude Desktop config file directly

---
*Phase: 11-claude-desktop-integration*
*Completed: 2026-04-02*
