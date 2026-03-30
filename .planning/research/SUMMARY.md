# Project Research Summary

**Project:** LDS MCP — General Conference Talk Search via Claude Desktop
**Domain:** Local MCP server over an existing Python/ChromaDB pipeline (Windows, pipenv)
**Researched:** 2026-03-30
**Confidence:** HIGH

## Executive Summary

This project adds a read-only Model Context Protocol (MCP) server on top of an already-complete data pipeline. The pipeline has loaded 300,928 records across four ChromaDB collections (talks, paragraphs, citations, footnotes). The new work is a thin query layer — approximately 5–6 new files — that exposes two tools to Claude Desktop: `search` (semantic query with optional metadata filter) and `get_talk` (full ordered paragraphs by talk ID). There is no new data processing, no new database, and no write path. Expert MCP practice is to start with the minimum viable tool surface and iterate.

The recommended approach is to use the official `mcp[cli]` package (which includes FastMCP), STDIO transport, and `difflib`-based fuzzy normalization for speaker and metadata inputs — all implemented as a standalone module that reads from ChromaDB without touching pipeline code. The build order matters: ChromaDB client factory first, then normalizers, then individual tool handlers, then the entry point, then Claude Desktop wiring. This sequence isolates each concern and allows incremental testing before full integration.

The two highest-stakes risks are both silent failures: (1) any `print()` statement to stdout corrupts the JSON-RPC channel with no error message, and (2) a relative `CHROMADB_PATH` causes ChromaDB to silently create an empty database, returning zero results. Both are fully preventable with startup logging and absolute path resolution. A third critical risk is the Ollama embedding service not running at query time; a startup health check converts this from a mysterious mid-session failure into a clear early error.

---

## Key Findings

### Recommended Stack

The existing stack (Python 3.14.2, pipenv, ChromaDB, Ollama + nomic-embed-text) requires exactly one new dependency: `pipenv install "mcp[cli]"`. FastMCP, the highest-level MCP abstraction, is included inside the official `mcp` package — the standalone `fastmcp` PyPI package is redundant and should be avoided. All transitive dependencies (anyio, pydantic, httpx, uvicorn) are already present in Pipfile.lock via chromadb.

**Core technologies:**
- `mcp[cli]` 1.2.0+: MCP server SDK — FastMCP is at `mcp.server.fastmcp`; official SDK, not the deprecated standalone package
- ChromaDB PersistentClient: existing DB at `data/chromadb/`; server reads only, no schema changes
- Ollama (`nomic-embed-text`): embedding service for semantic search; must match model used at pipeline load time
- `difflib` (stdlib): fuzzy speaker/metadata normalization — no new dependency

**Critical version requirement:** Python 3.10+ (project runs 3.14.2 — compatible).

### Expected Features

The tool surface is intentionally minimal. Research strongly advises against adding browse/list/pagination tools — 5,838 talk records and 202,175 paragraph records cannot be navigated conversationally.

**Must have (table stakes):**
- `search` tool with semantic query, optional `where` metadata filter, and `collection` parameter — core utility
- `get_talk` tool returning full ordered paragraphs by talk ID — enables deep reading
- Readable prose text output, not raw JSON or internal pipeline fields
- `isError` handling so tool failures degrade gracefully without breaking the session
- Claude Desktop config wiring (Windows absolute paths throughout)

**Should have (differentiators):**
- Server-side fuzzy normalization of speaker names ("Nelson" → "Russell M. Nelson") and conference dates ("April 2020" → year=2020, season=April)
- Field stripping: expose content-relevant fields only; strip `extraction_timestamp`, `parse_pattern`, `text_raw`, `source_type` from all results
- Startup health check for Ollama availability with a clear user-facing error message
- Collection-aware result formatting (talks, paragraphs, citations, footnotes each have a distinct useful field set)

**Defer (v2+):**
- HTTP transport — only relevant for multi-client or remote scenarios
- Additional tools (browse, filter-by-topic, citation lookup) — validate `search` + `get_talk` cover actual usage first
- Pagination — not viable conversationally; defer or skip

