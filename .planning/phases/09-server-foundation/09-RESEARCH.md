# Phase 9: Server Foundation - Research

**Researched:** 2026-03-30
**Domain:** MCP Python SDK (FastMCP), ChromaDB startup validation, Ollama health check, stdio transport logging
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Use `mcp` official SDK with `from mcp.server.fastmcp import FastMCP`. The standalone `fastmcp` package is NOT used.
- **D-02:** Server script lives at project root as `server.py`.
- **D-03:** ChromaDB path resolved with `__file__`-relative default + `CHROMADB_PATH` env var override:
  ```python
  DEFAULT_PATH = Path(__file__).parent.resolve() / "data" / "chromadb"
  path = Path(os.environ.get("CHROMADB_PATH", DEFAULT_PATH)).resolve()
  ```
- **D-04:** Ollama health check via live embedding call using `get_embedding_function()` from `extractors/phase6_chromadb_loader.py`. Not an HTTP ping.
- **D-05:** Load all 4 ChromaDB collections at startup using `CHROMADB_COLLECTION_NAMES` from `config/pipeline_config.py`.
- **D-06:** Run with `transport="stdio"`. All logging to `stderr` only. `stdout` for MCP protocol only.

### Claude's Discretion

- Exact error message wording for startup failures (beyond guidance in CONTEXT.md)
- Whether to warmup collections before or after the Ollama check (ordering within startup sequence)
- Whether to use a dedicated startup function or inline the checks

### Deferred Ideas (OUT OF SCOPE)

- Remote deployment (Milestone 3): env var pattern supports this without code changes
- HTTP transport: deferred to Milestone 3
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | Server resolves ChromaDB path to absolute at startup (prevents silent empty-DB creation when Claude Desktop spawns with unknown working directory) | D-03 pattern verified; ChromaDB confirmed to silently create empty DB at any path — `get_collection()` check after path resolution is the guard |
| CORE-02 | Server performs Ollama health check at startup and fails fast with a clear error if unreachable | `get_embedding_function()` already returns `OllamaEmbeddingFunction` — wrapping the call in try/except captures both "Ollama not running" and "model not pulled" cases |
| CORE-03 | Server warms up all 4 ChromaDB collections at startup before accepting tool calls | FastMCP lifespan pattern via `@asynccontextmanager` is the correct mechanism — collections loaded in lifespan, stored in context object available to all tools |
| INTG-01 | MCP server runs via stdio transport; all logging goes to stderr only (no stdout pollution) | `logging.basicConfig(stream=sys.stderr)` + `mcp.run(transport="stdio")` — confirmed by official MCP docs |
</phase_requirements>

---

## Summary

Phase 9 builds `server.py` at the project root: a FastMCP server that validates its environment before accepting any tool calls. The MCP Python SDK 1.26.0 (latest as of 2026-03-30) ships `FastMCP` in `mcp.server.fastmcp` and is not yet installed in the project — it must be added to Pipfile. The SDK requires Python 3.10+; the project runs Python 3.

The three startup concerns (path resolution, Ollama health, collection warmup) map directly to the FastMCP lifespan pattern: an `@asynccontextmanager` function that runs before the first tool call and stores live resources in a context object. Startup failures should call `sys.exit(1)` with a human-readable message to `sys.stderr` — FastMCP does not yet expose a "fail before accepting connections" hook, so the lifespan must raise `SystemExit` explicitly.

The biggest implementation pitfall is the ChromaDB silent-creation trap: `chromadb.PersistentClient(path=X)` creates an empty database at any path including nonexistent ones (verified locally). The guard is `client.get_collection(name)` after path resolution — if collections do not exist, fail fast with a clear message rather than serving queries against an empty DB.

