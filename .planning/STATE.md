---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: Remote MCP
status: executing
stopped_at: "Checkpoint 16-02-T2: awaiting human verify of HTTPS endpoint"
last_updated: "2026-04-04T21:14:40.567Z"
last_activity: 2026-04-04
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 9
  completed_plans: 9
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks.
**Current focus:** Phase 16 — caddy-cloudflare-tunnel

## Current Position

Phase: 16 (caddy-cloudflare-tunnel) — EXECUTING
Plan: 2 of 2
Status: Ready to execute
Last activity: 2026-04-04

Progress: [████████░░░░░░░░░░░░] v1.0 + v2.0 complete; v3.0 not started

## Performance Metrics

**Velocity:**

- Total plans completed: 0 (v3.0)
- Average duration: --
- Total execution time: 0 hours

**By Phase (v2.0 reference):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 09-server-foundation P01 | 15 | 3 tasks | 5 files |
| Phase 09.1-gap-identified-in-phase-10-plans P01 | 9 | 2 tasks | 3 files |
| Phase 10-tools-normalization P01 | 8 | 2 tasks | 2 files |
| Phase 10-tools-normalization P02 | 7 | 2 tasks | 2 files |
| Phase 11-claude-desktop-integration P01 | 5 | 2 tasks | 3 files |
| Phase 11-claude-desktop-integration P02 | 10 | 2 tasks | 2 files |
| Phase 12-tech-debt-validation-cleanup P01 | 30 | 3 tasks | 7 files |

**Recent Trend:**

- Last 5 plans: v2.0 plans ranged 5–30 min
- Trend: Stable

*Updated after each plan completion*
| Phase 13-http-transport P02 | 6 | 2 tasks | 2 files |
| Phase 14-auth-module P01 | 4 | 1 tasks | 3 files |
| Phase 14-auth-module P02 | 15 | 2 tasks | 5 files |
| Phase 14-auth-module P03 | 3 | 1 tasks | 2 files |
| Phase 15-docker-compose-config P01 | 4 | 2 tasks | 4 files |
| Phase 15-docker-compose-config P02 | 15 | 3 tasks | 2 files |
| Phase 16-caddy-cloudflare-tunnel P01 | 3 | 2 tasks | 6 files |

## Accumulated Context

### Roadmap Evolution

- Phase 09.1 inserted after Phase 9: gap identified in phase 10 plans (URGENT)
- v3.0: Caddy + cloudflared separated into Phase 16 (depends on working Compose stack in Phase 15)
- v3.0: Auth module is a new module — does not touch existing MCP tools

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Phase 12]: _resolve_ollama_url() is single source of truth in server.py; resolved once, passed as url= to get_embedding_function
- [Phase 11]: Two-layer prompting: FastMCP mcp.instructions (tool-level) + SYSTEM_PROMPT.md (adaptive persona)
- [Phase 11]: OLLAMA_URL env var is a base URL; /api/embeddings suffix always appended in get_embedding_function
- [Phase 10]: Speaker filtering is Python post-filter (ChromaDB 1.5.5 metadata string filters silently broken)
- [Phase 09]: get_collection() not get_or_create_collection() as ChromaDB startup guard
- [Phase 13-http-transport]: Health handler uses try/except + return 503 (not sys.exit) to avoid killing the process on dependency failure
- [Phase 13-http-transport]: Live embedding call ef(['health']) used for Ollama check — confirms model loaded, not just daemon running
- [Phase 14-auth-module]: KeyStore implemented as ABC (not Protocol) for explicit TypeError on direct instantiation — testable and verifiable
- [Phase 14-auth-module]: Per-operation sqlite3 connections (_connect() per method) for thread safety in async uvicorn context
- [Phase 14-auth-module]: idx_usage_key index on usage_log added proactively — zero cost now, avoids migration when AUTH-06 usage admin is added
- [Phase 14-02]: mcp.run() replaced with mcp.streamable_http_app() + app.add_middleware() + uvicorn.run() — only way to inject ASGI middleware
- [Phase 14-02]: _extract_tool_name logs all authenticated methods by name (initialize, tools/list, tools/call) per AUTH-03 literal requirement
- [Phase 14-auth-module]: sqlite3.IntegrityError caught at CLI boundary for clean user-facing errors (no traceback)
- [Phase 14-auth-module]: manage_keys.py AUTH_DB_PATH defaults to Path(__file__).parent.parent / auth.db (not cwd)
- [Phase 15-docker-compose-config]: python:3.12-slim chosen as Docker base image — onnxruntime lacks Python 3.14 wheels
- [Phase 15-docker-compose-config]: requirements.txt committed to git from Pipfile.lock — avoids pipenv in Docker build stage
- [Phase 15-docker-compose-config]: No version: key in docker-compose.yml — deprecated in Compose v2 spec
- [Phase 15-docker-compose-config]: Single mcp-server service only — Ollama runs on host (operator-managed), no Compose-managed Ollama container
- [Phase 15-docker-compose-config]: CHROMADB_PATH and AUTH_DB_PATH not settable in .env — fixed container-internal paths; only mount source paths (CHROMADB_DATA_PATH, AUTH_DATA_PATH) are operator-configurable
- [Phase 16-caddy-cloudflare-tunnel]: infra/ stack owns proxy network (no external:true in infra); MCP stack joins as external:true — correct multi-stack Docker pattern per D-04
- [Phase 16-caddy-cloudflare-tunnel]: TUNNEL_TOKEN env var pattern (remotely-managed tunnel) — no credentials file on disk, ingress in Cloudflare dashboard
- [Phase 16-caddy-cloudflare-tunnel]: mcp-server ports: removed — internal-only, reachable by Caddy on proxy network only (D-05)

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260320-hr5 | backfill_talk_kicker not writing updates | 2026-03-20 | 8ba4345 | [260320-hr5](./quick/260320-hr5-backfill-talk-kicker-not-writing-updates/) |
| 260323-0jy | Fix sqlite3.OperationalError no such column URI_L/URI_GC | 2026-03-23 | cc87f51 | [260323-0jy](./quick/260323-0jy-fix-sqlite3-operationalerror-no-such-col/) |

## Session Continuity

Last session: 2026-04-04T21:14:40.561Z
Stopped at: Checkpoint 16-02-T2: awaiting human verify of HTTPS endpoint
Resume file: None
