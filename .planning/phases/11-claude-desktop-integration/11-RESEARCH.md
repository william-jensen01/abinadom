# Phase 11: Claude Desktop Integration - Research

**Researched:** 2026-04-02
**Domain:** MCP server configuration, FastMCP `instructions` parameter, Claude Desktop Project system prompts
**Confidence:** HIGH

## Summary

Phase 11 is a configuration and light code phase — no new tools, no new infrastructure. It has four concrete deliverables: (1) add `OLLAMA_URL` env var support in two files, (2) update the two tool docstrings with collection/workflow hints, (3) set `FastMCP(instructions=...)` on the existing server, and (4) produce a `claude_desktop_config.json` template and a Claude Desktop Project system prompt for the user to apply manually.

The `mcp` SDK version 1.26.0 (already installed) confirms the `FastMCP.__init__` signature includes `instructions: str | None = None`. Claude Desktop surfaces this string as part of the system context for every conversation. The Claude Desktop Project custom instructions are a separate, richer layer set manually by the user in the claude.ai interface — they function as a persistent system prompt scoped to that Project.

The env var pattern for `OLLAMA_URL` is already established in the codebase: `os.environ.get("CHROMADB_PATH", default)` in `_resolve_chromadb_path()`. The same one-liner pattern applies to `_resolve_ollama_url()`. The hardcoded URL exists in exactly two places: `server.py:_check_ollama()` (indirect, via `get_embedding_function()`) and `extractors/phase6_chromadb_loader.py:get_embedding_function()` (direct, the `url=` argument to `OllamaEmbeddingFunction`).

**Primary recommendation:** Implement `_resolve_ollama_url()` in `server.py` following the `_resolve_chromadb_path()` pattern, pass its result into `get_embedding_function(url=...)`, update `get_embedding_function` to accept an optional `url` parameter with the env-var default as fallback. This keeps pipeline callers (which pass no argument) unaffected and gives the server env-var control.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Claude Desktop Config (INTG-02)**
- D-01: Python interpreter is referenced as the absolute virtualenv path (e.g., `C:\Users\wbjen\.virtualenvs\...\python.exe`). Pipenv and system Python are not used — absolute venv path is deterministic regardless of shell or PATH when Claude Desktop spawns the process.
- D-02: No `cwd` field in the config. `server.py` resolves ChromaDB path from `__file__` — working directory is irrelevant. Omitting `cwd` avoids unnecessary hardcoded user-specific paths.
- D-03: `CHROMADB_PATH` is set explicitly as an env var in `claude_desktop_config.json` (absolute path to `data/chromadb`). Establishes the env-var-driven configuration pattern for Milestone 3 remote deployment.
- D-04: `OLLAMA_URL` is also set as an env var. Currently hardcoded in `extractors/phase6_chromadb_loader.py:321` and `server.py:97` — this phase must add env var support there. Local value: `http://localhost:11434`.

**Env Var Pattern (Milestone 3 readiness)**
- D-05: The env-var-driven config pattern is intentional forward-design. `CHROMADB_PATH` and `OLLAMA_URL` should be documented together as deployment configuration knobs.
- D-06: Researcher should investigate how remote MCP servers are deployed and managed (transport, Python environment, hosting) — no implementation needed in Phase 11.

**System Prompt / Role (INTG-03)**
- D-07: Two-layer approach: (1) FastMCP `instructions` parameter — server-controlled, always present; (2) Claude Desktop Project — richer system prompt, user sets it manually.
- D-08: Claude's persona is adaptive — research assistant / informed discussion partner / study guide, shifting on conversation cues.
- D-09: Search-first behavior is an aggressive nudge: "Prefer database results over training data. Default to training data only when the database has insufficient information."

**Tool Descriptions (CORE-04, TOOL-01 through TOOL-05)**
- D-10: `search` tool description adds a 1-line collection hint: guide Claude to use `"paragraphs"` for passage text, `"talks"` for talk discovery, `"citations"` for scripture references. Prevents defaulting to `paragraphs` for all query types.
- D-11: `get_talk` tool description adds a 1-line workflow hint: "Use `search` to find a `talk_id`, then call this to retrieve full text." Prevents blind calls without a known ID.
- D-12: No other changes to tool parameter descriptions.