### Architecture Approach

The MCP server is a new standalone module (`mcp_server.py` + `tools/` + `chroma_client.py`) that sits entirely outside the existing pipeline. It does not import from `extractors/`, `models/`, or `scripts/`. It reads `config/pipeline_config.py` for collection names only. This isolation means pipeline code is never at risk from MCP development. All 5–6 new files live at the project root alongside the existing codebase.

**Major components:**
1. `chroma_client.py` — shared ChromaDB PersistentClient factory; resolves absolute path at import time; warms up all 4 collections at startup
2. `tools/normalizers.py` — fuzzy speaker list (built from ChromaDB metadata at startup), conference date coercion, collection alias resolution; uses `difflib.get_close_matches()` only
3. `tools/search.py` — search tool handler; normalizes inputs, constructs `where` filter, queries ChromaDB, strips internal fields, returns text block
4. `tools/get_talk.py` — get_talk tool handler; fetches paragraphs by talk_id, sorts by `position` in Python, returns prose
5. `mcp_server.py` — FastMCP entry point; registers tools; all logging to `sys.stderr` only

**Data flow:** Claude Desktop → stdio/JSON-RPC → `mcp_server.py` → tool handler → normalizers → `chroma_client.py` → ChromaDB → formatted text response → Claude Desktop.

### Critical Pitfalls

1. **stdout pollution** — Any `print()` or library writing to stdout silently corrupts the JSON-RPC stream. Configure `logging` to `sys.stderr` before any other logic. Audit imports. Test with `python mcp_server.py` from a clean terminal before connecting Claude Desktop.

2. **Relative ChromaDB path** — `CHROMADB_PATH = "data/chromadb"` resolves from Claude Desktop's undefined working directory, not the project root. Silently creates an empty database; queries return zero results with no error. Fix: `Path(__file__).parent / "data/chromadb"` at startup. Detection: log `collection.count()` — if `conference_talks` shows 0, path is wrong.

3. **Pipenv virtualenv not activated** — `command` in `claude_desktop_config.json` must be the full absolute path to the pipenv-managed Python executable (`pipenv --venv` + `\Scripts\python.exe`). System `python` lacks all dependencies and exits immediately with `ModuleNotFoundError`.

4. **Ollama not running at query time** — Server appears healthy until first search call, then errors. Catch `OllamaEmbeddingFunction` connection errors in the search handler and return `"Error: Ollama is not running. Start Ollama and try again."` Add startup health check.

5. **Paragraph ordering in `get_talk`** — `collection.get(where={"talk_id": N})` returns arbitrary order. `position` field exists but ChromaDB has no `ORDER BY`. Fix: `sorted(results, key=lambda x: x['metadata']['position'])` after retrieval.

---

## Implications for Roadmap

Based on combined research, three phases cover everything needed for a working v2.0 MCP server.

### Phase 1: Foundation — ChromaDB Client and Normalizers
**Rationale:** All tool logic depends on a working ChromaDB connection and normalized inputs. Building these first means tools can be written and tested in isolation. This phase also enforces the critical constraint that paths are absolute from the start.
**Delivers:** `chroma_client.py` with startup warm-up and collection count logging; `tools/normalizers.py` with fuzzy speaker list, conference date coercion, and collection alias map
**Addresses:** Table-stakes dependency for all tools
**Avoids:** Pitfalls #2 (relative path), #3 (pipenv path), #9 (cold-start), #8 (speaker casing)

### Phase 2: Tool Implementation — search and get_talk
**Rationale:** With foundation in place, tool handlers can be written and tested independently before wiring to Claude Desktop. This is the bulk of the feature work.
**Delivers:** `tools/search.py` with metadata filtering, field stripping, token-budget defaults (n=5, cap 20); `tools/get_talk.py` with position-sorted paragraph output; `mcp_server.py` entry point with all logging to stderr
**Uses:** `mcp[cli]`, `chroma_client.py`, `tools/normalizers.py`
**Implements:** Both table-stakes tools plus all differentiator behaviors (fuzzy normalization, field stripping, collection-aware output)
**Avoids:** Pitfalls #1 (stdout), #5 (token overflow), #6 (verbose schema), #7 (topics encoding), #10 (paragraph order), #14 (tool name format), #15 (exceptions vs errors)

