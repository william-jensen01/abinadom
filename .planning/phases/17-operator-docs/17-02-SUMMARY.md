---
phase: 17-operator-docs
plan: 02
subsystem: docs
tags: [deployment, linux, docker, caddy, cloudflare, mcp]

requires: []
provides:
  - Self-deploy guide for Linux operators (docs/DEPLOY.md)
affects: [17-04]

tech-stack:
  added: []
  patterns: ["5-step numbered deploy guide linking to infra/SETUP.md without duplication"]

key-files:
  created:
    - docs/DEPLOY.md
  modified: []

key-decisions:
  - "Link to infra/SETUP.md for Caddy + Tunnel step rather than duplicating instructions"
  - "Include full env var table sourced from .env.example (8 variables)"

patterns-established:
  - "Operator guides reference infra/SETUP.md for infra-level steps"

requirements-completed:
  - DOCS-02

duration: 8min
completed: 2026-04-13
---

# Plan 17-02: Deploy Guide Summary

**5-step self-deploy guide covering clone → configure → start → public access → Auth0 setup for Linux operators**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-04-13
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- `docs/DEPLOY.md` created with 5 numbered steps: clone repo, configure .env, start MCP stack, set up public access (links to infra/SETUP.md), configure Auth0
- Full env var table with 8 variables sourced from `.env.example`
- Links to `infra/SETUP.md` for Caddy + Tunnel step (no duplication per D-05)
- 5-item troubleshooting section covering common operator issues
- All acceptance criteria from plan passed

## Task Commits

1. **Task 1: Create self-deploy guide** - `c85cee7` (docs)

## Files Created/Modified
- `docs/DEPLOY.md` — 5-step Linux self-deploy guide with env var table, health check verification, infra/SETUP.md link, and troubleshooting section

## Decisions Made
- Linked to `infra/SETUP.md` for Caddy + Tunnel step rather than duplicating those instructions — follows D-05 separation of concerns

## Deviations from Plan
None - plan executed exactly as written

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Deploy guide complete, ready for README.md (17-04) to link it

---
*Phase: 17-operator-docs*
*Completed: 2026-04-13*