**Primary recommendation:** Use `@asynccontextmanager` lifespan with `sys.exit(1)` on any startup failure. Check collections via `get_collection()` (not `get_or_create_collection()`). Log everything to `stderr` via `logging.basicConfig(stream=sys.stderr)` before FastMCP init.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mcp | 1.26.0 | MCP protocol + FastMCP class | Official Anthropic SDK — D-01 locked |
| chromadb | 1.5.5 (already installed) | PersistentClient for collection access | Already in project |
| ollama (pip) | installed | Ollama Python client | Already in project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib.Path | stdlib | Absolute path resolution | D-03 pattern |
| logging | stdlib | Structured logging to stderr | INTG-01 |
| sys | stdlib | `sys.stderr`, `sys.exit(1)` | Startup failure signaling |
| os | stdlib | `os.environ.get("CHROMADB_PATH", ...)` | Env var override |
| contextlib.asynccontextmanager | stdlib | FastMCP lifespan hook | Collection warmup |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastMCP lifespan | Inline startup in `__main__` | Inline approach runs before MCP loop is active — lifespan is cleaner, integrates with server lifecycle |
| `get_collection()` guard | Count check after `get_or_create_collection()` | `get_or_create_collection()` silently creates empty DB, defeating CORE-01 |
| `logging.basicConfig(stream=sys.stderr)` | `print(..., file=sys.stderr)` | `logging` is project convention per pipeline_config.py; `print` has no level/timestamp control |

**Installation:**
```bash
pipenv install mcp
```

**Version verification:** `mcp` 1.26.0 confirmed via `pip index versions mcp` on 2026-03-30.

---

## Architecture Patterns

### Recommended Project Structure

```
server.py                  # FastMCP entry point (project root, D-02)
config/
└── pipeline_config.py     # CHROMADB_PATH, CHROMADB_COLLECTION_NAMES (reuse, do not duplicate)
extractors/
└── phase6_chromadb_loader.py  # get_embedding_function(), get_chromadb_client() (reuse)
```

No new directories needed for Phase 9. `server.py` is the only new file.

### Pattern 1: FastMCP Lifespan for Startup Validation

**What:** An `@asynccontextmanager` passed to `FastMCP(lifespan=...)` that runs before any tool call is accepted. Startup failures raise `SystemExit` here; the yielded object carries live resources (client, collections) for tools.

**When to use:** Any startup validation or resource initialization that must complete before tools are available.

**Example (official SDK pattern):**
```python
# Source: https://modelcontextprotocol.io/docs/develop/build-server
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from dataclasses import dataclass
import sys

@dataclass
class AppContext:
    client: chromadb.ClientAPI
    collections: dict  # key -> chromadb.Collection

@asynccontextmanager
async def lifespan(server: FastMCP):
    # All startup validation here -- runs before first tool call
    ctx = _startup()  # raises SystemExit on failure
    try:
        yield ctx
    finally:
        pass  # no cleanup needed for read-only ChromaDB

mcp = FastMCP("lds-scripture-index", lifespan=lifespan)
```

### Pattern 2: ChromaDB Guard — get_collection(), not get_or_create_collection()

**What:** Use `client.get_collection(name)` for startup validation. This raises `chromadb.errors.InvalidCollectionException` if the collection does not exist. `get_or_create_collection()` silently creates an empty collection — the wrong behavior for startup validation.

**When to use:** Any code path that is asserting data exists (startup), as opposed to code that creates data (pipeline).

**Example:**
```python
# Source: local verification against chromadb 1.5.5
try:
    col = client.get_collection(name=CHROMADB_COLLECTION_NAMES["talks"])
    count = col.count()
    if count == 0:
        print(
            f"ERROR: Collection '{CHROMADB_COLLECTION_NAMES['talks']}' is empty. "
            "Run the pipeline first.",
            file=sys.stderr
        )
        sys.exit(1)
except Exception as e:
    print(f"ERROR: ChromaDB collection not found: {e}", file=sys.stderr)
    sys.exit(1)
```

### Pattern 3: Ollama Health Check via Live Embedding

**What:** Call `get_embedding_function()` and invoke it with a test string. This exercises the full path: Ollama running + `nomic-embed-text` loaded. An HTTP ping to port 11434 would only confirm the process is up — not that the model is ready.

