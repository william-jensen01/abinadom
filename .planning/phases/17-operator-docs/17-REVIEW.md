---
phase: 17-operator-docs
reviewed: 2026-04-13T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - docs/CONNECTION.md
  - docs/DEPLOY.md
  - docs/KEY-MANAGEMENT.md
  - README.md
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-04-13
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

The four operator documentation files are generally well-structured and cover the expected topics. However, two critical issues were found that would cause operator failures: a wrong tool parameter name in a curl example (`n_results` instead of `limit`) and a misleading description of the `AUTH_DATA_PATH`/`AUTH_DB_PATH` directory-vs-file mount relationship. Three warnings cover: an incorrect health status value claimed in docs vs what the server returns, a missing `Mcp-Session-Id` header step-1 note discrepancy, and the `DEPLOY.md` reference to an `infra/SETUP.md` that exists but whose content the operator is expected to discover independently. Two informational items cover minor inconsistencies.

---

## Critical Issues

### CR-01: Wrong parameter name in `tools/call` curl example

**File:** `docs/CONNECTION.md:97`

**Issue:** The curl example for calling the `search` tool passes `"n_results":3` as an argument. The actual tool parameter is named `limit`, not `n_results` (confirmed in `server.py` line 622 tool schema and in the `search` function signature at line 247). A client sending `n_results` will have it silently ignored and the default of 5 results will be returned, with no error — operators following this example will get incorrect behavior without any obvious feedback.

**Fix:**
```bash
curl -X POST https://mcp.yourdomain.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Mcp-Session-Id: SESSION_ID_FROM_STEP_1" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search","arguments":{"query":"faith and repentance","collection":"paragraphs","limit":3}}}'
```

---

### CR-02: `AUTH_DATA_PATH` volume mount mounts a directory at a file path — causes SQLite failure

**File:** `docs/DEPLOY.md:49` (cross-referenced with `docker-compose.yml:8`)

**Issue:** `DEPLOY.md` instructs operators to set `AUTH_DATA_PATH` to a host directory (e.g., `/home/user/data/auth`) and to `mkdir -p` that directory. However, `docker-compose.yml` mounts it as:

```yaml
- ${AUTH_DATA_PATH}:/data/auth.db
```

This mounts a host **directory** at the container path `/data/auth.db`, which is where the Dockerfile sets `AUTH_DB_PATH`. When SQLite attempts to open `/data/auth.db`, it will encounter a directory entry at that path and fail with `unable to open database file` or similar. The auth module will crash on startup.

The correct approach is either:
- Mount a specific file: `${AUTH_DATA_PATH}/auth.db:/data/auth.db` (requires pre-creating the file, or letting SQLite create it — but Docker will create a directory if the source path doesn't exist as a file)
- Mount the directory to a different container path and update `AUTH_DB_PATH`: `${AUTH_DATA_PATH}:/data/auth` with `AUTH_DB_PATH=/data/auth/auth.db`

**Fix for docs:** Update the table in `DEPLOY.md` to accurately describe what `AUTH_DATA_PATH` should contain and warn that the compose file mounts it directly as the `.db` file path. Coordinate with the `docker-compose.yml` fix so the description matches the actual mount behavior.

---

## Warnings

### WR-01: Health endpoint returns `"status": "ok"` not `"status": "healthy"`

**File:** `docs/DEPLOY.md:75` and `docs/DEPLOY.md:93` and `infra/SETUP.md:149`

**Issue:** Both `DEPLOY.md` and `infra/SETUP.md` state the expected health response contains `"status": "healthy"`. The actual server code (`server.py` line 400) returns `"status": "ok"` on success and `"status": "degraded"` on partial failure. An operator following these docs who scripts against the health endpoint checking for `"healthy"` will get false negatives.

**Fix:** Change the expected response examples in `DEPLOY.md` (lines 75 and 93) and `infra/SETUP.md` (line 149):
```
Expected: JSON with `"status": "ok"`.
```

---

### WR-02: Step 1 curl example says initialize requires no auth, but omits that the session header must be saved from the response

**File:** `docs/CONNECTION.md:70-78`

**Issue:** The step correctly says "Save the `Mcp-Session-Id` header value from the response." However, it does not show the operator how to do this with curl, and the example does not use `-i` or `-D -` to expose response headers. An operator running the example verbatim will see only the JSON body with no visible `Mcp-Session-Id` header and will not know where to obtain the session ID for Steps 2 and 3.

**Fix:** Update the Step 1 example to expose response headers:
```bash
curl -i -X POST https://mcp.yourdomain.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
# Copy the Mcp-Session-Id value from the response headers above
```

---

### WR-03: `KEY-MANAGEMENT.md` Docker commands omit `pipenv` but give no explanation for local use

**File:** `docs/KEY-MANAGEMENT.md:79-84`

**Issue:** The Docker section uses `python scripts/manage_keys.py` (no `pipenv`), which is correct inside the container (plain Python). However, the non-Docker section at lines 13–39 uses `pipenv run py scripts/manage_keys.py`, which is the correct local form per `CLAUDE.md`. The docs do note "No `pipenv` prefix needed inside the container" at line 84, but the discrepancy between `py` (Python Launcher, Windows) and `python` (Linux standard) is not called out. On Linux, `python` is the correct command; `pipenv run py` is the Windows-specific form used in this project's development environment. An operator on Linux running the local (non-Docker) commands with `py` instead of `python3` may get "command not found".

**Fix:** Add a note clarifying that `pipenv run py` is for the local dev environment on Windows. For Linux operators running outside Docker, the equivalent is:
```bash
pipenv run python scripts/manage_keys.py create --name alice
```
Or document that outside the container on Linux, the operator should use the pipenv-managed Python directly.

---

## Info

### IN-01: `KEY-MANAGEMENT.md` `AUTH_DB_PATH` default description is slightly misleading

**File:** `docs/KEY-MANAGEMENT.md:7`

**Issue:** The doc states the key database defaults to `auth.db` in the project root. In Docker deployments (which is the primary deployment model documented), `AUTH_DB_PATH` is set to `/data/auth.db` via the Dockerfile. The "project root" default only applies to local development runs. The Docker Usage section at line 84 correctly states `/data/auth.db`, but the Overview section does not distinguish the two contexts, which can confuse operators.

**Fix:** Rephrase the overview to distinguish contexts:
> The key database is a SQLite file at the path specified by `AUTH_DB_PATH`. In Docker deployments, this is fixed at `/data/auth.db` (set in the Dockerfile). For local development runs, it defaults to `auth.db` in the project root.

---

### IN-02: `README.md` link table references `infra/SETUP.md` but this file is in the `infra/` subdirectory not docs

**File:** `README.md:17`

**Issue:** The README Guides table correctly links `[Infrastructure Setup](infra/SETUP.md)`. This is accurate and the file exists. No change needed here — this is a confirmation that the cross-reference is correct and `DEPLOY.md`'s reference `[infra/SETUP.md](../infra/SETUP.md)` (line 85) is also correct. Both links resolve properly from their respective file locations. This item is noted to confirm the cross-references were verified.

**Fix:** No action required.

---

_Reviewed: 2026-04-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
