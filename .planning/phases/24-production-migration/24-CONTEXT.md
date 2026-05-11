# Phase 24: Production Migration - Context

**Gathered:** 2026-05-08 (updated 2026-05-11)
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace ChromaDB with Weaviate across all production code paths — `server.py` (MCP server),
`extractors/phase6_weaviate_loader.py` (pipeline Phase 6 loader), `scripts/run_pipeline.py`
(pipeline orchestrator), `config/pipeline_config.py` (constants), and `docker-compose.yml`
(Docker stack). ChromaDB is fully removed from all production code paths. All 5,838 GC talks
must be searchable via MCP tools against Weaviate.

WeaviateLoader (`loaders/weaviate_loader.py`) is the **write path** — a benchmark loader that
Phase 6 wraps. It is NOT used by `server.py`. `server.py` is the **read path** and connects
to Weaviate directly.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**8 requirements are locked.** See `24-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `24-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- Create `extractors/phase6_weaviate_loader.py`
- Update `scripts/run_pipeline.py` (swap ChromaDB imports → Weaviate loader)
- Replace `CHROMADB_COLLECTION_NAMES` with `WEAVIATE_COLLECTION_NAMES` in `config/pipeline_config.py`
- Update `server.py` (swap ChromaDB client → Weaviate client, update startup validation and health check)
- Delete `config/chromadb_client.py`
- Remove `chromadb` and `qdrant-client` from Pipfile `[packages]` (both are benchmark-only; neither has a production caller)
- Add `weaviate` service to `docker-compose.yml`
- Update `.env.example` (WEAVIATE_* vars in, CHROMADB_* vars out)
- Update CLAUDE.md project structure index (add new file, remove deleted file)

**Out of scope (from SPEC.md):**
- `loaders/chromadb_loader.py` — benchmark infrastructure; stays untouched
- `benchmark/` directory — no changes
- `infra/docker-compose.vector-dbs.yml` — benchmark stack; no changes
- Docker image rebuild and push — user's responsibility
- Weaviate schema migration tooling — schema finalized in Phase 21/23
- Re-embedding — same `nomic-embed-text` model
- Auth changes — ScaleKit/OAuth configuration unchanged
- Migrating SQLite — read-only source stays unchanged

</spec_lock>

<decisions>
## Implementation Decisions

### server.py — Weaviate Client Architecture
- **D-01:** `server.py` queries Weaviate **directly** via `weaviate.connect_to_local()`. `WeaviateLoader` is the write path (pipeline loader) and is **never imported by `server.py`**. This mirrors how `server.py` used `get_chromadb_client()` directly — not through any loader class.
- **D-02:** `AppContext` holds **only** the weaviate client — no `collections` dict. `search` and `get_talk` call `app.client.collections.use("ConferenceTalkParagraphs")` (or the appropriate collection name per D-18) inline. `client.collections.use()` is a free lightweight handle, not a connection.
  ```python
  @dataclass
  class AppContext:
      client: weaviate.WeaviateClient
  ```
- **D-03:** Weaviate client connection is provided by a new `config/weaviate_client.py` factory: `get_weaviate_client()` reads `WEAVIATE_HOST`, `WEAVIATE_PORT`, `WEAVIATE_GRPC_PORT` env vars and calls `weaviate.connect_to_local()`. Mirrors the deleted `config/chromadb_client.py` pattern.

### server.py — Startup Validation
- **D-04:** `_startup()` validates all 4 Weaviate collections are present and non-empty using `client.collections.exists(name)` + `collection.aggregate.over_all(total_count=True).total_count`. Fail-fast `SystemExit(1)` if any collection is missing or has 0 objects — same guard semantics as the ChromaDB version.
  ```python
  for name in ["ConferenceTalks", "ConferenceTalkParagraphs", "ConferenceTalkCitations", "ConferenceTalkFootnotes"]:
      if not client.collections.exists(name):
          sys.exit(1)
      count = client.collections.use(name).aggregate.over_all(total_count=True).total_count
      if count == 0:
          sys.exit(1)
  ```