**When to use:** D-04 is locked — use this pattern, not a ping.

**Example:**
```python
# Source: extractors/phase6_chromadb_loader.py + D-04 decision
from extractors.phase6_chromadb_loader import get_embedding_function

def _check_ollama():
    try:
        ef = get_embedding_function()
        ef(["health check"])  # live embedding call
    except Exception as e:
        err = str(e)
        if "nomic-embed-text" in err or "model" in err.lower():
            print(
                "ERROR: Ollama model not available. "
                "Run: ollama pull nomic-embed-text",
                file=sys.stderr
            )
        else:
            print(
                f"ERROR: Ollama unreachable at http://localhost:11434. "
                "Start Ollama and retry.",
                file=sys.stderr
            )
        sys.exit(1)
```

### Pattern 4: Logging Configuration for stdio Transport

**What:** Configure Python `logging` to write to `sys.stderr` before instantiating FastMCP. `logging.basicConfig()` defaults to `sys.stderr` for `StreamHandler` — but be explicit.

**When to use:** INTG-01 — all log output must go to stderr. Any `print()` call without `file=sys.stderr` corrupts the MCP protocol.

**Example:**
```python
# Source: https://modelcontextprotocol.io/docs/develop/build-server (logging section)
import logging, sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)
```

### Recommended Startup Sequence

Based on D-05 (collect warmup), D-04 (Ollama check), and Claude's Discretion on ordering:

1. Configure logging to `sys.stderr`
2. Resolve and validate ChromaDB path (CORE-01) — fail fast if path resolves but collections absent
3. Check Ollama via live embedding call (CORE-02) — side benefit: warms model into memory
4. Load all 4 collections using `get_collection()` (CORE-03)
5. Yield `AppContext` to tools

Rationale for this order: path validation is free (no network). Ollama check is the most likely failure mode in practice and also warms the model — do it before collection warmup to fail faster if Ollama is down.

### Anti-Patterns to Avoid

- **`get_or_create_collection()` at startup:** Silently creates empty collections. Verified locally — `PersistentClient` creates both the directory and `chroma.sqlite3` at any path, including nonexistent ones.
- **Writing to stdout:** Any `print()` without `file=sys.stderr` corrupts JSON-RPC messages. This includes stack traces from unhandled exceptions — wrap `lifespan` in a broad try/except that prints to stderr and calls `sys.exit(1)`.
- **Importing `CHROMADB_PATH` from `pipeline_config.py` directly:** The value there is `"data/chromadb"` (relative string). The server must resolve it to absolute using `Path(__file__).parent.resolve()` per D-03. Never pass the raw string to `PersistentClient`.
- **Duplicating constants:** Do not re-define `CHROMADB_COLLECTION_NAMES` in `server.py`. Import from `config/pipeline_config.py`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol (JSON-RPC over stdio) | Custom message framing, tool dispatch | `mcp.server.fastmcp.FastMCP` | Protocol is complex; tool schema generation, error codes, capability negotiation all handled |
| ChromaDB client | Direct SQLite access to `chroma.sqlite3` | `chromadb.PersistentClient` | Internal schema changes between versions; public API is stable |
| Embedding function construction | `OllamaEmbeddingFunction(model_name=..., url=...)` inline in server.py | `get_embedding_function()` from phase6_chromadb_loader.py | Already parameterized correctly; keeps model name and URL in one place |
| Collection name strings | Hardcoded `"conference_talks"` etc. in server.py | `CHROMADB_COLLECTION_NAMES` from `config/pipeline_config.py` | Single source of truth; prevents drift if names ever change |

**Key insight:** `server.py` is a thin orchestrator — it imports from existing extractors and config, not a place to reimplement anything already built.

---

## Common Pitfalls

### Pitfall 1: Silent Empty Database Creation (CORE-01 Risk)

**What goes wrong:** Server starts, collections show 0 records, all semantic queries return empty results. No error is raised.

