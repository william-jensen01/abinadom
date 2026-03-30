# Phase 9: Server Foundation - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

The MCP server starts reliably: absolute ChromaDB path resolution, Ollama health check via live embedding, collection warmup, and stdio transport. All logging goes to stderr only. No tool logic in this phase — that is Phase 10.

</domain>

<decisions>
## Implementation Decisions

### MCP Framework
- **D-01:** Use `mcp` official SDK with the built-in FastMCP class (`from mcp.server.fastmcp import FastMCP`). Decorator-based API (`@mcp.tool()`), minimal boilerplate, official Anthropic support, gets protocol updates on SDK upgrades. The standalone `fastmcp` package is NOT used — it may lag behind the official SDK.

### Server Entry Point
- **D-02:** Server script lives at project root as `server.py`. Top-level, conventional for MCP servers, easy for Claude Desktop config to reference directly.

### ChromaDB Path Resolution (CORE-01)
- **D-03:** Use env var `CHROMADB_PATH` with a `__file__`-relative default:
  ```python
  DEFAULT_PATH = Path(__file__).parent.resolve() / "data" / "chromadb"
  path = Path(os.environ.get("CHROMADB_PATH", DEFAULT_PATH)).resolve()
  ```
  - **Local (Phase 9–11):** No env var needed — defaults to project-relative path, zero config, CORE-01 satisfied
  - **Remote (Milestone 3):** Set `CHROMADB_PATH` in environment to decouple server from data location — no code changes needed
  - Rationale: best universal option — works now with no config, extensible for remote deployment

### Ollama Health Check (CORE-02)
- **D-04:** Perform a **live embedding call** at startup using the existing `get_embedding_function()` from `extractors/phase6_chromadb_loader.py`. Do not use an HTTP ping — the ping only confirms Ollama is running, not that `nomic-embed-text` is loaded.
  - Catches: Ollama not running, model not pulled
  - Error message should be actionable: e.g., "Ollama unreachable" vs "nomic-embed-text model not found — run: `ollama pull nomic-embed-text`"
  - Side benefit: warms the model into memory before the first real query

### Collection Warmup (CORE-03)
- **D-05:** Load all 4 ChromaDB collections at startup before accepting tool calls. Use `CHROMADB_COLLECTION_NAMES` from `config/pipeline_config.py` — it already defines all 4 collection names.

### Stdio Transport (INTG-01)
- **D-06:** Run with `transport="stdio"`. All logging (startup messages, errors, health check results) goes to `stderr` only. `stdout` carries MCP protocol messages exclusively.

### Claude's Discretion
- Exact error message wording for startup failures (beyond the guidance above)
- Whether to warmup collections before or after the Ollama check (ordering within startup sequence)
- Whether to use a dedicated startup function or inline the checks

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Requirements
- `.planning/REQUIREMENTS.md` — CORE-01, CORE-02, CORE-03, INTG-01 are the four requirements for this phase

### Existing ChromaDB Patterns
- `extractors/phase6_chromadb_loader.py` — `get_embedding_function()` (reuse for Ollama health check), `get_chromadb_client()`, `CHROMADB_COLLECTION_NAMES` usage patterns

### Config
- `config/pipeline_config.py` — `CHROMADB_PATH`, `CHROMADB_COLLECTION_NAMES` — extend these for server use; do NOT duplicate constants

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_embedding_function()` in `extractors/phase6_chromadb_loader.py`: Returns `OllamaEmbeddingFunction` configured for `nomic-embed-text` — reuse directly for the startup health check
- `get_chromadb_client(path)` in `extractors/phase6_chromadb_loader.py`: Returns `chromadb.PersistentClient` — reuse for collection warmup
- `CHROMADB_COLLECTION_NAMES` in `config/pipeline_config.py`: Dict of all 4 collection name strings — use for warmup loop

### Established Patterns
- `CHROMADB_PATH = "data/chromadb"` in `pipeline_config.py` is relative today — the server must resolve to absolute (D-03), but the pipeline scripts are unaffected
- Logging: project uses `logging` module with DEBUG/INFO/WARNING/ERROR levels per `pipeline_config.py` conventions — server should follow the same pattern, outputting to `stderr`

### Integration Points
- `server.py` will import from `extractors/phase6_chromadb_loader.py` and `config/pipeline_config.py`
- No existing MCP code — entirely greenfield
- `tools/` directory contains SQLite-based utilities from an earlier approach; Phase 9 does not use them (ChromaDB is the data layer for the MCP server)

</code_context>

<specifics>
## Specific Ideas

- The user is thinking ahead to Milestone 3 (remote/multi-device deployment): the `CHROMADB_PATH` env var pattern (D-03) was chosen explicitly to support future server/data separation without code changes
- FastMCP chosen for minimal boilerplate, not as a prototype shortcut — it is the official supported path via the `mcp` SDK

</specifics>

<deferred>
## Deferred Ideas

- Remote deployment (Milestone 3): env var pattern supports this without code changes — no Phase 9 work needed
- HTTP transport: deferred to Milestone 3 per REQUIREMENTS.md Out of Scope

</deferred>

---

*Phase: 09-server-foundation*
*Context gathered: 2026-03-30*
