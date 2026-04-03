---
phase: 11-claude-desktop-integration
plan: "02"
subsystem: infra
tags: [claude-desktop, mcp, config, system-prompt, fastmcp]

# Dependency graph
requires:
  - phase: 11-01
    provides: OLLAMA_URL env var, FastMCP instructions attribute, tool docstring hints

provides:
  - Claude Desktop config template (config/claude_desktop_config.template.json)
  - Claude Desktop Project system prompt (config/SYSTEM_PROMPT.md)
  - Human-verified end-to-end connection between Claude Desktop and MCP server

affects:
  - Any future phase deploying or reconfiguring the MCP server for Claude Desktop

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Claude Desktop config uses absolute virtualenv Python path as command (no cwd field)"
    - "Two-layer prompt design: FastMCP instructions (server-level) + Project system prompt (user-level)"
    - "Adaptive persona system prompt: research assistant / discussion partner / study guide"
    - "Search-first behavior: MCP database is authoritative, training data is fallback"

key-files:
  created:
    - config/claude_desktop_config.template.json
    - config/SYSTEM_PROMPT.md
  modified: []

key-decisions:
  - "Config template uses absolute virtualenv Python path as command field per D-01; no cwd field per D-02"
  - "System prompt encodes adaptive persona (3 modes) and search-first behavior; richer than FastMCP instructions"
  - "Human verification approved: Claude Desktop connects to lds-scripture-index, uses search and get_talk proactively"

patterns-established:
  - "Pattern: Claude Desktop MCP config — command=virtualenv python.exe, args=[server.py], env block with CHROMADB_PATH and OLLAMA_URL"
  - "Pattern: Two-layer prompting — FastMCP mcp.instructions (tool-level context) + Project system prompt (conversational persona)"

requirements-completed: [INTG-02, INTG-03]

# Metrics
duration: 10min
completed: 2026-04-02
---

# Phase 11 Plan 02: Claude Desktop Integration Summary

**Claude Desktop config template and adaptive system prompt — end-to-end connection verified with proactive tool use and conversational synthesis**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-02T19:52:00Z
- **Completed:** 2026-04-02T20:00:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `config/claude_desktop_config.template.json` with correct MCP server config: absolute virtualenv Python path, no cwd field, CHROMADB_PATH and OLLAMA_URL env vars
- Created `config/SYSTEM_PROMPT.md` with adaptive persona (research assistant / discussion partner / study guide) and search-first behavior instruction
- Human-verified end-to-end: Claude Desktop connected to `lds-scripture-index` MCP server, used `search` and `get_talk` tools proactively, returned conversational synthesis

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Claude Desktop config template and system prompt** - `528a714` (feat)
2. **Task 2: Verify Claude Desktop connects and engages conversationally** - human-approved checkpoint (no code changes)

**Plan metadata:** (see final docs commit)

## Files Created/Modified

- `config/claude_desktop_config.template.json` - Ready-to-use Claude Desktop MCP server config with absolute paths and env vars
- `config/SYSTEM_PROMPT.md` - Claude Desktop Project system prompt: adaptive persona, search-first, conversational synthesis

## Decisions Made

- Config template uses absolute virtualenv Python path as `command` field (per D-01); no `cwd` field (per D-02). Env block includes `CHROMADB_PATH` and `OLLAMA_URL` (per D-03/D-04).
- System prompt is richer than FastMCP `mcp.instructions`: encodes three adaptive conversation modes and explicit search-first behavior. Two-layer design (per D-07) ensures both server and Claude Desktop Project are well-instrumented.
- No architectural deviations — all decisions locked in 11-CONTEXT.md were honored exactly.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

**User must copy config to Claude Desktop and paste system prompt into a Project.**

Steps performed by user (already done at checkpoint):
1. Copy `config/claude_desktop_config.template.json` content to `%APPDATA%\Claude\claude_desktop_config.json`
2. Fully quit and relaunch Claude Desktop
3. Confirm `lds-scripture-index` appears as connected with 2 tools in the hammer icon menu
4. Create a new Claude Desktop Project and paste `config/SYSTEM_PROMPT.md` as custom instructions

Verification result: Approved — Claude Desktop connected, tools used proactively, conversational synthesis confirmed.

## Next Phase Readiness

- Phase 11 (claude-desktop-integration) is complete. All three plans (11-01, 11-02) finished.
- v2.0 milestone is complete: Foundation (Phase 9) + Tools (Phase 10) + Integration (Phase 11) all done.
- No blockers. MCP server is ready for daily use.

---
*Phase: 11-claude-desktop-integration*
*Completed: 2026-04-02*