### Claude's Discretion
- Exact wording of the FastMCP `instructions` string — should be concise, descriptive, encode adaptive-role + search-first behavior.
- Exact wording of the Claude Desktop Project system prompt — researcher/planner may draft candidate text for review.
- How to surface the `OLLAMA_URL` env var in `_check_ollama()` and `get_embedding_function()` — Claude picks the cleanest approach.

### Deferred Ideas (OUT OF SCOPE)
- Remote MCP server deployment (Milestone 3) — transport change (stdio → HTTP/SSE or streamable-http), auth tokens, network-accessible ChromaDB, remote Ollama.
- MCP `prompts` capability — named prompts (`/discuss`, `/find`, `/study`) for explicit mode switching.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTG-02 | User can connect to the MCP server from Claude Desktop via `claude_desktop_config.json` with absolute virtualenv path | D-01 through D-05 locked; exact Python path confirmed: `C:\Users\wbjen\.virtualenvs\LDS_MCP-4gXzNxfn\Scripts\python.exe`; config template structure confirmed from official MCP docs |
| INTG-03 | Claude engages with LDS content conversationally via a system prompt that establishes its role as an informed discussion partner | FastMCP `instructions` parameter confirmed in installed mcp 1.26.0; Claude Desktop Project system prompt pattern confirmed; adaptive persona + search-first behavior patterns from Anthropic prompt engineering docs |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mcp (FastMCP) | 1.26.0 (installed) | MCP server framework; `FastMCP(instructions=...)` constructor | Already installed and in use; `instructions` param confirmed present |
| chromadb | installed | Vector store (no change this phase) | Existing |
| Python | `C:\Users\wbjen\.virtualenvs\LDS_MCP-4gXzNxfn\Scripts\python.exe` | Absolute venv path required by D-01 | Deterministic spawn by Claude Desktop |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| os.environ.get | stdlib | Read env vars with defaults | Used in `_resolve_chromadb_path()` — same pattern for OLLAMA_URL |
| OllamaEmbeddingFunction | chromadb-installed | Embedding calls; needs `url=` param | Modified to accept optional url argument |

**No new installs required.** All dependencies are already present.

---

## Architecture Patterns

### Pattern 1: Env Var with Sensible Default

Already established in the codebase. Apply identically to `OLLAMA_URL`:

```python
# Source: server.py _resolve_chromadb_path() — existing pattern
def _resolve_ollama_url() -> str:
    """
    Return the Ollama base URL.
    Override: Set OLLAMA_URL env var (e.g. http://remote-host:11434).
    Default: http://localhost:11434
    """
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")
```

**Key constraint:** `get_embedding_function()` in `extractors/phase6_chromadb_loader.py` is called by both the pipeline (`scripts/run_pipeline.py`) and the server. Pipeline callers pass no argument. The cleanest approach is to add an optional `url` parameter with the env-var lookup as its default:

```python
# Source: extractors/phase6_chromadb_loader.py:get_embedding_function — modified
def get_embedding_function(url: str | None = None) -> OllamaEmbeddingFunction:
    resolved_url = url or os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/embeddings"
    return OllamaEmbeddingFunction(
        model_name="nomic-embed-text",
        url=resolved_url,
    )
```

Pipeline callers that pass no argument get the env-var value (or localhost default) automatically. Server can pass an explicit value if needed, or also rely on the env var.

### Pattern 2: FastMCP `instructions` Parameter

**Confirmed in installed `mcp` 1.26.0:** `FastMCP.__init__` signature includes `instructions: str | None = None`.

The `instructions` string is surfaced by MCP clients (including Claude Desktop) as context about how to use the server — effectively injected near the system prompt. It should be:
- Concise (a few sentences to a short paragraph, not 500 words)
- Factual about server capabilities and workflow
- Encode search-first default behavior and collection selection guidance

