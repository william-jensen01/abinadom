# Phase 9: Server Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 09-server-foundation
**Areas discussed:** MCP Framework, Server Entry Point, ChromaDB Path, Ollama Check Method

---

## MCP Framework

| Option | Description | Selected |
|--------|-------------|----------|
| mcp SDK + FastMCP class | Official SDK, decorator-based, minimal boilerplate, gets protocol updates | ✓ |
| mcp SDK low-level | More boilerplate, full protocol control | |
| fastmcp standalone | Third-party package, may lag behind official SDK | |

**User's choice:** `mcp` official SDK with built-in FastMCP class (`from mcp.server.fastmcp import FastMCP`)
**Notes:** User initially asked for pros/cons before deciding. Concern was that FastMCP might be "just for prototyping." Clarified that the standalone `fastmcp` package has that risk, but `mcp.server.fastmcp` is the official Anthropic-supported path — not a prototype shortcut.

---

## Server Entry Point

| Option | Description | Selected |
|--------|-------------|----------|
| server.py at project root | Top-level, conventional, easy for Claude Desktop config to reference | ✓ |
| scripts/mcp_server.py | Consistent with existing scripts/ pattern | |

**User's choice:** `server.py` at project root
**Notes:** No additional clarification needed.

---

## ChromaDB Path Resolution

| Option | Description | Selected |
|--------|-------------|----------|
| Env var: CHROMADB_PATH | Configurable externally, required for remote deployment | ✓ |
| CLI argument: --chromadb-path | Explicit flag, discoverable via --help | |
| Derive from __file__ | Zero config for local use, breaks if server/data separated | |

**User's choice:** Env var `CHROMADB_PATH` with `__file__`-relative default
**Notes:** User pushed back on the initial `__file__`-only recommendation, asking about future remote deployment (Milestone 3). Revised recommendation to env var with `__file__` default — works locally with zero config, overridable for remote. User confirmed: "I want the best universal option that works now and requires minimal changes in the future."

---

## Ollama Check Method

| Option | Description | Selected |
|--------|-------------|----------|
| HTTP ping only | Fast, confirms Ollama process running but not model loaded | |
| Live embedding call | Confirms Ollama running AND nomic-embed-text model loaded | ✓ |

**User's choice:** Live embedding call using `get_embedding_function()` from phase6_chromadb_loader.py
**Notes:** User asked for reasoning before deciding. Key insight: HTTP ping can pass while the model is missing, leaving CORE-02's actual failure mode unaddressed. Live call catches both conditions and reuses existing code.

---

## Claude's Discretion

- Exact error message wording for startup failures
- Ordering of startup sequence steps (Ollama check vs collection warmup)
- Whether to use a dedicated startup function or inline the checks

## Deferred Ideas

- Remote deployment / multi-device access — Milestone 3 (env var pattern supports this without code changes)
- HTTP transport — deferred to Milestone 3 per Out of Scope in REQUIREMENTS.md