**Why it happens:** `chromadb.PersistentClient(path=X)` creates a new SQLite database at any path, including a wrong one. Claude Desktop spawns MCP servers from an unknown working directory — a relative path like `"data/chromadb"` resolves relative to wherever Claude Desktop's process is rooted, not the project root.

**How to avoid:** Always resolve to absolute using `Path(__file__).parent.resolve()`. After `PersistentClient`, call `client.get_collection()` (not `get_or_create_collection()`) for at least the `talks` collection and check `count() > 0`.

**Warning signs:** All 4 collection UUIDs in `data/chromadb/` are from the pipeline run. If server creates a new `chroma.sqlite3` somewhere else, queries return nothing.

### Pitfall 2: Ollama Health Check That Doesn't Catch Missing Model

**What goes wrong:** Ollama is running but `nomic-embed-text` has not been pulled. An HTTP ping to port 11434 returns 200 OK. Server starts successfully. First real tool call fails with a cryptic HTTP 404 from Ollama.

**Why it happens:** Ollama's process is up but the model isn't loaded. A ping only confirms the daemon is alive.

**How to avoid:** D-04 is correct — use a live embedding call. `OllamaEmbeddingFunction.__call__(["test"])` will raise if the model is missing. Distinguish "unreachable" from "model not found" in the error message by inspecting the exception string.

**Warning signs:** Exception from `OllamaEmbeddingFunction` contains "404" or "model" — this is model-not-pulled, not Ollama-down.

### Pitfall 3: stdout Contamination

**What goes wrong:** MCP client (Claude Desktop) receives JSON-RPC parse errors. Connection drops or tools never become available.

**Why it happens:** Any write to stdout corrupts the protocol. Common sources: unhandled exception tracebacks (Python writes these to stderr by default, but not always), a `print()` debug statement, a library that writes to stdout at import time.

**How to avoid:** Configure `logging.basicConfig(stream=sys.stderr)` first. Never use bare `print()`. Add a top-level `try/except` in `main()` that catches all exceptions, logs to stderr, and calls `sys.exit(1)` rather than letting the traceback propagate.

**Warning signs:** Claude Desktop shows server as connected but no tools appear, or shows a protocol error in the logs.

### Pitfall 4: Importing from extractors Without sys.path

**What goes wrong:** `ImportError: No module named 'extractors'` when running `server.py` directly.

**Why it happens:** The existing extractor files use `sys.path.append(str(Path(__file__).parent.parent))` at the top of each file to handle imports when run standalone. `server.py` at project root does not need that adjustment, but the import path must still be clean.

**How to avoid:** Since `server.py` lives at project root and the virtualenv is activated, `from extractors.phase6_chromadb_loader import ...` and `from config.pipeline_config import ...` work without `sys.path` manipulation. Verify with a direct run: `pipenv run py server.py`.

---

## Code Examples

### Minimal FastMCP Server Skeleton (Official Pattern)

```python
# Source: https://modelcontextprotocol.io/docs/develop/build-server
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("lds-scripture-index")

@mcp.tool()
def example_tool(query: str) -> str:
    """Placeholder — Phase 10 implements real tools."""
    return "Phase 10 not yet implemented"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### FastMCP Lifespan with Startup Validation (Composite Pattern)

```python
# Source: official SDK lifespan pattern + D-03/D-04/D-05 decisions
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import chromadb
from mcp.server.fastmcp import FastMCP

from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from extractors.phase6_chromadb_loader import get_chromadb_client, get_embedding_function

logger = logging.getLogger(__name__)

@dataclass
class AppContext:
    client: chromadb.ClientAPI
    collections: dict  # str -> chromadb.Collection
    embedding_fn: object

@asynccontextmanager
async def lifespan(server: FastMCP):
    ctx = _startup()   # raises SystemExit on failure; logs to stderr
    try:
        yield ctx
    finally:
        pass  # ChromaDB PersistentClient has no explicit close needed

mcp = FastMCP("lds-scripture-index", lifespan=lifespan)
```

### ChromaDB Path Resolution + Collection Guard

```python
# Source: D-03 decision + local verification of silent-creation behavior
def _resolve_chromadb_path() -> str:
    default = Path(__file__).parent.resolve() / "data" / "chromadb"
    raw = os.environ.get("CHROMADB_PATH", str(default))
    return str(Path(raw).resolve())

