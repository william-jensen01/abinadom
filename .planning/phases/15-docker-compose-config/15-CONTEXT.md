# Phase 15: Docker Compose & Config - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Containerize the mcp-server with a `docker-compose.yml` and `Dockerfile`. All configuration driven by a `.env` file — no secrets or absolute paths in any tracked file. Ollama runs separately (not in Compose). A `.env.example` documents every configurable value.

This phase does NOT add Caddy or Cloudflare Tunnel (Phase 16 scope). The server is plain HTTP inside the container — TLS and public URL are Phase 16.

</domain>

<decisions>
## Implementation Decisions

### Ollama

- **D-01:** No Ollama container in Compose. `OLLAMA_URL` is purely `.env`-driven — the operator points it at wherever Ollama is running (host machine, remote box, etc.). The mcp-server code requires no changes.
- **D-02:** Operator is responsible for running `ollama pull <model>` before `docker compose up`. No startup script or entrypoint logic for model pulling. `/health` returns 503 until Ollama is reachable with the model loaded — clear signal if misconfigured.
- **Hardware note:** Deployment target is a Dell PE R720 with Intel Xeon E5-2670 (CPU-only, no GPU). Ollama runs on CPU. This reinforces keeping Ollama out of the Compose stack — no GPU passthrough complexity needed.

### Data Volumes

- **D-03:** Bind mounts via `.env`-configured host paths. Two variables for host-side paths: `CHROMADB_DATA_PATH` and `AUTH_DATA_PATH`. These are set in `.env` (not committed) and referenced in `compose.yml` via variable substitution.
- **D-04:** `compose.yml` volume entries:
  ```yaml
  volumes:
    - ${CHROMADB_DATA_PATH}:/data/chromadb
    - ${AUTH_DATA_PATH}:/data/auth.db
  ```
- **D-05:** Operator sets host paths to their storage mount, e.g. `/mnt/graviton/sci/chromadb` and `/mnt/graviton/sci/auth`. No absolute paths appear in any tracked file.

### Container-Internal Paths

- **D-06:** `CHROMADB_PATH` is fixed at `/data/chromadb` inside the container — set via `ENV CHROMADB_PATH=/data/chromadb` in the Dockerfile. Operator only controls the host-side path via `CHROMADB_DATA_PATH`. No two-variable sync risk.
- **D-07:** `AUTH_DB_PATH` is fixed at `/data/auth.db` inside the container — set via `ENV AUTH_DB_PATH=/data/auth.db` in the Dockerfile. Host-side path configured via `AUTH_DATA_PATH` in `.env`.

### .env Contract

- **D-08:** Every configurable value is documented in `.env.example` (committed). The operator copies it to `.env`, fills in their values, and `docker compose up` picks them up.
- **D-09:** Variables to document in `.env.example`: `OLLAMA_URL`, `MCP_HOST`, `MCP_PORT`, `CHROMADB_DATA_PATH`, `AUTH_DATA_PATH`. Internal paths (`CHROMADB_PATH`, `AUTH_DB_PATH`) are fixed in the image and do NOT appear in `.env.example` — they are not operator-facing.

### Claude's Discretion

- Python base image choice (e.g. `python:3.11-slim`) and Dockerfile layer ordering
- Whether pipenv or pip is used inside Docker (Pipfile vs generated requirements.txt)
- Docker Compose healthcheck configuration (interval, retries, timeout) using `/health`
- Container restart policy (`unless-stopped` or `always`)
- Whether `MCP_HOST` and `MCP_PORT` default to `0.0.0.0` and `8000` in the Dockerfile or only in `.env.example`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Server
- `server.py` — Entry point; all env vars already wired (`MCP_HOST`, `MCP_PORT`, `CHROMADB_PATH`, `OLLAMA_URL`, `AUTH_DB_PATH`)

### Requirements
- `.planning/REQUIREMENTS.md` §DEPLOY-01, DEPLOY-02 — Docker Compose startup and .env contract requirements

### Roadmap
- `.planning/ROADMAP.md` §Phase 15 — Success criteria (3 items: `docker compose up` starts stack, `.env.example` documents all values, no secrets/paths in tracked files)

### Prior Phase Context
- `.planning/phases/13-http-transport/13-CONTEXT.md` — `/health` endpoint must remain public; established as Docker Compose healthcheck target; responds to `GET /health`
- `.planning/phases/14-auth-module/14-CONTEXT.md` — `AUTH_DB_PATH` env var, `auth/` module structure, `auth.db` location

No external specs — standard Docker Compose v3 syntax. No new libraries required.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `server.py` env var block (lines 258–262) — `MCP_HOST`, `MCP_PORT`, `CHROMADB_PATH`, `AUTH_DB_PATH` all resolved via `os.environ.get()`. Fixed internal paths will be set as `ENV` in Dockerfile; no code changes needed.
- `GET /health` endpoint — already implemented and returns 200/503 with live Ollama + ChromaDB checks. Used directly as Docker Compose `healthcheck` target.
- `auth/` package (`store.py`, `middleware.py`, `__init__.py`) — fully implemented; no changes needed for containerization.
- `Pipfile` / `Pipfile.lock` — dependency manifest for image build.

### Established Patterns
- `os.environ.get("VAR", default)` — all env var resolution; Dockerfile `ENV` overrides defaults for container-internal paths
- All logging to `sys.stderr` only — compatible with Docker log collection

### Integration Points
- `docker-compose.yml` references `${CHROMADB_DATA_PATH}` and `${AUTH_DATA_PATH}` for bind mounts
- `Dockerfile` sets `ENV CHROMADB_PATH=/data/chromadb` and `ENV AUTH_DB_PATH=/data/auth.db`
- `/health` endpoint wired as `healthcheck` in `compose.yml`

</code_context>

<specifics>
## Specific Ideas

- Deployment target: Dell PowerEdge R720, Intel Xeon E5-2670 (CPU-only). No GPU. Ollama runs on CPU on the host.
- Storage mount at `/mnt/graviton/sci/` — operator will set `CHROMADB_DATA_PATH=/mnt/graviton/sci/chromadb` and `AUTH_DATA_PATH=/mnt/graviton/sci/auth`.
- Ollama is external to the Compose stack; `OLLAMA_URL` in `.env` points to wherever it runs (e.g. `http://host.docker.internal:11434` or a LAN IP).

</specifics>

<deferred>
## Deferred Ideas

- **Ollama sidecar** — Could be added to `compose.yml` later if needed. The `OLLAMA_URL` design makes it a one-service addition. Deferred due to CPU-only hardware (no GPU passthrough benefit).
- **Caddy + TLS** — Phase 16 scope.
- **Cloudflare Tunnel** — Phase 16 scope.

</deferred>

---

*Phase: 15-docker-compose-config*
*Context gathered: 2026-04-04*
