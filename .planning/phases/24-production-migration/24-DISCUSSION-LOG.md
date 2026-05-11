# Phase 24: Production Migration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-08
**Phase:** 24-production-migration
**Areas discussed:** Search retrieval API, Speaker filter strategy, Weaviate config module, Phase 6 embed_fn source, Resume skip check, Loader lifecycle, get_talk fetch strategy, server.py lifespan teardown, Filter construction, test_phase6.py breakage, AppContext shape, Startup validation, generate_verification_report

---

## Search Retrieval API

| Option | Description | Selected |
|--------|-------------|----------|
| Extend WeaviateLoader | Add query_with_properties() to WeaviateLoader; server.py uses it as client | |
| server.py queries Weaviate directly | server.py calls weaviate.connect_to_local() itself; WeaviateLoader untouched | ✓ |

**User's choice:** server.py queries Weaviate directly
**Notes:** User clarified that WeaviateLoader is a loader — a step in the pipeline write path. It should remain as a loader, not be extended to serve server read queries. This mirrors how server.py used get_chromadb_client() directly, not through any loader class.

---

## Speaker Filter Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Native Weaviate filter | Filter.by_property("speaker_name").like() in the near_vector call; removes pre-fetch-4× | ✓ |
| Keep Python post-filter | Fetch 4× results, filter by speaker_name in Python after query | |

**User's choice:** Native Weaviate filter
**Notes:** The ChromaDB post-filter was a documented bug workaround (ChromaDB 1.5.5 broken text filters). Weaviate doesn't have this bug. Native filter removes the over-fetch workaround entirely.

---

## Weaviate Config Module

| Option | Description | Selected |
|--------|-------------|----------|
| New config/weaviate_client.py | get_weaviate_client() reads WEAVIATE_HOST/PORT/GRPC_PORT; centralizes connection | ✓ |
| Inline in each caller | Each caller reads env vars and connects directly; fewer files | |

**User's choice:** New config/weaviate_client.py
**Notes:** Mirrors the deleted config/chromadb_client.py pattern. Single place for Weaviate connection config.

---

## Phase 6 embed_fn Source

| Option | Description | Selected |
|--------|-------------|----------|
| Caller provides WeaviateLoader | run_pipeline.py creates WeaviateLoader with embed_fn, passes to load_talk_bundles | ✓ |
| Loader creates internally | load_talk_bundles reads env vars and creates WeaviateLoader itself | |

**User's choice:** Caller provides WeaviateLoader
**Notes:** User asked to check git history for the original phase6_chromadb_loader.py signature. Found: `load_talk_bundles(bundles, client: chromadb.ClientAPI, embedding_fn=None)` — caller always provided the client. The Weaviate equivalent is caller provides WeaviateLoader (which bundles both client and embed_fn). Stateless function, same pattern.

---

## Resume Skip Check

| Option | Description | Selected |
|--------|-------------|----------|
| Add talk_exists() to WeaviateLoader | loader.talk_exists(talk_id) queries by doc_id_str property | ✓ |
| run_pipeline.py queries Weaviate directly | Separate connection in run_pipeline.py for skip check | |

**User's choice:** Add talk_exists() to WeaviateLoader
**Notes:** Keeps Weaviate query logic encapsulated. run_pipeline.py calls loader.talk_exists(talk_id) — clean analog to talks_col.get(ids=[...]).

---

## Loader Lifecycle (run_pipeline.py)

| Option | Description | Selected |
|--------|-------------|----------|
| Context manager — with WeaviateLoader(...) as loader | WeaviateLoader already has __enter__/__exit__; guarantees close() | ✓ |
| try/finally in main() | Explicit loader = WeaviateLoader(...); finally: loader.close() | |

**User's choice:** Context manager
**Notes:** WeaviateLoader already implements __enter__/__exit__. Zero new code needed. Guarantees close() on both normal exit and exception.

---

## get_talk Fetch Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| fetch_objects with property filters | Filter by doc_id_str for talk; filter by talk_id INT for paragraphs | ✓ |
| You decide | Claude picks at planning time based on Weaviate v4 docs | |

**User's choice:** fetch_objects with property filters
**Notes:** User noted to verify correct value types within .equal() (string vs int) — researcher to confirm against Weaviate v4 client docs.

---

## server.py Lifespan Teardown

| Option | Description | Selected |
|--------|-------------|----------|
| finally block in _lifespan | app_ctx.client.close() in finally; explicit cleanup | ✓ |
| You decide | Claude picks at planning time | |

**User's choice:** finally block in _lifespan
**Notes:** Clean, explicit, no new abstractions. FastMCP lifespan is an async generator — finally block runs at server shutdown.

---

## Filter Construction in server.py

| Option | Description | Selected |
|--------|-------------|----------|
| Single _build_weaviate_filters helper | Replaces _build_where_filter; combines year + season + speaker into one Filter | ✓ |
| Keep year/season separate from speaker | Two separate filter paths; mirrors current structure | |

**User's choice:** Single _build_weaviate_filters helper
**Notes:** Since all three filters are now native Weaviate Filters (speaker no longer needs post-filter), combining them into one helper is cleaner than maintaining two separate paths.

