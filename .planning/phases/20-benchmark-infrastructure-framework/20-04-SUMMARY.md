---
phase: 20-benchmark-infrastructure-framework
plan: "04"
subsystem: infra
tags: [docker-compose, chromadb, weaviate, qdrant, vector-db, benchmark, healthcheck]

# Dependency graph
requires:
  - phase: 20-benchmark-infrastructure-framework
    plan: "01"
    provides: "loaders/ and benchmark/ package markers — confirms package layout before infra is needed"
provides:
  - "infra/docker-compose.vector-dbs.yml — single-command local stack for ChromaDB, Weaviate, and Qdrant"
affects:
  - "Phase 21 benchmark loaders — need all three DBs running before data can be loaded"
  - "Phase 22 benchmark runner — needs healthy services to execute query workloads"

# Tech tracking
tech-stack:
  added:
    - "chromadb/chroma:1.5.7 (Docker image — pinned)"
    - "cr.weaviate.io/semitechnologies/weaviate:1.37.1 (Docker image — pinned)"
    - "qdrant/qdrant:v1.17.1 (Docker image — pinned)"
  patterns:
    - "Loopback-only port binding (127.0.0.1:HOST:CONTAINER) for local dev security isolation"
    - "Dedicated benchmark network separate from production proxy network"
    - "Pinned image tags — no :latest allowed"
    - "All services use restart: unless-stopped and container_name"

key-files:
  created:
    - infra/docker-compose.vector-dbs.yml
  modified: []

key-decisions:
  - "Used /api/v2/heartbeat for ChromaDB healthcheck — v1 endpoint is deprecated as of ChromaDB 1.x"
  - "Weaviate healthcheck uses wget not curl — curl is absent from the official Weaviate container image"
  - "Qdrant healthcheck targets port 6333 not 6334 — 6334 is gRPC-only, healthz is HTTP-only"
  - "All ports bound to 127.0.0.1 loopback — prevents remote access on shared/multi-user machines (T-20-04-01)"
  - "benchmark network isolated from production proxy network — no cross-stack references (T-20-04-03)"

patterns-established:
  - "Vector DB Compose pattern: pinned tags + loopback ports + dedicated network + named volumes + healthchecks"

requirements-completed:
  - EVAL-01

# Metrics
duration: "~20 min (including checkpoint verification)"
completed: "2026-04-20"
tasks_completed: 1
tasks_total: 1
files_created: 1
files_modified: 0
---

# Phase 20 Plan 04: Vector DB Docker Compose Stack Summary

**Docker Compose stack for ChromaDB 1.5.7, Weaviate 1.37.1, and Qdrant v1.17.1 with loopback-bound ports, healthchecks, and an isolated benchmark network.**

## Performance

- **Duration:** ~20 min (including human-verify checkpoint)
- **Started:** 2026-04-20
- **Completed:** 2026-04-20
- **Tasks:** 1 (+ 1 checkpoint)
- **Files modified:** 1

## Accomplishments

- Created `infra/docker-compose.vector-dbs.yml` — all three vector DBs start with `docker compose -f infra/docker-compose.vector-dbs.yml up -d`
- All three healthcheck endpoints verified returning HTTP 200 by user during checkpoint
- All ports bound to 127.0.0.1 (loopback only) — satisfies T-20-04-01 threat mitigation
- benchmark network isolated from production proxy network — satisfies T-20-04-03 threat mitigation
- EVAL-01 requirement satisfied: local vector DB environment is one-command ready

## Task Commits

Each task was committed atomically:

1. **Task 1: Create infra/docker-compose.vector-dbs.yml** - `599ddf5` (feat)
2. **Fix: ChromaDB /api/v2/heartbeat (v1 deprecated)** - `baaa068` (fix — post-checkpoint deviation)

## Files Created/Modified

- `infra/docker-compose.vector-dbs.yml` — Docker Compose stack with ChromaDB, Weaviate, Qdrant services; pinned image tags; loopback port bindings; healthchecks; benchmark network

## Decisions Made

- **ChromaDB healthcheck endpoint:** Used `/api/v2/heartbeat` (not v1) — user confirmed during checkpoint review that v1 is deprecated in ChromaDB 1.x. Updated post-checkpoint before SUMMARY.
- **Weaviate uses wget:** curl is not present in the official Weaviate container image; wget is.
- **Qdrant HTTP port:** Healthcheck targets 6333 (HTTP REST); port 6334 is gRPC-only and does not serve `/healthz`.
- **Loopback binding:** All ports use `127.0.0.1:HOST:CONTAINER` form — prevents external access on shared machines, consistent with project security posture.
- **Isolated network:** `name: benchmark` with `driver: bridge` — never joins the production `proxy` network.

## Deviations from Plan

### Post-checkpoint Fix

**1. [User-noted Deprecation] Updated ChromaDB healthcheck from /api/v1/heartbeat to /api/v2/heartbeat**
- **Found during:** Human-verify checkpoint — user noted v1 endpoint is deprecated
- **Issue:** Plan spec explicitly stated "use /api/v1/heartbeat (NOT /api/v2/heartbeat)" based on RESEARCH.md data that predated confirmation of deprecation. The v1 endpoint has been deprecated in ChromaDB 1.x; v2 is the correct endpoint.
- **Fix:** Updated `infra/docker-compose.vector-dbs.yml` line 13: `api/v1/heartbeat` → `api/v2/heartbeat`
- **Files modified:** `infra/docker-compose.vector-dbs.yml`
- **Verification:** User confirmed all three health endpoints returned HTTP 200 during checkpoint (v1 was still reachable at verification time; v2 future-proofs the config)
- **Committed in:** `baaa068` (`fix(20-04): use chromadb /api/v2/heartbeat (v1 deprecated)`)

---

**Total deviations:** 1 post-checkpoint fix (user-noted API deprecation)
**Impact on plan:** Minimal — single-line URL update. No structural changes. Future-proofs the healthcheck as ChromaDB v1 endpoint is deprecated.

## Issues Encountered

None during implementation. The YAML was valid on first write (`docker compose config --quiet` exited 0). All three services passed health verification during checkpoint.

## User Setup Required

None — no external secrets or credentials required. Stack is fully self-contained with anonymous access enabled on all three DBs.

To start the stack:
```bash
docker compose -f infra/docker-compose.vector-dbs.yml up -d
```

To stop:
```bash
docker compose -f infra/docker-compose.vector-dbs.yml down
```

## Next Phase Readiness

- Phase 21 (benchmark loaders) can now target `localhost:8000` (ChromaDB), `localhost:8080` (Weaviate), and `localhost:6333` (Qdrant)
- Phase 22 (benchmark runner) has all three DBs available for query workload execution
- No blockers — EVAL-01 satisfied

## Threat Surface

| Threat | Mitigation | Status |
|--------|-----------|--------|
| T-20-04-01: Vector DB ports on non-loopback | All ports use `127.0.0.1:PORT:PORT` binding | Mitigated |
| T-20-04-02: No auth on benchmark DBs | Accepted — local dev scope, anonymous access per SPEC | Accepted |
| T-20-04-03: benchmark network joining proxy network | `name: benchmark` with no cross-references to proxy network | Mitigated |

## Threat Flags

None — no new network endpoints, auth paths, or schema changes beyond what the plan's threat model already covers.

## Self-Check: PASSED

Files exist:
- FOUND: infra/docker-compose.vector-dbs.yml

Commits exist:
- FOUND: 599ddf5 (feat — initial compose file)
- FOUND: baaa068 (fix — api/v2/heartbeat)

---
*Phase: 20-benchmark-infrastructure-framework*
*Completed: 2026-04-20*
