---
phase: 15-docker-compose-config
plan: "02"
subsystem: infra
tags: [docker, docker-compose, env, deployment, healthcheck, chromadb, ollama]

# Dependency graph
requires:
  - phase: 15-docker-compose-config plan 01
    provides: Dockerfile, .dockerignore, requirements.txt — the base image build artifacts this compose file references

provides:
  - docker-compose.yml orchestrating mcp-server with env_file, bind mounts, healthcheck, and host.docker.internal support
  - .env.example documenting all 5 operator-facing variables (OLLAMA_URL, MCP_HOST, MCP_PORT, CHROMADB_DATA_PATH, AUTH_DATA_PATH)

affects:
  - 16-caddy-cloudflared (uses docker-compose.yml as compose base, may extend or override)
  - any future infra phase deploying or scaling the mcp-server container

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "docker compose env_file pattern: .env supplies all runtime config, compose references ${VAR} for bind mount paths and ports"
    - "healthcheck start_period: 60s absorbs ChromaDB ONNX model cold start before unhealthy is reported"
    - "extra_hosts host.docker.internal:host-gateway enables container-to-host Ollama connectivity on Linux"

key-files:
  created:
    - docker-compose.yml
    - .env.example
  modified: []

key-decisions:
  - "No version: key in docker-compose.yml — deprecated in Compose v2 spec"
  - "Single mcp-server service — no Ollama container managed in compose (operator-owned Ollama per D-01)"
  - "Bind mounts use ${CHROMADB_DATA_PATH} and ${AUTH_DATA_PATH} variables (not hardcoded paths, per D-04/D-05)"
  - "Exactly 5 operator-facing variables in .env.example — CHROMADB_PATH and AUTH_DB_PATH excluded (fixed inside container per D-06/D-07/D-09)"

patterns-established:
  - "Operator copy-fill pattern: cp .env.example .env, fill values, docker compose up — zero manual config beyond that"

requirements-completed: [DEPLOY-01, DEPLOY-02]

# Metrics
duration: 15min
completed: 2026-04-04
---

# Phase 15 Plan 02: docker-compose.yml and .env.example Summary

**docker-compose.yml with bind-mount volumes, 60s-start healthcheck, and host.docker.internal; .env.example documenting the 5-variable operator contract**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-04T18:40:00Z
- **Completed:** 2026-04-04T18:55:00Z
- **Tasks:** 3 (2 auto, 1 human-verify checkpoint)
- **Files modified:** 2

## Accomplishments

- Created docker-compose.yml with mcp-server service using env_file, bind mounts via operator-supplied paths, healthcheck with 60s start_period, and extra_hosts for Linux Ollama connectivity
- Created .env.example with exactly 5 operator-facing variables plus comments explaining container-internal paths and pre-existing host directory requirement
- Verified: no hardcoded paths (graviton, /mnt/) or secrets in any Docker file; all 470 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Create docker-compose.yml with healthcheck and bind mounts** - `2d37be0` (feat)
2. **Task 2: Create .env.example with all 5 operator-facing variables** - `6319d1e` (feat)
3. **Task 3: Verify Docker build and compose config** — human-verify checkpoint (user approved); verification automated checks all passed

## Files Created/Modified

- `docker-compose.yml` - mcp-server service orchestration: build, env_file, bind mounts, healthcheck, restart policy, extra_hosts
- `.env.example` - Operator configuration contract: 5 variables with explanatory comments

## Decisions Made

- No `version:` key in compose file — deprecated in Compose v2 spec and causes warnings in recent Docker
- Single `mcp-server` service only — Ollama runs on the host (operator-managed), no Compose-managed Ollama container
- `CHROMADB_PATH` and `AUTH_DB_PATH` not settable in .env — they are fixed container-internal paths (/data/chromadb, /data/auth.db); only host-side mount source paths (CHROMADB_DATA_PATH, AUTH_DATA_PATH) are operator-configurable

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

After this plan, the operator must:
1. `cp .env.example .env`
2. Fill in `OLLAMA_URL` (e.g., `http://host.docker.internal:11434` on Linux or LAN IP)
3. Create host data directories and set `CHROMADB_DATA_PATH` and `AUTH_DATA_PATH`
4. Run `docker compose up`

No additional configuration beyond filling .env is required.

## Known Stubs

None - all variables in docker-compose.yml are resolved from .env at runtime. No placeholder values flow to container behavior.

## Next Phase Readiness

- Complete Docker deployment stack is ready: Dockerfile (Plan 01) + docker-compose.yml + .env.example (this plan)
- Phase 16 (Caddy + cloudflared) can reference or extend docker-compose.yml for reverse proxy and tunnel setup
- No blockers

---
*Phase: 15-docker-compose-config*
*Completed: 2026-04-04*