---

## test_phase6.py Breakage

| Option | Description | Selected |
|--------|-------------|----------|
| Skip with pytest.mark.skip | Mark file as skipped; keeps as historical reference | |
| Delete test_phase6.py | Remove entirely; clean but loses reference | |
| Rewrite for Weaviate | Full rewrite with Weaviate fixtures | ✓ |

**User's choice:** Rewrite for Weaviate — scope expanded
**Notes:** SPEC.md had this as out of scope, but user decided to expand scope. Full rewrite using weaviate-embedded as the test fixture (see below).

---

## Test Fixture for test_phase6.py

| Option | Description | Selected |
|--------|-------------|----------|
| weaviate-embedded | weaviate.connect_to_embedded() — in-process binary, no Docker | ✓ |
| Require live Docker Weaviate | Tests connect to localhost:8080; requires benchmark stack running | |
| Mock WeaviateLoader | Patch with mock — fast but tests the mock not the integration | |

**User's choice:** weaviate-embedded
**Notes:** User asked what weaviate-embedded is. Explained: it downloads and runs a real Weaviate binary as a subprocess (~100MB, cached after first run), returns standard WeaviateClient. Direct analog to chromadb.EphemeralClient(). First run requires internet access; subsequent runs use ~/.cache/weaviate-embedded.

---

## AppContext Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Just the weaviate client | AppContext.client: weaviate.WeaviateClient; no collections dict | ✓ |
| Keep collections dict | AppContext holds both client and pre-built collection handles | |

**User's choice:** Just the weaviate client
**Notes:** client.collections.use() is a free lightweight handle — no benefit to pre-loading. Removes the collections dict entirely.

---

## Startup Collection Validation

| Option | Description | Selected |
|--------|-------------|----------|
| aggregate.over_all() count check | exists() check + aggregate count; fail-fast SystemExit(1) | ✓ |
| You decide | Claude picks at planning time | |

**User's choice:** aggregate.over_all() count check
**Notes:** Same fail-fast guard semantics as the ChromaDB _load_collections. Uses Weaviate v4 aggregate API instead of col.count().

---

## generate_verification_report()

| Option | Description | Selected |
|--------|-------------|----------|
| Include Weaviate equivalent | Uses aggregate.over_all() counts; useful for human-gated Req 7 | ✓ |
| Drop it | Not used by run_pipeline.py; keep phase6 loader minimal | |

**User's choice:** Include Weaviate equivalent
**Notes:** Manual-use function for the human-gated acceptance check. Not called by run_pipeline.py but useful for verifying the full pipeline run completed successfully.

---

## Claude's Discretion

- Exact Weaviate v4 API calls for fetch_objects — researcher verifies .equal() argument types
- generate_verification_report() scope — whether to include FK spot checks or just collection counts
- WEAVIATE_BATCH_SIZE value — researcher recommends based on Weaviate batch characteristics
- Internal structure of rewritten test_phase6.py — which test cases to carry over, drop, or add

## Deferred Ideas

None — discussion stayed within phase scope.

---

# Update Session — 2026-05-11

**Areas discussed:** Orchestrator tests (D-20), Benchmark deps fate (D-21), Docker image version (D-22)

---

## Orchestrator tests (D-20)

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal patch | Replace 9 `get_chromadb_client` patches with `WeaviateLoader` mocks. Keep existing test structure. | ✓ |
| Full rewrite | Full Weaviate-native rewrite alongside `test_phase6.py`. More work, consistent approach. | |
| Skip/xfail | Mark 9 affected tests as `pytest.mark.skip`. Deferred indefinitely. | |

**User's choice:** Minimal patch
**Notes:** User initially leaned toward full rewrite but wanted help deciding. After tradeoff analysis (orchestration logic doesn't change, only mock target changes; full rewrite risk vs. SPEC boundary; deferred cleanup phases often don't ship), user selected minimal patch. Full rewrite deferred to optional Phase 24.1.

---

## Benchmark deps fate (D-21)

| Option | Description | Selected |
|--------|-------------|----------|
| Move to [dev-packages] | `chromadb` and `qdrant-client` move to dev section. Benchmark loaders stay importable. | ✓ |
| Remove from Pipfile entirely | Benchmark is done. Fully remove both. Benchmark loaders become unimportable. | |

**User's choice:** Move to [dev-packages]
**Notes:** User wants benchmark infrastructure to remain importable in dev even though Phase 23 is complete. Supersedes prior note in CONTEXT.md that suggested chromadb might be removable from dev entirely.

---

## Docker image version (D-22)

| Option | Description | Selected |
|--------|-------------|----------|
| Pin to 1.37.1 | Same version validated in Phase 23 benchmark against 5,838 talks. Reproducible deploys. | ✓ |
| Use latest tag | Always pulls most recent stable release. Risk of breaking changes on `docker compose pull`. | |

**User's choice:** Pin to 1.37.1
**Notes:** No hesitation. Same version proven in benchmark.

---

## Deferred Ideas (update session)

- **Phase 24.1 (optional):** Full Weaviate-native rewrite of `tests/test_phase6_orchestrator.py`. User expressed interest but agreed to defer after tradeoff analysis.
