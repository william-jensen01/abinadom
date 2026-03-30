# Domain Pitfalls

**Domain:** Local MCP server layer over existing Python/ChromaDB pipeline (Windows, pipenv)
**Researched:** 2026-03-30

---

## Critical Pitfalls

### Pitfall 1: Writing to stdout in a stdio MCP server

Any `print()` or library writing to stdout corrupts the JSON-RPC stream. Claude Desktop loses connection silently — no helpful error.

**Prevention:** Configure `logging` to `sys.stderr` only. Never bare `print()`. Audit imports for stdout writers. Launch server directly from CLI to check for stray output before connecting.

---

### Pitfall 2: Relative paths in `claude_desktop_config.json`

Claude Desktop spawns the server with an undefined working directory. `CHROMADB_PATH = "data/chromadb"` (relative, in `config/pipeline_config.py`) resolves wrong — ChromaDB silently creates a new empty DB. Queries return zero results with no error.

**Prevention:** Resolve `CHROMADB_PATH` to absolute at server startup: `Path(__file__).parent.parent / "data/chromadb"`. Use absolute paths everywhere in claude_desktop_config.json.

**Detection:** Log `collection.count()` at startup. If `conference_talks` shows 0, wrong path.

---

### Pitfall 3: Pipenv virtualenv not activated in Claude Desktop subprocess

`command` in `claude_desktop_config.json` must point to the pipenv-managed Python executable directly, not system `python`. Server exits immediately with `ModuleNotFoundError`.

**Prevention:** Run `pipenv --venv`, append `\Scripts\python.exe`. Test the exact command from a fresh terminal (not pipenv shell).

---

### Pitfall 4: Ollama not running at query time

`OllamaEmbeddingFunction` makes HTTP calls to `localhost:11434`. Server appears healthy until first search, then errors.

**Prevention:** Health check at startup. Catch connection errors in `search` handler and return: `"Error: Ollama is not running. Start Ollama and try again."` Document: Ollama must start before Claude Desktop.

---

### Pitfall 5: Returning too much text per tool call

202,175 paragraphs averaging 200–800 tokens each. A full talk is 35+ paragraphs.

**Prevention:** `search` default `n_results=5`, snippets not full text. Hard cap at 20 results. `get_talk` returns single full talk only. Plain text, not JSON.

---

### Pitfall 6: Verbose tool schema consuming system prompt tokens

Tool schemas are injected every turn. Long descriptions waste tokens.

**Prevention:** One sentence per tool, brief arg descriptions. Never embed data (no speaker enum lists). Flat parameter schemas — validate server-side.

---

## Moderate Pitfalls

### Pitfall 7: `topics` pipe-encoding breaks exact filters

`topics` stored as `"Faith|Prayer|Service"`. `{"topics": {"$eq": "Faith"}}` never matches. Same for `verse_list` (comma-joined ints).

**Prevention:** Use semantic search for topic queries. Avoid exact `topics` `where` filter. Comment the encoding in server code.

---

### Pitfall 8: Speaker name case-sensitive exact match

`"russell nelson"` or `"President Nelson"` returns zero results; stored value is `"Russell M. Nelson"`.

**Prevention:** Load canonical speaker list from ChromaDB at startup. Normalize input (lowercase, strip titles), fuzzy-match via `difflib.get_close_matches`. If no match, omit speaker filter.

---

### Pitfall 9: ChromaDB cold-start latency on Windows

First query after startup can take 3–10 seconds (202,175 paragraphs, SQLite index load).

**Prevention:** Warm up all 4 collections at startup with `collection.count()` before accepting tool calls. Log startup timing.

---

### Pitfall 10: `get_talk` returning paragraphs out of order

`collection.get(where={"talk_id": N})` returns arbitrary order. `position` field exists but ChromaDB has no `ORDER BY`.

**Prevention:** Sort by `position` in Python after retrieval: `sorted(results, key=lambda x: x['metadata']['position'])`.

---

### Pitfall 11: `%APPDATA%` not expanded in Windows config

Shell variables in claude_desktop_config.json paths are not expanded.

**Prevention:** Use fully expanded absolute paths. Run `echo %APPDATA%` and hardcode the literal path.

---

### Pitfall 12: Closing window doesn't restart MCP server

Code changes have no effect until Claude Desktop fully quits (system tray > Quit).

**Prevention:** Full quit after any server code change. Use MCP Inspector (`npx @modelcontextprotocol/inspector`) during development.

---

## Minor Pitfalls

### Pitfall 13: `mcp` not in Pipfile

Package not yet declared. Fresh `pipenv install` produces a broken server.

**Prevention:** `pipenv install "mcp[cli]"` as first step.

---

### Pitfall 14: Tool names with spaces or special characters

**Prevention:** Use `snake_case` only: `search`, `get_talk`.

---

### Pitfall 15: Raising exceptions instead of returning tool errors

Unhandled exceptions cause protocol-level errors; Claude may stop using the tool.

**Prevention:** Catch expected errors in tool handlers and return descriptive strings.

---

## Phase-Specific Warning Map

| Phase Topic | Pitfall | Mitigation |
|-------------|---------|------------|
| Server scaffold | #3 Pipenv path | Absolute Python executable path in config |
| Server scaffold | #13 mcp missing | Add `mcp[cli]` to Pipfile first |
| ChromaDB connection | #2 Relative path | Resolve to absolute at startup |
| ChromaDB connection | #4 Ollama down | Health check + handler catch |
| ChromaDB connection | #9 Cold-start | Warm up collections at startup |
| `search` tool | #1 stdout | All logging to stderr before any tool logic |
| `search` tool | #5 Token overflow | Default n=5, snippets, hard cap 20 |
| `search` tool | #6 Verbose schema | Under 2 lines, no embedded data |
| `search` tool | #7 topics encoding | Semantic search for topics, skip exact filter |
| `search` tool | #8 Speaker casing | Server-side fuzzy normalization |
| `get_talk` tool | #10 Paragraph order | Sort by `position` after retrieval |
| Claude Desktop wiring | #2 Relative paths | Absolute paths everywhere in config |
| Claude Desktop wiring | #11 Windows env vars | Expand %APPDATA% to literal |
| Claude Desktop wiring | #12 Window vs quit | Full quit after code changes |