```python
# Source: server.py — add instructions= to existing FastMCP instantiation
mcp = FastMCP(
    "lds-scripture-index",
    lifespan=lifespan,
    instructions=(
        "LDS General Conference corpus: 5,838 talks (1971–present) across 4 collections — "
        "talks (full-talk metadata), paragraphs (passage text), citations (scripture references), "
        "footnotes. "
        "Use `search` with collection='paragraphs' for passage text, 'talks' for talk discovery, "
        "'citations' for scripture references. "
        "Prefer database results over training data; fall back to training data only when the "
        "database has insufficient information. "
        "Use `search` to find a talk_id, then `get_talk` to retrieve full text."
    ),
)
```

### Pattern 3: `claude_desktop_config.json` Template

Config file location on Windows: `%APPDATA%\Claude\claude_desktop_config.json`
(resolves to `C:\Users\wbjen\AppData\Roaming\Claude\claude_desktop_config.json`)

**Exact structure confirmed from official MCP docs:**

```json
{
  "mcpServers": {
    "lds-scripture-index": {
      "command": "C:\\Users\\wbjen\\.virtualenvs\\LDS_MCP-4gXzNxfn\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\wbjen\\OneDrive\\Documents\\LDS MCP\\server.py"
      ],
      "env": {
        "CHROMADB_PATH": "C:\\Users\\wbjen\\OneDrive\\Documents\\LDS MCP\\data\\chromadb",
        "OLLAMA_URL": "http://localhost:11434"
      }
    }
  }
}
```

**Notes:**
- No `cwd` field (D-02 — locked).
- `CHROMADB_PATH` present per D-03.
- `OLLAMA_URL` present per D-04.
- Double backslashes required in JSON on Windows.
- Server key name `"lds-scripture-index"` matches the FastMCP server name.

### Pattern 4: Claude Desktop Project System Prompt

Claude Desktop Projects allow a persistent system prompt scoped to all conversations in that project. This is set manually by the user in the claude.ai desktop interface (Settings > Projects > New Project > Custom Instructions).

**Draft candidate text** (for planner to include as a deliverable for the user):

```
You are an informed discussion partner for LDS General Conference content — 
a corpus of 5,838 talks spanning 1971 to the present.

You have access to two tools: `search` (semantic search across talks, 
paragraphs, citations, and footnotes) and `get_talk` (retrieve a full talk 
by ID). Always search the database before drawing on your training knowledge 
about conference talks or doctrinal content. The database is authoritative; 
training data is a fallback.

Adapt your role to the conversation:
- When the user wants to find specific content: act as a research assistant — 
  search proactively, surface relevant talks, quote passages directly.
- When the user wants to explore ideas or doctrine: act as an informed 
  discussion partner — bring in talks that illuminate the topic, connect 
  themes across speakers and decades.
- When the user wants to understand a teaching: act as a study guide — 
  retrieve the talk, walk through its structure, highlight key passages.

Synthesize and discuss content. Do not return raw tool output — weave 
results into your response conversationally.
```

### Anti-Patterns to Avoid

- **Modifying `server.py` startup logic.** The startup sequence (path → Ollama → collections) is correct and complete. Phase 11 adds `instructions=` to the `FastMCP()` call only — no structural change to `_startup()`, `_check_ollama()`, or `_load_collections()`.
- **Changing tool return formats.** The 6-field shape from `_format_search_result` is already correct (Phase 10 decision D-01). Tool docstring changes are additive hints only.
- **Adding env var fallback in `server.py:_check_ollama()` directly.** The Ollama URL lives in `get_embedding_function()`. Add the env var there so pipeline callers also benefit. `_check_ollama()` calls `get_embedding_function()` — it picks up the change automatically.
- **Hard-coding paths in `claude_desktop_config.json` that the user doesn't own.** The template should clearly label which values the user must substitute.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Server capability hints | Custom `get_server_info` tool | FastMCP `instructions=` param | Already in MCP protocol; injected by Claude Desktop automatically |
| Persona management | Custom prompt scaffolding code | Claude Desktop Project custom instructions | Native Claude Desktop feature; no code required |
| Mode switching | MCP `prompts` capability with named prompts | Adaptive instructions in system prompt | Deferred to Milestone 3; adaptive approach handles it automatically |