def _load_collections(client: chromadb.ClientAPI) -> dict:
    collections = {}
    for key, name in CHROMADB_COLLECTION_NAMES.items():
        try:
            col = client.get_collection(name=name)
        except Exception:
            print(
                f"ERROR: ChromaDB collection '{name}' not found. "
                "Run the pipeline (scripts/run_pipeline.py) first.",
                file=sys.stderr,
            )
            sys.exit(1)
        count = col.count()
        if count == 0:
            print(
                f"ERROR: Collection '{name}' exists but has 0 records. "
                "Re-run the pipeline to populate it.",
                file=sys.stderr,
            )
            sys.exit(1)
        logger.info("Loaded collection '%s' (%d records)", name, count)
        collections[key] = col
    return collections
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Standalone `fastmcp` package (jlowin/fastmcp) | Official `mcp` SDK with built-in FastMCP | mcp SDK 1.x | D-01 is already correct — official SDK is the canonical path |
| `mcp.run()` with no transport arg | `mcp.run(transport="stdio")` | mcp >= 1.2.0 | Explicit is better; default is still stdio but naming it is clearer |
| Startup logic inline in `if __name__ == "__main__"` | FastMCP lifespan `@asynccontextmanager` | mcp 1.x lifespan feature | Lifespan runs inside the server's async loop — safer for async resources |

**Deprecated/outdated:**
- Standalone `fastmcp` PyPI package: may lag behind official MCP SDK — D-01 explicitly prohibits it.
- `sse` transport: still supported but deferred to Milestone 3 per REQUIREMENTS.md Out of Scope.

---

## Open Questions

1. **Exception type from `get_collection()` when collection missing**
   - What we know: `get_collection()` raises when collection doesn't exist; the exception type in chromadb 1.5.5 is `chromadb.errors.InvalidCollectionException` (based on chromadb docs)
   - What's unclear: Whether the exception class name is stable across minor versions
   - Recommendation: Catch broad `Exception` in the guard and check the message — avoids brittle import of internal exception class

2. **FastMCP lifespan — sync vs async startup functions**
   - What we know: The lifespan must be an `@asynccontextmanager`. The startup validation (ChromaDB path check, Ollama call) can be sync functions called within it.
   - What's unclear: Whether `OllamaEmbeddingFunction.__call__` is sync or async in current chromadb version
   - Recommendation: Wrap the Ollama call in `asyncio.to_thread()` if needed — the lifespan is async context, but `OllamaEmbeddingFunction` uses `httpx` sync under the hood

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| mcp (Python SDK) | INTG-01, all MCP transport | NOT INSTALLED | — | None — must install via `pipenv install mcp` |
| chromadb | CORE-01, CORE-03 | ✓ | 1.5.5 | — |
| ollama (pip) | CORE-02 | ✓ | installed | — |
| Ollama daemon | CORE-02 | Running (with caveat) | 0.18.3 | Cannot proceed without it — fail fast per CORE-02 |
| nomic-embed-text model | CORE-02 | ✓ | latest | None — `ollama pull nomic-embed-text` required |
| ChromaDB data (4 collections) | CORE-03 | ✓ | All 4 populated | None — pipeline must have run (Phase 8 complete) |
| Python 3.10+ | mcp SDK requirement | ✓ | 3.14 | — |

**Collection record counts (verified 2026-03-30):**
- `conference_talks`: 5,838 records
- `conference_talk_paragraphs`: 202,175 records
- `conference_talk_citations`: 67,307 records
- `conference_talk_footnotes`: 25,608 records

**Missing dependencies with no fallback:**
- `mcp` package: not installed — `pipenv install mcp` must be Wave 0 task 1.

**Missing dependencies with fallback:**
- None beyond the above.