### Phase 3: Integration and Validation — Claude Desktop Wiring
**Rationale:** Claude Desktop config is done last because the server must be verified working standalone first. This phase also documents the Ollama startup requirement.
**Delivers:** Working `claude_desktop_config.json` with absolute paths; startup health check for Ollama; validated end-to-end query behavior; usage documentation for Ollama prerequisite
**Avoids:** Pitfalls #4 (Ollama down), #11 (Windows env vars), #12 (window vs quit), #13 (mcp missing from Pipfile)

### Phase Ordering Rationale

- Foundation-first prevents both silent failure modes (wrong Python, wrong ChromaDB path) from ever reaching tool development
- Normalizers built before tools means speaker/date logic is testable in isolation and reused by both tools without duplication
- Claude Desktop wired last means integration failures are diagnosed against a server already confirmed working at the CLI level
- Three phases maps cleanly to the build order identified in ARCHITECTURE.md: client factory → normalizers → tools → entry point → wiring

### Research Flags

Phases with standard, well-documented patterns (skip research-phase):
- **Phase 1:** ChromaDB PersistentClient and difflib are stdlib/well-documented; patterns are clear
- **Phase 2:** FastMCP tool registration is well-documented in official SDK; field stripping is straightforward Python
- **Phase 3:** Claude Desktop config format is fully specified; Windows path handling is a known pattern

No phase requires `/gsd:research-phase`. All patterns are established and sources are HIGH confidence.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Official MCP SDK docs confirm import path and FastMCP location; pipenv constraint verified against existing Pipfile.lock |
| Features | HIGH | Tool surface derived from actual ChromaDB schema and record counts; token budget math is concrete |
| Architecture | HIGH | Component boundaries and build order are unambiguous given existing codebase structure; no design decisions required |
| Pitfalls | HIGH | All pitfalls are based on known MCP/ChromaDB/Windows behaviors, not speculation; most have concrete detection steps |

**Overall confidence:** HIGH

### Gaps to Address

- **ChromaDB file lock behavior under concurrent access:** The pipeline + MCP server cannot run simultaneously due to SQLite exclusive lock. This is documented but the exact error message and recovery path have not been tested. Validate during Phase 1 and document in usage notes.
- **Ollama health check API:** The specific endpoint to poll for Ollama availability (`GET localhost:11434/api/tags` or similar) should be confirmed at implementation time; the pattern is clear but the exact call is not specified in research.
- **`mcp[cli]` version pinning:** Research says 1.2.0+ but does not identify a specific pinned version. Use `pipenv install "mcp[cli]"` and record the installed version in Pipfile for reproducibility.

---

## Sources

### Primary (HIGH confidence)
- Official MCP SDK — `mcp.server.fastmcp` import path, STDIO transport requirement, tool schema guidelines
- modelcontextprotocol.io quickstart — confirmed FastMCP is inside official `mcp` package
- ChromaDB docs — `PersistentClient`, `collection.get()`, `where` filter syntax, file lock behavior
- Existing project codebase (`config/pipeline_config.py`, `extractors/phase6_chromadb_loader.py`) — confirmed collection names, record counts, field schemas, embedding model

### Secondary (MEDIUM confidence)
- Claude Desktop documentation — config file location, subprocess spawning behavior, PATH limitations on Windows
- Community MCP server examples — stderr-only logging pattern, startup warm-up pattern

### Tertiary (LOW confidence)
- Inferred from Windows behavior — `%APPDATA%` not expanded in JSON config; full quit required to restart subprocess

---
*Research completed: 2026-03-30*
*Ready for roadmap: yes*
