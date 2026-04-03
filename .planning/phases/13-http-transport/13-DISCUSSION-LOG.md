# Phase 13: HTTP Transport - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 13-http-transport
**Areas discussed:** Host binding, Health endpoint payload, MCP endpoint path, Env-var config scope

---

## Host Binding

| Option | Description | Selected |
|--------|-------------|----------|
| 0.0.0.0 hardcoded | Docker-ready, no env var | |
| 127.0.0.1 hardcoded, fix in Phase 15 | Safe default, two revisits | |
| Env var (default 0.0.0.0) | 12-factor, Docker-ready, Phase 15 just sets .env | ✓ |

**User's choice:** `MCP_HOST` env var defaulting to `0.0.0.0`; `MCP_PORT` env var defaulting to `8000`
**Notes:** User asked about the difference between hardcoded 0.0.0.0 and env var with same default. After clarification (env var allows operator override without code edit, avoids Phase 15 server.py revisit), chose env var approach.

---

## Health Endpoint Payload

| Option | Description | Selected |
|--------|-------------|----------|
| Static {"status":"ok"} | Zero latency, always 200 | |
| Dynamic — Ollama + collection counts | Live checks, heavier | ✓ (modified) |
| Static + version/uptime | Status + service name | |

**User's choice:** Dynamic — but collection counts don't matter. Final payload: `{"status":"ok","ollama":"reachable","chromadb":"reachable"}`.
**Notes:** User selected dynamic but noted collection counts are unnecessary. Follow-up confirmed ChromaDB reachability should be included (not just Ollama). Health endpoint serves as a readiness probe.

---

## MCP Endpoint Path

| Option | Description | Selected |
|--------|-------------|----------|
| Keep /mcp default | FastMCP standard, no config change | ✓ |
| Use / (root) | Cleaner URL, conflicts with /health | |
| Custom path | Adds indirection, no benefit | |

**User's choice:** Keep `/mcp` default.
**Notes:** No override needed.

---

## Env-Var Config Scope

| Option | Description | Selected |
|--------|-------------|----------|
| MCP_HOST + MCP_PORT only | Minimal, Phase 15 owns the rest | ✓ |
| Add MCP_LOG_LEVEL | Slightly broader, useful for containers | |
| Full transport config (path, log level too) | Ahead of Phase 15 scope | |

**User's choice:** `MCP_HOST` and `MCP_PORT` only.
**Notes:** CHROMADB_PATH and OLLAMA_URL already exist as env vars. Phase 15 consolidates everything into .env.

---

## Claude's Discretion

- How `/health` is mounted on the Starlette app
- Whether health-check logic is refactored into a shared helper
- 503 error shape when a dependency fails

## Deferred Ideas

None.
