# Phase 11: Claude Desktop Integration - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire Claude Desktop to the MCP server via `claude_desktop_config.json`, add env-var-driven configuration for `CHROMADB_PATH` and `OLLAMA_URL`, write concise tool descriptions with collection and workflow hints, and establish Claude's role via FastMCP `instructions` + a Claude Desktop Project system prompt. No new tools. No new infrastructure. This phase is the last step before the MCP server is fully operational end-to-end.

</domain>

<decisions>
## Implementation Decisions

### Claude Desktop Config (INTG-02)
- **D-01:** Python interpreter is referenced as the **absolute virtualenv path** (e.g., `C:\Users\wbjen\.virtualenvs\...\python.exe`). Pipenv and system Python are not used — absolute venv path is deterministic regardless of shell or PATH when Claude Desktop spawns the process.
- **D-02:** No `cwd` field in the config. `server.py` resolves ChromaDB path from `__file__` — working directory is irrelevant. Omitting `cwd` avoids unnecessary hardcoded user-specific paths.
- **D-03:** `CHROMADB_PATH` is set explicitly as an env var in `claude_desktop_config.json` (absolute path to `data/chromadb`). Establishes the env-var-driven configuration pattern for Milestone 3 remote deployment — remote configs just change the value.
- **D-04:** `OLLAMA_URL` is also set as an env var. Currently **hardcoded** in `extractors/phase6_chromadb_loader.py:321` and `server.py:97` — this phase must add env var support there. Local value: `http://localhost:11434`. This mirrors `CHROMADB_PATH` in intent: configurable per-deployment for Milestone 3.

### Env Var Pattern (Milestone 3 readiness)
- **D-05:** The env-var-driven config pattern is intentional forward-design for remote deployment. Milestone 3 will need `CHROMADB_PATH` pointing to a network-accessible ChromaDB and `OLLAMA_URL` pointing to a remote Ollama instance (or a different embedding provider). Both vars should be documented in a README or config template.
- **D-06:** Researcher should investigate how remote MCP servers are deployed and managed (transport, Python environment, hosting) to inform Milestone 3 planning. This is a research directive — no implementation needed in Phase 11.

### System Prompt / Role (INTG-03)
- **D-07:** Two-layer approach:
  1. **FastMCP `instructions` parameter** — Server-controlled, always present, no user action needed. Describes the server's purpose and the "search first" default behavior.
  2. **Claude Desktop Project** — Richer system prompt establishing Claude's adaptive discussion persona. Phase 11 delivers the prompt text; user sets it up manually in Claude Desktop.
- **D-08:** Claude's persona is **adaptive** — not a single fixed role. Claude reads conversation cues and shifts:
  - Research assistant when user wants to find specific content
  - Informed discussion partner when exploring ideas or doctrines
  - Study guide when user wants to understand teachings
  The instructions authorize all three modes explicitly.
- **D-09:** Search-first behavior is an **aggressive nudge**: "Prefer database results over training data. Default to training data only when the database has insufficient information." Not a hard rule — Claude falls back to training data gracefully when needed, but database is the strong default.

### Tool Descriptions (CORE-04, TOOL-01 through TOOL-05)
- **D-10:** `search` tool description adds a brief collection-hint line: guide Claude to use `"paragraphs"` for passage text, `"talks"` for talk discovery, `"citations"` for scripture references. Prevents defaulting to `paragraphs` for all query types. Kept to 1 line to honor token-minimal requirement.
- **D-11:** `get_talk` tool description adds a brief workflow hint: "Use `search` to find a `talk_id`, then call this to retrieve full text." Prevents blind calls without a known ID. Kept to 1 line.
- **D-12:** No other changes to tool parameter descriptions — they are already correct and concise from Phase 10.

### Claude's Discretion
- Exact wording of the FastMCP `instructions` string — should be concise, descriptive, and encode the adaptive-role + search-first behavior
- Exact wording of the Claude Desktop Project system prompt — researcher/planner may draft candidate text for review
- How to surface the `OLLAMA_URL` env var in `_check_ollama()` and `get_embedding_function()` — Claude picks the cleanest approach

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Server Implementation
- `server.py` — FastMCP server; `FastMCP(instructions=...)` is where the server-level instructions go; `_check_ollama()` has hardcoded `http://localhost:11434` that needs env var support
- `extractors/phase6_chromadb_loader.py:321` — hardcoded Ollama URL `http://localhost:11434/api/embeddings`; this is where `OLLAMA_URL` env var support must be added

### Configuration
- `config/pipeline_config.py` — `CHROMADB_COLLECTION_NAMES` keys are the valid `collection` values for the `search` tool
- `.planning/REQUIREMENTS.md` — INTG-02 and INTG-03 are the two requirements for this phase

### Prior Phase Context
- `.planning/phases/09-server-foundation/09-CONTEXT.md` — established patterns: FastMCP lifespan, AppContext, stderr logging, fail-fast startup
- `.planning/phases/10-tools-normalization/10-CONTEXT.md` — tool shape decisions (D-01 through D-15), especially token-minimal tool descriptions requirement

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `server.py:FastMCP` instantiation — add `instructions=` parameter here (no structural change)
- `server.py:_resolve_chromadb_path()` — pattern to follow for `_resolve_ollama_url()`: `os.environ.get("OLLAMA_URL", "http://localhost:11434")`
- Existing `search` and `get_talk` docstrings — update in place, no tool signature changes

### Established Patterns
- Env var override with a sensible default (`os.environ.get("KEY", default)`) — already used for `CHROMADB_PATH`; apply same pattern to `OLLAMA_URL`
- All startup errors exit via `SystemExit(1)` with actionable stderr messages
- Tool descriptions are docstrings on `@mcp.tool()` async functions

### Integration Points
- `claude_desktop_config.json` is a user-local file (not committed); planner should produce a template or instructions for generating it
- `extractors/phase6_chromadb_loader.py:get_embedding_function()` is called by both pipeline and server — any change to how Ollama URL is read must work for both callers

</code_context>

<specifics>
## Specific Ideas

- The two env vars (`CHROMADB_PATH`, `OLLAMA_URL`) should be documented together as "deployment configuration knobs" — a natural README section or config template that makes Milestone 3 onboarding clear
- Claude Desktop Project system prompt should explicitly name the 5,838-talk corpus scope so Claude knows what it's working with

</specifics>

<deferred>
## Deferred Ideas

- **Remote MCP server deployment** (Milestone 3) — transport change (stdio → HTTP/SSE or streamable-http), auth tokens, network-accessible ChromaDB (client-server mode vs embedded), remote Ollama. Flagged as a research directive for the Phase 11 researcher to investigate patterns without implementing.
- **MCP `prompts` capability** — named prompts (`/discuss`, `/find`, `/study`) for explicit mode switching. Additive complexity; the adaptive instructions approach handles it automatically. Consider for Milestone 3.

</deferred>

---

*Phase: 11-claude-desktop-integration*
*Context gathered: 2026-04-02*