### server.py — Lifespan Teardown
- **D-05:** The `_lifespan` async generator adds a `finally:` block to call `app_ctx.client.close()` at server shutdown. Weaviate requires explicit close to release the gRPC connection.
  ```python
  async def _lifespan(server: FastMCP):
      app_ctx = _startup()
      try:
          yield {"app": app_ctx}
      finally:
          app_ctx.client.close()
  ```

### server.py — Search Tool Filters
- **D-06:** Replace `_build_where_filter(year, season)` with a single `_build_weaviate_filters(year, season, speaker)` helper that returns a combined Weaviate `Filter` or `None`. All three filters (year, season, speaker) use native Weaviate property filters — the ChromaDB post-filter speaker workaround is removed entirely.
  ```python
  def _build_weaviate_filters(year, season, speaker):
      conditions = []
      if year:    conditions.append(Filter.by_property("conference_year").equal(year))
      if season:  conditions.append(Filter.by_property("conference_month").equal(season))
      if speaker: conditions.append(Filter.by_property("speaker_name").like(f"*{speaker}*"))
      if not conditions: return None
      result = conditions[0]
      for c in conditions[1:]: result = result & c
      return result
  ```
- **D-07:** The pre-fetch-4× workaround (`fetch_n = min(limit * 4, 80) if speaker else limit`) is removed. Native Weaviate filter eliminates the need for over-fetching.

### server.py — get_talk Fetch Strategy
- **D-08:** `get_talk` looks up talk and paragraphs as follows:
  - Talk lookup: `fetch_object_by_id(generate_uuid5(f"talk_{talk_num}"))` — same UUID-based O(1) pattern as `talk_exists()` (D-14). No property filter scan needed; returns `None` when the talk doesn't exist.
  - Paragraph fetch: `Filter.by_property("talk_id").equal(talk_num)` via `fetch_objects(filters=..., limit=10000)` — still a property filter since we need all paragraphs for a talk, not one specific object.
  - The exact `.equal()` argument type for `talk_id` (integer) must be verified against Weaviate v4 client docs at planning time.

### config/weaviate_client.py (new file)
- **D-09:** Create `config/weaviate_client.py` with `get_weaviate_client()` reading `WEAVIATE_HOST` (default `localhost`), `WEAVIATE_PORT` (default `8080`), `WEAVIATE_GRPC_PORT` (default `50051`). Returns a connected `weaviate.WeaviateClient`. Used by `server.py` (`_startup()` and `health_handler`).

