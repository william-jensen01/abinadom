# MCP Stack Research — Python + ChromaDB

## New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp[cli]` | 1.2.0+ (verify at install) | Official MCP SDK — FastMCP is now inside this package |

**Install:** `pipenv install "mcp[cli]"`

No other new dependencies. mcp's transitive deps (anyio, pydantic, httpx, uvicorn) are already present in Pipfile.lock via chromadb.

## FastMCP vs Official SDK

Use `from mcp.server.fastmcp import FastMCP` — the official `mcp` package. The standalone `fastmcp` PyPI package is redundant; FastMCP was merged into the official SDK. The official quickstart at modelcontextprotocol.io uses this import path.

## Transport

**STDIO** for v2.0 (local Claude Desktop). The MCP spec says "Clients SHOULD support stdio whenever possible." Claude Desktop spawns the MCP server as a subprocess — no HTTP server needed.

## Python Compatibility

Python 3.10+ required. Project runs 3.14.2 — compatible.

## Claude Desktop Config (Windows)

Config file: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "lds-search": {
      "command": "C:\\path\\to\\pipenv\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\project\\mcp_server.py"]
    }
  }
}
```

**Critical:** `command` must be the full path to the Python executable inside the pipenv virtualenv (get it via `pipenv --venv`). Claude Desktop cannot resolve `pipenv` from PATH.

## Critical Gotcha

**Never write to stdout in STDIO mode.** This silently breaks the MCP connection — Claude Desktop reads stdout as the protocol stream. Use `logging` directed to `sys.stderr` only. This is the #1 cause of STDIO server breakage.
