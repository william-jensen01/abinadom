---
phase: 16-caddy-cloudflare-tunnel
plan: 01
subsystem: infra
tags: [docker, caddy, cloudflared, cloudflare-tunnel, reverse-proxy, compose]

# Dependency graph
requires:
  - phase: 15-docker-compose-config
    provides: docker-compose.yml with mcp-server service, container name mcp-server on port 8000
provides:
  - infra/docker-compose.yml — Caddy + cloudflared services on named proxy network
  - infra/Caddyfile — subdomain routing from mcp.DOMAIN to mcp-server:8000
  - infra/.env.example — operator env var documentation (TUNNEL_TOKEN, DOMAIN)
  - docker-compose.yml — MCP server joined to proxy external network, no published ports
affects: [phase-16-plan-02, operator-setup-docs]

# Tech tracking
tech-stack:
  added: [caddy:2-alpine, cloudflare/cloudflared:latest]
  patterns: [multi-stack Docker external network, TUNNEL_TOKEN remotely-managed cloudflare tunnel, Caddyfile env var substitution]

key-files:
  created:
    - infra/docker-compose.yml
    - infra/Caddyfile
    - infra/.env.example
  modified:
    - docker-compose.yml
    - .gitignore
    - CLAUDE.md

key-decisions:
  - "infra/ stack owns the proxy network (no external: true in infra); MCP stack joins it as external: true"
  - "caddy:2-alpine chosen over caddy:latest to avoid unexpected major version jumps"
  - "cloudflare/cloudflared:latest conventional for single-operator stacks; pinning is operator option"
  - "TUNNEL_TOKEN env var pattern (remotely-managed tunnel) — no credentials file on disk"
  - "mcp-server ports: removed — internal-only, reachable by Caddy on proxy network only"
  - "Caddyfile bind-mounted :ro so operator can edit routing without rebuilding"
  - "admin off in Caddyfile — no config API needed in this deployment"

patterns-established:
  - "Pattern: multi-stack Docker network via external: true — infra stack creates network, app stacks join it"
  - "Pattern: Caddyfile {$DOMAIN} substitution from .env for subdomain routing"
  - "Pattern: cloudflared remotely-managed tunnel — ingress rules in Cloudflare dashboard, not local YAML"

requirements-completed: [DEPLOY-03, DEPLOY-04]

# Metrics
duration: 3min
completed: 2026-04-04
---

# Phase 16 Plan 01: Caddy + Cloudflare Tunnel Infra Stack Summary

**Shared infra Compose stack with Caddy (reverse proxy) and cloudflared (Cloudflare Tunnel), MCP server wired in via Docker external network with ports removed**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-04T21:06:51Z
- **Completed:** 2026-04-04T21:10:10Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Created `infra/` directory with complete Compose stack: caddy:2-alpine + cloudflared:latest on a bridge network named `proxy`
- Caddyfile routes `mcp.{$DOMAIN}` to `mcp-server:8000` with `admin off` and no TLS config (Cloudflare handles TLS at the edge)
- MCP `docker-compose.yml` updated: `ports:` block removed, `networks: proxy` added (external: true) — mcp-server is now internal-only
- All 470 existing tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create infra/ Compose stack files** - `e6261f4` (feat)
2. **Task 2: Wire MCP docker-compose.yml into proxy network and update project files** - `93db79c` (feat)

**Plan metadata:** (final commit — see below)

## Files Created/Modified
- `infra/docker-compose.yml` — Caddy + cloudflared services, proxy bridge network definition, named volumes
- `infra/Caddyfile` — Global options (admin off) + mcp.{$DOMAIN} site block routing to mcp-server:8000
- `infra/.env.example` — Operator env var docs: TUNNEL_TOKEN and DOMAIN
- `docker-compose.yml` — Removed ports: block, added networks: proxy (external: true, name: proxy)
- `.gitignore` — Added infra/.env entry
- `CLAUDE.md` — Added ### infra/ section to project structure index

## Decisions Made
- infra stack owns the `proxy` network (creates it, no `external: true`); MCP stack joins as `external: true` — this is the correct multi-stack Docker pattern per D-04
- `caddy:2-alpine` (not `:latest`) for version stability on major releases
- `cloudflare/cloudflared:latest` — conventional for operator stacks; Cloudflare releases monthly and `:latest` is their recommended tag for single-operator deployments
- TUNNEL_TOKEN env var pattern (remotely-managed tunnel per D-01) — no credentials file on disk, ingress rules live in Cloudflare dashboard
- `ports:` removed from docker-compose.yml per D-05 — mcp-server only reachable by Caddy on the proxy network (eliminates host port exposure)
- Caddyfile bind-mounted `:ro` per D-08 — operator edits routing without rebuilding container
- `admin off` in Caddyfile — no dynamic config API needed in this deployment

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — all files created cleanly, all acceptance criteria met, 470 tests passed.

## User Setup Required
None - no external service configuration required at this stage. Operator setup walkthrough will be delivered in Plan 02.

## Next Phase Readiness
- All infra stack config files committed and ready for operator deployment
- Phase 16 Plan 02 (operator setup walkthrough / docs) can proceed
- Operator will need: Cloudflare account, domain registered with Cloudflare DNS, TUNNEL_TOKEN from Cloudflare Zero Trust dashboard
- Stack startup order: `~/infra/` first (creates proxy network), then MCP project (joins proxy network)

---
*Phase: 16-caddy-cloudflare-tunnel*
*Completed: 2026-04-04*