---

## Common Pitfalls

### Pitfall 1: Claude Desktop Ignores Config After Edit
**What goes wrong:** Changes to `claude_desktop_config.json` have no effect.
**Why it happens:** Claude Desktop caches the config at startup. Must be fully quit (system tray right-click > Quit, not just closing the window) and relaunched.
**How to avoid:** Always full-quit via system tray after editing config.
**Warning signs:** MCP tool indicator does not appear in the input box bottom-right corner.

### Pitfall 2: JSON Syntax Error in Config Silently Blocks Server
**What goes wrong:** Server never connects; no helpful error shown to user.
**Why it happens:** Malformed JSON in `claude_desktop_config.json` causes the whole mcpServers block to be ignored.
**How to avoid:** Validate JSON before saving. On Windows, path backslashes must be doubled (`\\`).
**Warning signs:** No hammer/tool indicator in Claude Desktop UI.

### Pitfall 3: Wrong Python Executable
**What goes wrong:** `ModuleNotFoundError` for `mcp`, `chromadb`, etc. when Claude Desktop starts the server.
**Why it happens:** Using system Python or `python` from PATH rather than the absolute venv path. Claude Desktop spawns the process with a minimal environment — PATH is not reliable.
**How to avoid:** Always use the full absolute path: `C:\Users\wbjen\.virtualenvs\LDS_MCP-4gXzNxfn\Scripts\python.exe`.
**Verification:** Run that exact path manually from any directory with `server.py` as the argument to confirm it starts cleanly.

### Pitfall 4: `OllamaEmbeddingFunction` URL Must Include `/api/embeddings`
**What goes wrong:** `OLLAMA_URL` env var is set to `http://localhost:11434` but `OllamaEmbeddingFunction` receives `http://localhost:11434` instead of `http://localhost:11434/api/embeddings`.
**Why it happens:** The `url` param to `OllamaEmbeddingFunction` is the full API endpoint path, not the base URL. The env var stores the base URL.
**How to avoid:** `_resolve_ollama_url()` returns the base URL; the `/api/embeddings` suffix is appended inside `get_embedding_function()`.
**Example:** `url = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/embeddings"`

### Pitfall 5: `instructions=` String Too Long Wastes Tokens
**What goes wrong:** A 500-word instructions block is included in every session's context, consuming tokens on every request.
**Why it happens:** Over-documentation in the `instructions` parameter.
**How to avoid:** Per MCP blog guidance: keep instructions to a few focused sentences. The Claude Desktop Project system prompt is the right place for richer guidance.
**Warning signs:** Instructions longer than 3-5 sentences; repeating information already in tool docstrings.

### Pitfall 6: MCP Logs Are Separate from Server Stderr
**What goes wrong:** Debugging connection issues is difficult because the developer looks in the wrong place.
**Why it happens:** Claude Desktop writes MCP connection logs to `%APPDATA%\Claude\logs\mcp.log` and server stderr to `%APPDATA%\Claude\logs\mcp-server-lds-scripture-index.log`.
**How to avoid:** When debugging, check `mcp-server-lds-scripture-index.log` for Python exceptions and `mcp.log` for connection-level issues.

---

## Code Examples

### Adding `instructions=` to existing FastMCP instantiation

```python
# Source: server.py line ~246 — modify in place
mcp = FastMCP(
    "lds-scripture-index",
    lifespan=lifespan,
    instructions=(
        "LDS General Conference corpus: 5,838 talks (1971–present) across 4 collections — "
        "talks (full-talk metadata), paragraphs (passage text), citations (scripture references), "
        "footnotes. "
        "Use search with collection='paragraphs' for passage text, 'talks' for talk discovery, "
        "'citations' for scripture references. "
        "Prefer database results over training data; fall back to training data only when "
        "the database has insufficient information. "
        "Use search to find a talk_id, then get_talk to retrieve full text."
    ),
)
```

### Updated `search` tool docstring with collection hint (D-10)

