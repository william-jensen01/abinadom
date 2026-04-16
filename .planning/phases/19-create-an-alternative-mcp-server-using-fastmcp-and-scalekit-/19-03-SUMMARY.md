---
phase: 19-create-an-alternative-mcp-server-using-fastmcp-and-scalekit-
plan: "03"
subsystem: deployment-config
tags: [pipfile, requirements, docker, scalekit, env-config]
dependency_graph:
  requires: [19-02]
  provides: [clean-pipfile, updated-requirements-txt, scalekit-env-config, docker-compose-cleanup]
  affects: [docker-compose.yml, .env.example, Pipfile, requirements.txt]
tech_stack:
  added: []
  patterns: [env-file-driven-config, fastmcp-transport]
key_files:
  created: []
  modified:
    - Pipfile
    - Pipfile.lock
    - requirements.txt
    - .env.example
    - docker-compose.yml
decisions:
  - fastmcp replaces fastapi in Pipfile; fastapi was a leftover from the pre-FastMCP architecture
  - scalekit-sdk-python removed entirely (FastMCP ScalekitProvider handles OAuth without the SDK)
  - mcp kept in Pipfile as fastmcp lists it as a required dependency
  - AUTH_DATA_PATH and auth.db volume removed; SqliteKeyStore-based bearer auth replaced by ScalekitProvider
  - FASTMCP_HOST/FASTMCP_PORT replace MCP_HOST/MCP_PORT to match FastMCP env var naming
metrics:
  duration: 15 min
  completed: "2026-04-15"
  tasks_completed: 2
  files_modified: 5
---

# Phase 19 Plan 03: Dependency and Deployment Config Cleanup Summary

**One-liner:** Removed fastapi and scalekit-sdk-python from deps, regenerated requirements.txt, replaced Auth0 config with ScaleKit vars in .env.example and docker-compose.yml.

## What Was Done

Cleaned up deployment configuration to reflect the FastMCP + ScalekitProvider architecture established in Plans 01 and 02:

1. **Pipfile cleanup** — Replaced `fastapi = "*"` with `fastmcp = "*"` (fastapi was unused after FastMCP took over as transport); confirmed `mcp` is a transitive dependency of fastmcp and kept it.
2. **Dependency removal** — Uninstalled `fastapi` (via `pipenv uninstall`) and `scalekit-sdk-python` (pip-only, not in Pipfile); FastMCP's built-in `ScalekitProvider` handles OAuth without the SDK.
3. **requirements.txt regenerated** — Fresh freeze from Pipfile.lock; neither fastapi nor scalekit-sdk-python appear.
4. **.env.example updated** — Replaced Auth0 section (AUTH0_DOMAIN, AUTH0_AUDIENCE) with ScaleKit section (SCALEKIT_ENVIRONMENT_URL, SCALEKIT_RESOURCE_ID, MCP_BASE_URL); replaced MCP_HOST/MCP_PORT with FASTMCP_HOST/FASTMCP_PORT; removed AUTH_DATA_PATH.
5. **docker-compose.yml cleaned** — Removed `${AUTH_DATA_PATH}:/data/auth.db` volume mount; auth.db is no longer used.

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Remove fastapi, regenerate requirements.txt | 8980b7f | Pipfile, Pipfile.lock, requirements.txt |
| 2 | Update .env.example and docker-compose.yml | fb20a1a | .env.example, docker-compose.yml |

## Verification

- `grep "fastapi" Pipfile` — no matches
- `grep "SCALEKIT_ENVIRONMENT_URL" .env.example` — matches (present)
- `grep "AUTH0_DOMAIN" .env.example` — no matches
- `grep "auth.db" docker-compose.yml` — no matches
- `pipenv run py -m pytest tests/ -x -q` — 449 passed, 1 warning

## Deviations from Plan

**1. [Rule 1 - Bug] Pipfile already missing fastapi at copy time**
- **Found during:** Task 1
- **Issue:** The worktree's Pipfile had `fastapi = "*"` (original state), but `pipenv uninstall fastapi` in the main project already updated the Pipfile there to have `fastmcp = "*"` (from Phase 19-01/02 work). After uninstalling, the main project's Pipfile showed `fastmcp = "*"` not just the removal of fastapi.
- **Fix:** Copied the authoritative updated Pipfile and Pipfile.lock from the main project to the worktree after running `pipenv uninstall`.
- **Files modified:** Pipfile, Pipfile.lock
- **Commit:** 8980b7f

## Known Stubs

None.

## Threat Flags

No new security-relevant surface introduced. `.env.example` contains only placeholder values (empty strings for secrets). `.env` remains in `.gitignore`.

## Self-Check: PASSED

- Pipfile exists and contains `fastmcp = "*"`, no `fastapi`: FOUND
- requirements.txt exists and contains no fastapi/scalekit: FOUND
- .env.example contains SCALEKIT_ENVIRONMENT_URL=: FOUND
- docker-compose.yml has no auth.db: FOUND
- Commits 8980b7f and fb20a1a exist: FOUND