### extractors/phase6_weaviate_loader.py (new file)
- **D-10:** `load_talk_bundles(bundles: list[TalkBundle], loader: WeaviateLoader) -> dict` — caller provides the `WeaviateLoader` instance. Mirrors how the original ChromaDB phase6 loader received `client: chromadb.ClientAPI` as a parameter. The function is stateless. Uses production bulk loading (not per-talk `loader.load()` calls) — researcher/planner determines the exact Weaviate bulk API to use (e.g. `client.batch.dynamic()` or equivalent).
- **D-11:** `TalkBundle` is re-exported from `loaders.shared_transforms` (same as ChromaDB loader). No new dataclass needed.
- **D-12:** `generate_verification_report(loader: WeaviateLoader, load_summary: dict) -> dict` is included. Uses `aggregate.over_all(total_count=True).total_count` for collection counts. Includes FK spot checks: paragraph→talk and citation→paragraph, using UUID lookup via `generate_uuid5` (mirrors the ChromaDB version's `.get(ids=[...])` semantics). FK checks catch partial-insert failures where one collection loaded but another didn't — a real failure mode since Weaviate logs per-collection errors rather than rolling back atomically. Useful for the human-gated Requirement 7 acceptance check. Not called by `run_pipeline.py` — manual use only.

### scripts/run_pipeline.py — Weaviate Integration
- **D-13:** `run_pipeline.py` creates the `WeaviateLoader` as a context manager so `close()` is guaranteed:
  ```python
  with WeaviateLoader(
      host=WEAVIATE_HOST,
      port=WEAVIATE_PORT,
      embed_fn=get_embedding_function(url=resolve_ollama_url()),
  ) as loader:
      # all pipeline logic including load_talk_bundles calls
  ```
  `WeaviateLoader` already implements `__enter__`/`__exit__`.
- **D-14:** Resume/skip check uses a new `loader.talk_exists(talk_id: int) -> bool` method added to `WeaviateLoader`. Queries by UUID via `generate_uuid5(f"talk_{talk_id}")` → `fetch_object_by_id()`. UUID lookup is O(1) — faster than a property filter scan and exactly analogous to ChromaDB's direct ID lookup. Replaces the ChromaDB `talks_col.get(ids=[f"talk_{talk_id}"])` pattern.
  ```python
  # In WeaviateLoader:
  def talk_exists(self, talk_id: int) -> bool:
      from weaviate.util import generate_uuid5
      col = self._client.collections.use("ConferenceTalks")
      obj = col.query.fetch_object_by_id(generate_uuid5(f"talk_{talk_id}"))
      return obj is not None

  # In run_pipeline.py:
  if not args.force and loader.talk_exists(talk_id):
      skipped_count += 1
      continue
  ```
- **D-15:** `CHROMADB_BATCH_SIZE` → `WEAVIATE_BATCH_SIZE` in `config/pipeline_config.py`. Used as the pipeline buffer flush size (how many talks to accumulate before calling `load_talk_bundles`).

### tests/test_phase6.py — Scope Expanded
- **D-16:** `test_phase6.py` is **fully rewritten** for Weaviate (scope expanded beyond SPEC.md's deferred boundary). The ChromaDB `EphemeralClient()` fixture is replaced with `weaviate.connect_to_embedded()` — a session-scoped pytest fixture that runs a real Weaviate binary in-process, no Docker required.
  ```python
  @pytest.fixture(scope="session")
  def weaviate_client():
      with weaviate.connect_to_embedded() as client:
          yield client
  ```
- **D-17:** First run of `weaviate-embedded` downloads the Weaviate binary (~100MB, cached in `~/.cache/weaviate-embedded`). Subsequent runs use the cache. Startup adds ~2–5s per test session. CI must have internet access on first run or pre-cache the binary.

### tests/test_phase6_orchestrator.py — Minimal Patch
- **D-20:** `test_phase6_orchestrator.py` receives a **minimal patch only** — not a full rewrite. The 9 tests that use `patch.object(run_pipeline, "get_chromadb_client", ...)` will fail with `AttributeError` after `run_pipeline.py` is migrated (the attribute no longer exists). Fix: replace those 9 patches with `WeaviateLoader` context manager mocks. Preserve all existing test logic (skip behavior, batch flush, failure recording — none of that changes). SPEC exception clause: "update minimally if blocking." A full Weaviate-native rewrite is deferred to an optional Phase 24.1.

### Dependency Cleanup
- **D-21:** `chromadb` and `qdrant-client` move from `[packages]` to `[dev-packages]` in Pipfile — they are NOT removed from Pipfile entirely. `loaders/chromadb_loader.py` and `loaders/qdrant_loader.py` stay untouched (benchmark infrastructure) and remain importable in dev. Production Docker image (`pipenv install --deploy`) installs only `[packages]`, so neither package lands in the production image. This supersedes the earlier `<specifics>` note that suggested `chromadb` might be removable from dev deps entirely.

### Docker Stack — Image Version
- **D-22:** Weaviate service in `docker-compose.yml` is pinned to `cr.weaviate.io/semitechnologies/weaviate:1.37.1` — the same version validated against 5,838 talks in Phase 23 benchmark. Do not use `latest` tag. Explicit pin ensures reproducible deploys and a deliberate upgrade path.

### Weaviate Collection Names
- **D-18:** Production collection names are PascalCase conversions of the original ChromaDB names. `WeaviateLoader.COLLECTIONS` and `_ensure_schema()` are updated to use these names. The benchmark names (`Talk`, `Paragraph`, `Citation`, `Footnote`) are replaced.

  | ChromaDB (removed) | Weaviate (production) |
  |---|---|
  | `conference_talks` | `ConferenceTalks` |
  | `conference_talk_paragraphs` | `ConferenceTalkParagraphs` |
  | `conference_talk_citations` | `ConferenceTalkCitations` |
  | `conference_talk_footnotes` | `ConferenceTalkFootnotes` |

  `WEAVIATE_COLLECTION_NAMES` dict in `config/pipeline_config.py` mirrors the old `CHROMADB_COLLECTION_NAMES` structure:
  ```python
  WEAVIATE_COLLECTION_NAMES = {
      "talks": "ConferenceTalks",
      "paragraphs": "ConferenceTalkParagraphs",
      "citations": "ConferenceTalkCitations",
      "footnotes": "ConferenceTalkFootnotes",
  }
  ```

### server.py — Health Handler
- **D-19:** `health_handler` checks Weaviate via a direct HTTP GET to `http://{WEAVIATE_HOST}:{WEAVIATE_PORT}/v1/.well-known/ready` (2s timeout). No Weaviate client is created — avoids a gRPC connection per health poll. `/ready` is the correct endpoint: returns 200 only when Weaviate is fully initialized and serving requests (not just alive). Consistent with the Ollama check pattern — both are direct HTTP calls with no client lifecycle management. Response key changes from `"chromadb"` to `"weaviate"`.
  ```python
  import requests as http_requests
  host = os.environ.get("WEAVIATE_HOST", "localhost")
  port = os.environ.get("WEAVIATE_PORT", "8080")
  resp = http_requests.get(f"http://{host}:{port}/v1/.well-known/ready", timeout=2)
  if not resp.ok:
      raise RuntimeError(f"HTTP {resp.status_code}")
  ```

### Claude's Discretion
- Exact Weaviate v4 API calls for `fetch_objects` — researcher verifies `.equal()` argument types (string vs int) against official docs
- `WEAVIATE_BATCH_SIZE` value — researcher recommends based on Weaviate batch performance characteristics vs. the ChromaDB SQLite-limit-driven value (1000 was an SQLite artifact; Weaviate has no such constraint)
- Internal structure of the rewritten `test_phase6.py` — what test cases to carry over vs. drop vs. add for Weaviate

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Requirements & Decision
- `.planning/phases/24-production-migration/24-SPEC.md` — Locked requirements, boundaries, acceptance criteria. MUST read before planning.
- `benchmark/DECISION.md` — Weaviate winner declaration with full metric comparison. Why Weaviate was selected.

### Existing Weaviate Infrastructure (benchmark)
- `loaders/weaviate_loader.py` — `WeaviateLoader` class: schema (`_ensure_schema`), `load(bundle)`, `query()`, `close()`, `reset()`, `__enter__`/`__exit__`. Phase 6 wraps this. `talk_exists()` method to be added here.
- `loaders/shared_transforms.py` — `TalkBundle`, `prepare_talk_bundle_rich()`, `prepare_talk_bundle()`. Phase 6 re-exports `TalkBundle` from here.

### Existing Production Code Being Replaced
- `server.py` — Full current server implementation. All ChromaDB patterns to be replaced.
- `scripts/run_pipeline.py` — Full pipeline orchestrator. ChromaDB client, batch flush, skip check all to be replaced.
- `config/pipeline_config.py` — `CHROMADB_COLLECTION_NAMES`, `CHROMADB_BATCH_SIZE` to be replaced.
- `config/chromadb_client.py` — Factory pattern to be mirrored in new `config/weaviate_client.py`, then deleted.

### Deleted File (in git history)
- `git show 5718c96:extractors/phase6_chromadb_loader.py` — Original phase6 ChromaDB loader. Reference for `load_talk_bundles()` interface, `generate_verification_report()` structure, and return value shape.

### Docker & Environment
- `docker-compose.yml` — Current single-service stack. Weaviate service to be added.
- `.env.example` — Current ChromaDB env vars. To be replaced with `WEAVIATE_HOST`, `WEAVIATE_PORT`, `WEAVIATE_GRPC_PORT`.
- `infra/docker-compose.vector-dbs.yml` — Reference for Weaviate service definition used in benchmark (image, ports, env vars). Use as the model for the production `docker-compose.yml` Weaviate service.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `WeaviateLoader.__enter__`/`__exit__` — Already implemented. `run_pipeline.py` uses `with WeaviateLoader(...) as loader:` with no new code needed.
- `WeaviateLoader.COLLECTIONS` — Updated by Phase 24 to `["ConferenceTalks", "ConferenceTalkParagraphs", "ConferenceTalkCitations", "ConferenceTalkFootnotes"]` (D-18). Use `WEAVIATE_COLLECTION_NAMES` dict from `config/pipeline_config.py` when key-based access is needed.
- `config/ollama.py` `resolve_ollama_url()` + `get_embedding_function()` — Already used in `server.py` and `run_pipeline.py`. Phase 6 loader embed_fn comes from here.
- `loaders/shared_transforms.py` `TalkBundle` — Already the canonical type. Phase 6 loader re-exports it.

### Established Patterns
- **Fail-fast startup** (`server.py` lines 97–171): `_resolve_chromadb_client()` → `_check_ollama()` → `_load_collections()` each raise `SystemExit(1)` on failure. Weaviate startup follows this same pattern.
- **Lifespan context** (`server.py` line 277): `AppContext` yielded via `lifespan_context["app"]`. Shape changes (no `collections` dict) but the yield pattern stays.
- **Batch flush buffer** (`run_pipeline.py` lines 165–169): `processed_since_flush >= CHROMADB_BATCH_SIZE` triggers `load_talk_bundles()`. Buffer constant name changes, pattern stays.
- **Skip check guard** (`run_pipeline.py` lines 119–123): `if not args.force` → existence check → `continue`. Pattern stays, implementation swaps from ChromaDB `.get(ids=[])` to `loader.talk_exists()`.
- **`_format_search_result(document, meta)`** (`server.py` line 207): Currently receives `(str, dict)` from ChromaDB query. With Weaviate, `obj.properties` is a dict — `text` field is the document, other fields are metadata. Check property name for paragraph text (`"text"` in `WeaviateLoader._paragraph_properties()`).

### Integration Points
- `WeaviateLoader` (benchmark, `loaders/`) ← wrapped by `extractors/phase6_weaviate_loader.py` (new production loader)
- `config/weaviate_client.py` (new) ← used by `server.py` `_startup()` and `health_handler`
- `loader.talk_exists()` (new method on `WeaviateLoader`) ← called by `run_pipeline.py` skip check
- `infra/docker-compose.vector-dbs.yml` Weaviate service definition ← reference for `docker-compose.yml` Weaviate service addition

</code_context>

<specifics>
## Specific Ideas

- **`_build_weaviate_filters` preview** (from discussion): The user confirmed the exact combined-filter pattern using `&` chaining — see D-06.
- **`load_talk_bundles` signature** (from discussion): Caller provides `WeaviateLoader` as second positional argument — exact analog to original `(bundles, client, embedding_fn)` but collapsed to `(bundles, loader)` since `WeaviateLoader` bundles both.
- **Weaviate service image** (from SPEC.md): `cr.weaviate.io/semitechnologies/weaviate` — use latest stable tag at execution time (benchmark used 1.37.1 as reference).
- **`chromadb` + `qdrant-client` Pipfile disposition** (from D-21): Both move to `[dev-packages]`, not removed entirely. `loaders/chromadb_loader.py` and `loaders/qdrant_loader.py` stay importable in dev. The prior note suggesting chromadb might be removable from dev deps is superseded by D-21.

</specifics>

<deferred>
## Deferred Ideas

- **Phase 24.1 (optional):** Full Weaviate-native rewrite of `tests/test_phase6_orchestrator.py`. Phase 24 delivers a minimal patch only (D-20). If a proper rewrite is desired, a Phase 24.1 can do it cleanly after Phase 24 ships.

</deferred>

---

*Phase: 24-production-migration*
*Context gathered: 2026-05-08 (updated 2026-05-11)*