**Note on Ollama:** `ollama --version` returned "could not connect to a running Ollama instance" meaning the daemon was stopped at research time, but `ollama list` confirmed `nomic-embed-text:latest` (274 MB) is pulled. The server's startup check (CORE-02) will catch this condition at runtime.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (implicit discovery) |
| Quick run command | `pipenv run py -m pytest tests/test_server.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-01 | Path resolves to absolute regardless of cwd | unit | `pipenv run py -m pytest tests/test_server.py::test_chromadb_path_absolute -x` | Wave 0 |
| CORE-01 | get_collection() raises on wrong path (not silent creation) | unit | `pipenv run py -m pytest tests/test_server.py::test_chromadb_missing_collection_exits -x` | Wave 0 |
| CORE-02 | Ollama failure triggers sys.exit(1) with actionable message | unit (mock) | `pipenv run py -m pytest tests/test_server.py::test_ollama_failure_exits -x` | Wave 0 |
| CORE-03 | All 4 collections loaded before tools accept calls | unit | `pipenv run py -m pytest tests/test_server.py::test_all_collections_warmed -x` | Wave 0 |
| INTG-01 | Server produces no stdout output during startup | smoke (manual) | Run `pipenv run py server.py 2>/dev/null` and verify empty stdout | manual-only |

**Manual-only justification for INTG-01:** Verifying that stdout is clean requires actually running the full server process and capturing its output — not feasible in a unit test that imports the module. A smoke test run manually before Phase 11 integration covers this.

### Sampling Rate

- **Per task commit:** `pipenv run py -m pytest tests/test_server.py -x -q`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_server.py` — covers CORE-01, CORE-02, CORE-03 unit tests (does not exist yet)
- [ ] Framework install: `pipenv install mcp` — mcp not yet in Pipfile/Pipfile.lock

*(Existing 395-test suite covers Phases 1–6 infrastructure; no server tests exist yet.)*

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 9 |
|-----------|-------------------|
| `pipenv run py` for all Python commands | All pytest/server run commands must use `pipenv run py` |
| Update `tasks/lessons.md` after corrections | Not a planning constraint but executor must follow |
| Verify before marking complete | Phase gate test suite must be green |
| Simplicity First — minimal code impact | `server.py` imports existing functions; no reimplementation |
| Update Project Structure Index in CLAUDE.md when adding files | `server.py` must be added to the index after creation |

---

## Sources

### Primary (HIGH confidence)

- Official MCP docs: https://modelcontextprotocol.io/docs/develop/build-server — FastMCP server creation, logging guidance, stdio transport
- Local verification: `chromadb.PersistentClient` silent-creation behavior confirmed by running against a temp directory — `Created silently at nonexistent path: True`
- Local verification: ChromaDB collection counts confirmed (5,838 talks / 202,175 paragraphs / 67,307 citations / 25,608 footnotes)
- Local verification: `pip index versions mcp` — mcp 1.26.0 is current as of 2026-03-30
- `extractors/phase6_chromadb_loader.py` — `get_embedding_function()`, `get_chromadb_client()` signatures read directly
- `config/pipeline_config.py` — `CHROMADB_PATH`, `CHROMADB_COLLECTION_NAMES` confirmed

### Secondary (MEDIUM confidence)

- GitHub modelcontextprotocol/python-sdk README — FastMCP lifespan `@asynccontextmanager` pattern; cross-referenced with official docs
- WebSearch results on FastMCP lifespan hooks — consistent with official SDK example at `examples/snippets/servers/lifespan_example.py`

### Tertiary (LOW confidence)

- Exception class name `chromadb.errors.InvalidCollectionException` — from chromadb docs, not locally verified by import; using broad `Exception` catch is safer

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — mcp 1.26.0 confirmed via pip registry; chromadb 1.5.5 confirmed locally
- Architecture: HIGH — FastMCP lifespan pattern from official SDK + official docs; ChromaDB behavior verified locally
- Pitfalls: HIGH — silent DB creation verified by running code; stdout contamination from official MCP docs

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (mcp SDK is actively developed — re-verify if > 30 days)
