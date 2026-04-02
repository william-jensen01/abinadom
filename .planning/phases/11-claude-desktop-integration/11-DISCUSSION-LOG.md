# Phase 11: Claude Desktop Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-02
**Phase:** 11-claude-desktop-integration
**Areas discussed:** Config wiring, System prompt design, Tool descriptions

---

## Config Wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Absolute venv path | Deterministic — works regardless of shell or PATH | ✓ |
| pipenv run command | Requires pipenv on PATH when Claude Desktop spawns — less reliable | |
| System Python + PYTHONPATH | Fragile — depends on system Python having right packages | |

**User's choice:** Absolute venv path

---

| Option | Description | Selected |
|--------|-------------|----------|
| Omit cwd | Server uses __file__ resolution — cwd not needed | ✓ |
| Include cwd anyway | Cheap insurance and self-documenting | |

**User's choice:** Omit cwd — server.py uses __file__ for ChromaDB path resolution

---

| Option | Description | Selected |
|--------|-------------|----------|
| Set CHROMADB_PATH in local config | Establishes env-var-driven config pattern for Milestone 3 | ✓ |
| Omit for now | Keep local config minimal, add when needed | |

**User's choice:** Set CHROMADB_PATH explicitly — forward-design for remote deployment
**Notes:** User raised the Milestone 3 remote deployment concern proactively. Env var pattern established now to make Milestone 3 transition easier.

---

| Option | Description | Selected |
|--------|-------------|----------|
| OLLAMA_URL env var | Remote Ollama endpoint configurable per-deployment | ✓ |
| LOG_LEVEL env var | Control verbosity without code changes | |
| Neither — just CHROMADB_PATH | Don't add more than needed | |

**User's choice:** OLLAMA_URL (in addition to CHROMADB_PATH)
**Notes:** User identified OLLAMA_URL as the other deployment-variable knob. Currently hardcoded in phase6_chromadb_loader.py:321 — must be added as env var support.

**Additional context from discussion:** User asked about remote MCP server deployment patterns. Deferred as a research directive to Phase 11 researcher — investigate transport, Python environment, hosting patterns for Milestone 3.

---

## System Prompt Design

| Option | Description | Selected |
|--------|-------------|----------|
| FastMCP instructions + Claude Desktop project | Two-layer: server handles basics, project handles depth | ✓ |
| FastMCP instructions only | Self-contained but limited in depth | |
| Claude Desktop project only | Rich but requires manual setup, no server control | |

**User's choice:** Two-layer approach

---

| Option | Description | Selected |
|--------|-------------|----------|
| Adaptive persona | Claude reads conversation cues and shifts mode | ✓ |
| Informed discussion partner | Single fixed conversational role | |
| Research assistant | Utilitarian retrieval focus | |
| Gospel teacher | Instructive tone, higher synthesis risk | |

**User's choice:** Adaptive — user asked "can Claude determine what role to become?"
**Notes:** Rather than fixing a role, system prompt authorizes all modes and lets Claude adapt.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Aggressive nudge | "Prefer database, fall back to training when insufficient" | ✓ |
| Explicit rule | "Always search before answering, never use memory alone" | |
| Soft nudge only | "Prefer database results over memory" | |
| No rule | Trust Claude's natural tool use | |

**User's choice:** Aggressive nudge with graceful fallback
**Notes:** Database is the strong default. Training data is the fallback when the database has insufficient information, not a prohibition.

---

## Tool Descriptions

| Option | Description | Selected |
|--------|-------------|----------|
| Brief collection hints | 1-line guidance on which collection for which query type | ✓ |
| Keep minimal | No hints — Claude infers from parameter descriptions | |

**User's choice:** Add collection hints to search description

---

| Option | Description | Selected |
|--------|-------------|----------|
| Brief workflow hint | "Use search to find talk_id, then call this" | ✓ |
| Description only | Keep to what the tool does | |

**User's choice:** Add workflow hint to get_talk description

---

## Claude's Discretion

- Exact wording of FastMCP `instructions` string
- Exact wording of Claude Desktop Project system prompt
- How to surface `OLLAMA_URL` env var cleanly in both `server.py` and `extractors/phase6_chromadb_loader.py`

## Deferred Ideas

- Remote MCP server deployment patterns (Milestone 3) — transport, auth, hosted ChromaDB
- MCP `prompts` capability for explicit mode switching (`/discuss`, `/find`, `/study`)
