---
phase: 24-production-migration
plan: 03
subsystem: server
tags: [weaviate, server, mcp, migration, vector-db]
status: complete

# Dependency graph
requires:
  - phase: 24-01
    provides: config/weaviate_client.py with get_weaviate_client() factory
  - phase: 24-04
    provides: WEAVIATE_COLLECTION_NAMES PascalCase constants (indirect context)
provides:
  - server.py connected to Weaviate (zero chromadb references)
  - _build_weaviate_filters() native Filter-based speaker/year/season filtering
  - health_handler checking /v1/.well-known/ready via HTTP GET
  - _SNIPPET_PROP dict for per-collection snippet extraction
affects: [MIGR-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_SNIPPET_PROP dict pattern: maps collection key to lambda that extracts meaningful text snippet from Weaviate properties dict"
    - "app_ctx=None before try block in _lifespan: prevents NameError when _startup() raises SystemExit before assignment"
    - "health_handler uses requests library HTTP GET to /v1/.well-known/ready (no gRPC client per health poll)"
    - "_build_weaviate_filters: native Filter.by_property() chaining with & operator replaces ChromaDB post-filter workaround"

key-files:
  created: []
  modified:
    - server.py

key-decisions:
  - "AppContext holds only weaviate.WeaviateClient (no collections dict) — collections.use() is free lightweight handle called inline"
  - "_startup() validates 4 PascalCase collections with fail-fast SystemExit(1) and preserves _check_ollama() call"
  - "health_handler uses HTTP GET /v1/.well-known/ready via requests library, not gRPC client, to avoid connection-per-health-poll overhead"
  - "_SNIPPET_PROP per-collection extractor ensures non-empty snippets for talks/citations/footnotes (not just paragraphs)"
  - "Speaker filter is native (Filter.by_property().like()) eliminating 4x over-fetch workaround from ChromaDB era"

requirements-completed:
  - MIGR-02

# Metrics
duration: 5min
completed: 2026-06-27
---

# Phase 24 Plan 03: MCP Server Weaviate Migration Summary

**server.py rewritten with zero chromadb references — all MCP tools, startup validation, and health check now use Weaviate**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-27T21:26:00Z
- **Completed:** 2026-06-27T21:31:25Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Replaced all ChromaDB imports (`chromadb`, `get_chromadb_client`, `CHROMADB_COLLECTION_NAMES`) with Weaviate equivalents (`weaviate`, `get_weaviate_client`, `Filter`, `generate_uuid5`, `requests as http_requests`)
- Rewrote `AppContext` to hold only `weaviate.WeaviateClient` (removed `collections: dict`)
- Added `_SNIPPET_PROP` module-level dict mapping collection key → property extractor lambda for non-empty snippets from all 4 collections
- Replaced `_resolve_chromadb_client()` and `_load_collections()` with unified `_startup()` that validates all 4 PascalCase Weaviate collections
- Fixed NameError risk: `_lifespan` initializes `app_ctx = None` before try block; `finally` guards `client.close()` with `if app_ctx is not None`
- Replaced `_build_where_filter()` + 4x over-fetch workaround with native `_build_weaviate_filters()` using `Filter.by_property()` API
- Updated `health_handler` to check Weaviate via HTTP GET `/v1/.well-known/ready` (requests library, no gRPC client per health poll)
- Rewrote `search` tool to use `col.query.near_vector()` with native filters and `_SNIPPET_PROP` for meaningful snippets
- Rewrote `get_talk` tool to use `fetch_object_by_id(generate_uuid5())` for O(1) talk lookup and `Filter.by_property("talk_id").equal()` for paragraphs

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite server.py for Weaviate | ff2eeb8 | server.py |

## Files Created/Modified

- `server.py` — Fully rewritten: zero chromadb references; Weaviate client via get_weaviate_client(); 4-collection PascalCase validation; native Filter-based search; _SNIPPET_PROP per-collection extraction; HTTP health check

## Acceptance Criteria Results

All 16 criteria verified:

| Criterion | Expected | Actual | Result |
|-----------|----------|--------|--------|
| `grep -ic "chromadb" server.py` | 0 | 0 | PASS |
| `from config.weaviate_client import get_weaviate_client` | 1 | 1 | PASS |
| `def _build_weaviate_filters` | 1 | 1 | PASS |
| `_build_where_filter` | 0 | 0 | PASS |
| `fetch_object_by_id` | 1 | 1 | PASS |
| `/v1/.well-known/ready` | 1 | 1 | PASS |
| `app_ctx: AppContext \| None = None` | 1 | 1 | PASS |
| `if app_ctx is not None` | 1 | 1 | PASS |
| `"weaviate"` (health key) | >=1 | 2 | PASS |
| `collections: dict` | 0 | 0 | PASS |
| `fetch_n = min` | 0 | 0 | PASS |
| `app.client.collections.use` | >=2 | 3 | PASS |
| `app.collections` (old pattern) | 0 | 0 | PASS |
| `_SNIPPET_PROP` | >=2 | 2 | PASS |
| `import requests as http_requests` | 1 | 1 | PASS |
| `_check_ollama` | >=1 | 3 | PASS |

## Decisions Made

- `AppContext.collections` dict removed per D-02 — each tool calls `app.client.collections.use()` inline (free lightweight handle, not a connection)
- `_startup()` calls `_check_ollama()` after Weaviate is validated — Ollama check is non-fatal (consistent with prior behavior)
- `health_handler` reads `WEAVIATE_HOST`/`WEAVIATE_PORT` env vars at call time — same vars used by `get_weaviate_client()` for consistency
- `_matches_speaker()` function removed (dead code after native speaker filter via `Filter.by_property().like()`)

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new trust boundaries introduced. The speaker filter now uses Weaviate's parameterized `Filter.by_property().like(f"*{speaker}*")` — the wildcard pattern is a typed data value passed to the Filter API, not string-interpolated into a query language. This satisfies T-24-03-01 (mitigate disposition from threat register).

## Known Stubs

None — all 4 collection paths are wired to real Weaviate queries. No placeholder data.

## Self-Check: PASSED

- `grep -ic "chromadb" server.py` → 0
- `pipenv run py -m py_compile server.py` → Syntax OK
- `from config.weaviate_client import get_weaviate_client` → 1 match
- `def _build_weaviate_filters` → 1 match
- `app_ctx: AppContext | None = None` → 1 match
- `/v1/.well-known/ready` → 1 match
- `_SNIPPET_PROP` → 2 matches
- `_check_ollama` → 3 matches (definition + 2 calls)
- Commit ff2eeb8 exists in git log