```python
# Source: server.py — modify existing docstring; keep param descriptions unchanged
"""Search LDS General Conference content by meaning.

Use collection='paragraphs' for passage text, 'talks' for talk discovery,
'citations' for scripture references, 'footnotes' for footnote content.

Args:
    query: Natural language search query.
    speaker: Optional speaker name filter (substring match, e.g. "Holland").
    year: Optional conference year filter (e.g. 2020).
    season: Optional conference season filter ("April" or "October").
    collection: Collection to search — "talks", "paragraphs" (default), "citations", or "footnotes".
    limit: Number of results to return (default 5, max 20).
"""
```

### Updated `get_talk` tool docstring with workflow hint (D-11)

```python
# Source: server.py — modify existing docstring
"""Retrieve the full text of a General Conference talk by ID.

Use search to find a talk_id first, then call this to retrieve full text.

Args:
    talk_id: Talk identifier (e.g. "talk_8820" or "8820").
"""
```

### `get_embedding_function` with optional url parameter

```python
# Source: extractors/phase6_chromadb_loader.py — modify get_embedding_function
def get_embedding_function(url: str | None = None) -> OllamaEmbeddingFunction:
    """
    Return the OllamaEmbeddingFunction configured for nomic-embed-text.

    url: Optional override. Defaults to OLLAMA_URL env var, then http://localhost:11434.
    Pipeline callers (no argument) pick up the env var automatically.
    """
    base_url = url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
    return OllamaEmbeddingFunction(
        model_name="nomic-embed-text",
        url=base_url + "/api/embeddings",
    )
```

Note: `import os` is already present in `phase6_chromadb_loader.py` — verify before adding.

---

## Milestone 3 Research Finding (D-06 Directive)

> **Scope:** Research only. No implementation in Phase 11.

For Milestone 3 remote deployment, the current stdio transport must be replaced with **Streamable HTTP** (MCP protocol version 2025-03-26, supported in mcp SDK since v1.8.0, confirmed current in installed 1.26.0). SSE is available but deprecated as of that protocol version.

**Key facts:**
- FastMCP supports `mcp.run(transport="streamable-http")` with `stateless_http=True, json_response=True` for stateless production deployments.
- Python MCP servers can be deployed to Google Cloud Run, Cloudflare Workers (Python support added 2025), VPS with any WSGI/ASGI host, or AWS Lambda.
- Auth is handled via OAuth 2.1 (standard for remote MCP), not API keys.
- ChromaDB in client-server mode (separate process, HTTP API) replaces embedded PersistentClient for remote access.
- Ollama must be accessible from the hosting environment; managed GPU inference (Together AI, Replicate) is an alternative to self-hosted Ollama for remote deployment.

**Planning implication:** The `CHROMADB_PATH` and `OLLAMA_URL` env vars established in Phase 11 are the exact two knobs that Milestone 3 will change values on. No architectural changes to the server are needed — just new env var values pointing to remote services.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python (venv) | INTG-02 — subprocess spawn | ✓ | `C:\Users\wbjen\.virtualenvs\LDS_MCP-4gXzNxfn\Scripts\python.exe` | — |
| mcp SDK | FastMCP `instructions=` param | ✓ | 1.26.0 | — |
| Claude Desktop | INTG-02 — client connection | ✓ (assumed installed) | Latest | — |
| Ollama | Server startup check | ✓ (assumed running, existing requirement) | — | Startup exits with actionable error (CORE-02) |
| ChromaDB data | Server startup check | ✓ (pipeline complete) | — | Startup exits with actionable error (CORE-01) |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed via pipenv) |
| Config file | none (uses default discovery) |
| Quick run command | `pipenv run py -m pytest tests/test_server.py -q` |
| Full suite command | `pipenv run py -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTG-02 | `claude_desktop_config.json` template correctness | manual-only | n/a — requires Claude Desktop UI verification | n/a |
| INTG-02 | `OLLAMA_URL` env var read in `get_embedding_function()` | unit | `pipenv run py -m pytest tests/test_server.py -k ollama_url -x` | ❌ Wave 0 |
| INTG-02 | `get_embedding_function(url=...)` optional param backward compat | unit | `pipenv run py -m pytest tests/test_server.py -k embedding_function -x` | ❌ Wave 0 |
| INTG-03 | `FastMCP` instantiated with non-empty `instructions` string | unit | `pipenv run py -m pytest tests/test_server.py -k instructions -x` | ❌ Wave 0 |
| INTG-03 | Tool docstrings include collection/workflow hints | unit | `pipenv run py -m pytest tests/test_server.py -k docstring -x` | ❌ Wave 0 |
| INTG-03 | End-to-end Claude converses about LDS content | manual-only | n/a — requires live Claude Desktop + Ollama | n/a |

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/test_server.py -q`
- **Per wave merge:** `pipenv run py -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_server.py` — add `test_ollama_url_env_override`, `test_get_embedding_function_url_param`, `test_mcp_has_instructions`, `test_search_docstring_has_collection_hint`, `test_get_talk_docstring_has_workflow_hint`

