---
phase: 16-caddy-cloudflare-tunnel
plan: 02
subsystem: infra
tags: [docs, setup, cloudflare-tunnel, caddy, operator-guide]

# Dependency graph
requires:
  - phase: 16-01
    provides: infra/docker-compose.yml, infra/Caddyfile, infra/.env.example, docker-compose.yml (proxy network wired)
provides:
  - infra/SETUP.md — Complete operator walkthrough from zero (no Cloudflare account) to HTTPS endpoint at mcp.yourdomain.com
affects: [operator-deployment, DEPLOY-03, DEPLOY-04]

# Tech tracking
tech-stack:
  added: []
  patterns: [named Cloudflare tunnel (TUNNEL_TOKEN), HTTP-not-HTTPS upstream pattern for cloudflared→Caddy, Docker external network startup order]

key-files:
  created:
    - infra/SETUP.md
  modified: []

key-decisions:
  - "Service type in Cloudflare public hostname must be HTTP (not HTTPS) — cloudflared forwards to caddy:80; Cloudflare terminates TLS at the edge"
  - "Infra stack must start before MCP stack — proxy network does not exist until infra compose up runs"
  - "TUNNEL_TOKEN pattern means no reconfiguration on restart — same URL persists automatically"

patterns-established:
  - "Pattern: startup order documentation — infra first (creates proxy network), MCP stack second (joins it)"
  - "Pattern: caddy reload for live Caddyfile changes without container restart"

requirements-completed: []

# Metrics
duration: pending (Task 2 awaiting human verify)
completed: pending
---

# Phase 16 Plan 02: Setup Walkthrough + Human Verify Summary

**Complete operator walkthrough from zero (no Cloudflare account) to HTTPS endpoint via Caddy + Cloudflare Tunnel, with human verification checkpoint pending**

## Status

**Task 1 COMPLETE** — `infra/SETUP.md` created and committed.  
**Task 2 PENDING** — Human verification checkpoint. Operator must follow `infra/SETUP.md` and confirm `curl -f https://mcp.yourdomain.com/health` returns HTTP 200 from outside the local network.

## Performance

- **Duration:** In progress
- **Started:** 2026-04-04T21:12:56Z
- **Completed:** Pending Task 2 human verify
- **Tasks:** 1 of 2 complete
- **Files modified:** 1

## Accomplishments

- Created `infra/SETUP.md` — 8-step walkthrough covering the full zero-to-HTTPS operator journey per D-09
- Covers every pitfall identified in research: HTTP-not-HTTPS upstream, startup order (infra first), named tunnel vs quick tunnel, DOMAIN variable, proxy network creation
- Troubleshooting section maps each pitfall to an exact diagnostic and fix command
- Adding More Services section shows how to extend the stack to Jellyfin and other services via Caddyfile + caddy reload

## Task Commits

1. **Task 1: Create infra/SETUP.md walkthrough document** — `d89e72f` (feat)

## Files Created/Modified

- `infra/SETUP.md` — Complete operator walkthrough: Cloudflare account → domain → named tunnel → public hostname (HTTP, caddy:80) → .env setup → infra stack → MCP stack → curl verification + troubleshooting + adding services + restart guide

## Decisions Made

- HTTP (not HTTPS) is the correct service type for the Cloudflare public hostname — cloudflared routes to Caddy on the internal Docker network (plain HTTP); Cloudflare terminates external TLS at the edge
- Startup order documented explicitly: infra stack must run first to create the `proxy` network; MCP stack joins it second
- Named tunnel pattern (TUNNEL_TOKEN) means the same public URL is restored on every restart — no Cloudflare dashboard reconfiguration needed after initial setup

## Deviations from Plan

None — plan executed exactly as written for Task 1.

## Known Stubs

None. `infra/SETUP.md` is a complete documentation artifact. No data wiring or code stubs.

## Pending: Task 2 Human Verification

The operator must:
1. Follow `infra/SETUP.md` Steps 1–8 on the Dell PowerEdge R720 server
2. Verify from a machine outside the local network: `curl -f https://mcp.yourdomain.com/health`
3. Expected: HTTP 200 with `{"status": "healthy", ...}`
4. Verify host IP is not exposed in response headers
5. Verify restart persistence: bring infra stack down and up, re-run curl — same URL works

Requirements DEPLOY-03 and DEPLOY-04 are satisfied once the operator confirms the above.
