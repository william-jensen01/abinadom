# Architecture Patterns: MCP Server Integration

## Recommended Architecture

```
Claude Desktop (host)
    |
    | stdio (JSON-RPC over stdin/stdout)
    | [subprocess — Claude Desktop launches the server]
    v
mcp_server.py  (NEW — entry point)
    |
    +-- tools/search.py        (NEW — search tool handler)
    +-- tools/get_talk.py      (NEW — get_talk tool handler)
    +-- tools/normalizers.py   (NEW — fuzzy speaker/metadata normalization)
    |
    +-- chroma_client.py       (NEW — shared ChromaDB client factory)
    |
    v
ChromaDB PersistentClient  (EXISTING — data/chromadb/)
    |
    +-- conference_talks              (5,838 records)
    +-- conference_talk_paragraphs    (202,175 records)
    +-- conference_talk_citations     (67,307 records)
    +-- conference_talk_footnotes     (25,608 records)
```

The MCP server is a new, standalone module that reads from ChromaDB. It does not modify pipeline code (Phases 1–6), does not touch SQLite, and does not import from `extractors/` or `models/`.

---

## Transport: stdio

Use stdio. Do not use HTTP.

- Claude Desktop launches the MCP server as a subprocess and communicates via stdin/stdout
- stdio requires zero network config — no port binding, no firewall rules
- HTTP is for multi-client/remote scenarios; adds DNS rebinding risk and persistent process requirements
- MCP spec: "Clients SHOULD support stdio whenever possible"

---

## Process Model

Separate process, same pipenv virtualenv. One new dependency: `pipenv install "mcp[cli]"`.

**File lock conflict:** ChromaDB `PersistentClient` holds an exclusive lock on `data/chromadb/`. Do not run pipeline scripts while the MCP server is active.

---

## Component Map

| Component | File | New vs Existing |
|-----------|------|-----------------|
| MCP entry point | `mcp_server.py` | NEW |
| Search tool | `tools/search.py` | NEW |
| Get talk tool | `tools/get_talk.py` | NEW |
| Fuzzy normalizers | `tools/normalizers.py` | NEW |
| ChromaDB client factory | `chroma_client.py` | NEW |
| Pipeline config | `config/pipeline_config.py` | EXISTING (read-only) |

MCP server must NOT import from `extractors/`, `models/`, or `scripts/`.

---

## Claude Desktop Config (Windows)

File: `%AppData%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "lds-talks": {
      "command": "C:\\Users\\wbjen\\.virtualenvs\\LDS-MCP-XXXXXXXX\\Scripts\\python.exe",
      "args": ["C:\\Users\\wbjen\\OneDrive\\Documents\\LDS MCP\\mcp_server.py"]
    }
  }
}
```

Get virtualenv path via `pipenv --venv`, append `\Scripts\python.exe`. Use full absolute path — Claude Desktop has a minimal PATH. After editing: fully quit Claude Desktop via system tray and relaunch.

---

## Fuzzy Normalization

`tools/normalizers.py` — uses `difflib.get_close_matches()` (stdlib, no new dependency).

- Build canonical speaker list from ChromaDB metadata at startup
- Match "Holland" or "Elder Holland" → "Jeffrey R. Holland"
- Map collection aliases (talks/paragraphs/citations/footnotes) to `CHROMADB_COLLECTION_NAMES`
- Coerce year/month: accept "April"/"april"/"4", omit when absent

---

## Build Order

1. `chroma_client.py` — client factory
2. `tools/normalizers.py` — normalization (tools depend on this)
3. `tools/search.py` — search tool
4. `tools/get_talk.py` — get talk tool
5. `mcp_server.py` — entry point, tool registration
6. Claude Desktop config — wire up and test end-to-end
7. System prompt — add after tools verified working

---

## Critical Anti-Patterns

- **Writing to stdout** — corrupts JSON-RPC channel. Use `logging` to `sys.stderr` only. Never bare `print()`
- **Importing pipeline extractors** — unnecessary coupling; server only needs `chromadb` + `config/pipeline_config.py`
- **Simultaneous ChromaDB access** — pipeline + MCP server cannot run concurrently (file lock)
- **Raw user input in `where` filters** — always normalize before passing to ChromaDB