*(All new tests go into the existing `tests/test_server.py` — no new file needed.)*

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSE transport for remote MCP | Streamable HTTP (MCP protocol 2025-03-26) | MCP SDK v1.8.0, 2025-05 | SSE deprecated for new projects; stdio unchanged for local |
| Hard-coded Ollama URL in loader | `OLLAMA_URL` env var | Phase 11 | Pipeline and server both read from environment |

**Deprecated/outdated:**
- HTTP+SSE transport for new remote servers: replaced by Streamable HTTP. SSE still works for backwards compat but should not be used for new Milestone 3 work.

---

## Open Questions

1. **Does `_check_ollama()` in `server.py` need to call `_resolve_ollama_url()` explicitly, or does it pick up the change automatically?**
   - What we know: `_check_ollama()` calls `get_embedding_function()` with no args, which will read `OLLAMA_URL` from env after the change to `phase6_chromadb_loader.py`.
   - What's unclear: Whether the server-side helper should also call `_resolve_ollama_url()` for logging/error-message clarity (e.g., printing the resolved URL in the error message on failure).
   - Recommendation: Add `_resolve_ollama_url()` to `server.py` for use in `_check_ollama()`'s error message only. It calls `get_embedding_function()` with no arg — the env var lookup happens in the loader. Consistent with the `_resolve_chromadb_path()` logging pattern.

2. **Does `os` need to be imported in `phase6_chromadb_loader.py`?**
   - What we know: The file already uses `Path`, `Any`, and other stdlib imports. `os` may or may not be present.
   - Recommendation: Verify with a quick read of the import block before writing the change. If absent, add `import os`.

---

## Sources

### Primary (HIGH confidence)
- Installed `mcp` SDK 1.26.0 — `FastMCP.__init__` signature verified via `help()` in the project virtualenv
- `server.py` (project file) — existing `_resolve_chromadb_path()` pattern, `_check_ollama()`, `FastMCP()` instantiation
- `extractors/phase6_chromadb_loader.py:312-322` — confirmed hardcoded `url="http://localhost:11434/api/embeddings"`
- [Model Context Protocol — Connect to local MCP servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers) — Windows config file location, JSON structure, env field, log file locations
- [FastMCP server constructor — gofastmcp.com](https://gofastmcp.com/servers/server) — `instructions` parameter description verified

### Secondary (MEDIUM confidence)
- [MCP blog — Using Server Instructions](http://blog.modelcontextprotocol.io/posts/2025-11-03-using-server-instructions/) — best practices: concise, factual, workflow-focused; not 500+ words
- [Anthropic prompt engineering docs](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/system-prompts) — "Give Claude a role" pattern; adaptive persona guidance

### Tertiary (LOW confidence)
- Remote deployment notes (Streamable HTTP, Cloud Run, Cloudflare): multiple sources agree on direction but Milestone 3 implementation not yet designed.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries confirmed installed; constructor signature verified from live venv
- Architecture: HIGH — patterns directly from existing codebase + confirmed official docs
- Pitfalls: HIGH — derived from confirmed Claude Desktop behavior and MCP protocol docs
- Remote deployment research (D-06): MEDIUM — multiple consistent sources, no implementation needed

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable domain; FastMCP API unlikely to change in 30 days)
