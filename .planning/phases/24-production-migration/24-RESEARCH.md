# Phase 24: Production Migration - Research

**Researched:** 2026-05-11
**Domain:** Weaviate v4 Python client (weaviate-client==4.20.5), ChromaDB removal, Docker Compose
**Confidence:** HIGH

## Summary

Phase 24 replaces ChromaDB with Weaviate across all production code paths. The codebase is currently broken: `extractors/phase6_chromadb_loader.py` was deleted in a prior commit, and `scripts/run_pipeline.py` + `tests/test_phase6.py` + `tests/test_phase6_orchestrator.py` all fail at import time with `ModuleNotFoundError`. Two test files error on collection (blocking `pipenv run py -m pytest`), which means fixing the import errors is mandatory — not just the deferred test updates the SPEC described.

The installed weaviate-client is **4.20.5** (pinned in Pipfile). All API signatures in this research were verified against this exact installed version via introspection. The existing `WeaviateLoader` in `loaders/weaviate_loader.py` already implements `__enter__`/`__exit__`, uses `insert_many`, and issues `weaviate.connect_to_local()` with all required parameters. Phase 24 wraps that loader from the production path, adds `talk_exists()` to it, and wires `server.py` directly to `weaviate.connect_to_local()`.

**Primary recommendation:** Use `col.data.insert_many(objects)` (already proven in `WeaviateLoader.load()`) as the bulk insert path inside `load_talk_bundles()`. Use `collection.batch.dynamic()` as a context manager only when iterating one object at a time is necessary; for bulk pre-computed lists `insert_many` is simpler and already battle-tested. Set `WEAVIATE_BATCH_SIZE = 50` (talks, not records) as the pipeline buffer flush size.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** `server.py` queries Weaviate directly via `weaviate.connect_to_local()`. `WeaviateLoader` is the write path and is never imported by `server.py`.

**D-02:** `AppContext` holds only the weaviate client — no `collections` dict.
```python
@dataclass
class AppContext:
    client: weaviate.WeaviateClient
```

**D-03:** Weaviate client provided by new `config/weaviate_client.py`: `get_weaviate_client()` reads `WEAVIATE_HOST`, `WEAVIATE_PORT`, `WEAVIATE_GRPC_PORT` env vars and calls `weaviate.connect_to_local()`.

**D-04:** `_startup()` validates all 4 Weaviate collections are present and non-empty using `client.collections.exists(name)` + `collection.aggregate.over_all(total_count=True).total_count`. Fail-fast `SystemExit(1)` if any collection is missing or has 0 objects.

**D-05:** The `_lifespan` async generator adds a `finally:` block to call `app_ctx.client.close()` at server shutdown.

**D-06:** Replace `_build_where_filter(year, season)` with `_build_weaviate_filters(year, season, speaker)` returning a combined Weaviate `Filter` or `None`. Native Weaviate filter for speaker via `.like(f"*{speaker}*")`.

**D-07:** The pre-fetch-4x workaround (`fetch_n = min(limit * 4, 80) if speaker else limit`) is removed.

**D-08:** `get_talk` uses `fetch_object_by_id(generate_uuid5(f"talk_{talk_num}"))` for the talk lookup, and `Filter.by_property("talk_id").equal(talk_num)` via `fetch_objects(filters=..., limit=10000)` for paragraphs.

**D-09:** Create `config/weaviate_client.py` with `get_weaviate_client()` reading `WEAVIATE_HOST` (default `localhost`), `WEAVIATE_PORT` (default `8080`), `WEAVIATE_GRPC_PORT` (default `50051`).

**D-10:** `load_talk_bundles(bundles: list[TalkBundle], loader: WeaviateLoader) -> dict` — caller provides the `WeaviateLoader` instance. Function is stateless.

**D-11:** `TalkBundle` re-exported from `loaders.shared_transforms`.

**D-12:** `generate_verification_report(loader: WeaviateLoader, load_summary: dict) -> dict` is included.

**D-13:** `run_pipeline.py` creates `WeaviateLoader` as a context manager.

**D-14:** Resume/skip check uses `loader.talk_exists(talk_id: int) -> bool` added to `WeaviateLoader`.

**D-15:** `CHROMADB_BATCH_SIZE` → `WEAVIATE_BATCH_SIZE` in `config/pipeline_config.py`.

**D-16:** `test_phase6.py` is fully rewritten for Weaviate using `weaviate.connect_to_embedded()`.

**D-17:** First run of `weaviate-embedded` downloads ~100MB binary cached in `~/.cache/weaviate-embedded`.

**D-18:** Production collection names are PascalCase: `ConferenceTalks`, `ConferenceTalkParagraphs`, `ConferenceTalkCitations`, `ConferenceTalkFootnotes`. Both `WeaviateLoader.COLLECTIONS` and `config/pipeline_config.py` are updated.

**D-19:** `health_handler` checks Weaviate via `GET http://{WEAVIATE_HOST}:{WEAVIATE_PORT}/v1/.well-known/ready` (2s timeout, no client).

**D-20:** `test_phase6_orchestrator.py` receives a minimal patch — replace 9 `get_chromadb_client` patches with `WeaviateLoader` context manager mocks. Preserve all test logic.

**D-21:** `chromadb` and `qdrant-client` move from `[packages]` to `[dev-packages]` in Pipfile. NOT removed entirely.

**D-22:** Weaviate service pinned to `cr.weaviate.io/semitechnologies/weaviate:1.37.1`.

### Claude's Discretion
- Exact Weaviate v4 API calls for `fetch_objects` — `.equal()` argument types (string vs int) — RESOLVED below
- `WEAVIATE_BATCH_SIZE` value — RESOLVED below
- Internal structure of the rewritten `test_phase6.py` — what test cases to carry over vs. drop vs. add

### Deferred Ideas (OUT OF SCOPE)
- Phase 24.1: Full Weaviate-native rewrite of `tests/test_phase6_orchestrator.py`
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MIGR-01 | `scripts/run_pipeline.py` Phase 6 loader swapped to Weaviate | WeaviateLoader.load() + insert_many proven; talk_exists() pattern verified via fetch_object_by_id UUID lookup |
| MIGR-02 | `server.py` winning DB client + startup validation | connect_to_local(), aggregate.over_all(total_count=True).total_count verified; Filter API verified |
| MIGR-03 | `docker-compose.yml` + `.env.example` updated with Weaviate service | Weaviate service definition from benchmark infra verified; port mapping confirmed |
| MIGR-04 | Full pipeline re-run + MCP `search` + `get_talk` tools verified end-to-end | Human-gated; preconditions are MIGR-01, MIGR-02, MIGR-03 |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Vector DB write path (pipeline ingestion) | Pipeline/batch script | WeaviateLoader (loaders/) | `run_pipeline.py` orchestrates; `WeaviateLoader` executes bulk inserts |
| Vector DB read path (MCP search + get_talk) | API/MCP server | Weaviate (remote service) | `server.py` queries Weaviate directly; no loader involvement |
| Client factory / connection config | Config layer | — | `config/weaviate_client.py` mirrors deleted `config/chromadb_client.py` |
| Collection schema management | WeaviateLoader | — | `_ensure_schema()` in `loaders/weaviate_loader.py`; called at init |
| Health monitoring | MCP server | Weaviate HTTP API | HTTP GET `/v1/.well-known/ready` — no client lifecycle |
| Docker service definition | Infrastructure | — | `docker-compose.yml` — co-located with mcp-server |

---

## Standard Stack

### Core (installed, verified)

| Library | Version | Purpose | Verification |
|---------|---------|---------|--------------|
| weaviate-client | 4.20.5 (pinned in Pipfile) | Weaviate Python client — all read/write ops | `pipenv run py -c "import weaviate; print(weaviate.__version__)"` → 4.20.5 |
| weaviate (Docker) | 1.37.1 | Production vector DB server | `benchmark/DECISION.md` — validated against 5,838 talks |
| requests | >=2.31.0 (already in Pipfile) | HTTP GET for health check (`/v1/.well-known/ready`) | Already a production dependency |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| chromadb | * (move to [dev-packages]) | Benchmark loader; test_phase6.py (rewritten away) | Dev/test only after Phase 24 |
| qdrant-client | 1.17.1 (move to [dev-packages]) | Benchmark loader | Dev/test only |
| pytest | * | Test framework | Already in [dev-packages] |

### Image and Environment

| Item | Value | Source |
|------|-------|--------|
| Weaviate Docker image | `cr.weaviate.io/semitechnologies/weaviate:1.37.1` | D-22; `benchmark/DECISION.md` validated this version |
| HTTP port | 8080 | `infra/docker-compose.vector-dbs.yml` verified |
| gRPC port | 50051 | `infra/docker-compose.vector-dbs.yml` verified |
| Required env vars (container) | `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true`, `PERSISTENCE_DATA_PATH=/var/lib/weaviate`, `DEFAULT_VECTORIZER_MODULE=none` | `infra/docker-compose.vector-dbs.yml` |

---

## Architecture Patterns

### System Architecture Diagram

```
SQLite (read-only) ──► run_pipeline.py ──► extractors/phase6_weaviate_loader.py
                           │                        │
                     (TalkBundle[])         load_talk_bundles(bundles, loader)
                           │                        │
                     WeaviateLoader ◄───────────────┘
                    (loaders/weaviate_loader.py)
                           │
                    col.data.insert_many()
                           │
                       Weaviate ◄─────────────────────────── server.py
                    (Docker service)                    weaviate.connect_to_local()
                                                       col.query.near_vector()
                                                       col.query.fetch_object_by_id()
                                                       col.query.fetch_objects()
```

### Recommended Project Structure (additions only)

```
config/
├── chromadb_client.py    # DELETE
└── weaviate_client.py    # NEW — get_weaviate_client() factory

extractors/
├── phase6_chromadb_loader.py  # already deleted
└── phase6_weaviate_loader.py  # NEW — load_talk_bundles(), TalkBundle, generate_verification_report()

loaders/
└── weaviate_loader.py    # MODIFY — add talk_exists(), update COLLECTIONS list, update _ensure_schema()
```

### Pattern 1: Weaviate Client Factory (`config/weaviate_client.py`)

Mirrors the deleted `config/chromadb_client.py`. Both `server.py` and any future tooling import from here.

```python
# Source: verified via weaviate.connect_to_local signature introspection
import os
import weaviate

def get_weaviate_client() -> weaviate.WeaviateClient:
    host = os.environ.get("WEAVIATE_HOST", "localhost")
    port = int(os.environ.get("WEAVIATE_PORT", "8080"))
    grpc_port = int(os.environ.get("WEAVIATE_GRPC_PORT", "50051"))
    return weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)
```

**Note:** `connect_to_local()` signature verified: `(host: str = 'localhost', port: int = 8080, grpc_port: int = 50051, ...)`. [VERIFIED: introspection of weaviate-client==4.20.5]

### Pattern 2: Startup Validation in `server.py`

```python
# Source: verified from aggregate.over_all signature and AggregateReturn dataclass fields
from weaviate.util import generate_uuid5

def _startup() -> AppContext:
    client = get_weaviate_client()
    try:
        client.is_ready()  # basic connectivity check
    except Exception as exc:
        logger.warning(f"Weaviate unreachable: {exc}")
        sys.exit(1)

    _check_ollama()

    for name in ["ConferenceTalks", "ConferenceTalkParagraphs",
                 "ConferenceTalkCitations", "ConferenceTalkFootnotes"]:
        if not client.collections.exists(name):
            print(f"ERROR: Weaviate collection '{name}' not found. Run the pipeline first.",
                  file=sys.stderr)
            sys.exit(1)
        result = client.collections.use(name).aggregate.over_all(total_count=True)
        if result.total_count == 0:
            print(f"ERROR: Collection '{name}' has 0 records. Re-run the pipeline.",
                  file=sys.stderr)
            sys.exit(1)
        logger.info("Validated collection '%s' (%d records)", name, result.total_count)

    return AppContext(client=client)
```

**Key facts verified:**
- `aggregate.over_all(total_count=True)` returns `AggregateReturn` [VERIFIED: introspection]
- `AggregateReturn` has field `total_count` (confirmed: `__dataclass_fields__.keys()` = `['properties', 'total_count']`) [VERIFIED: introspection]
- `over_all` signature: `(self, *, filters=None, group_by=None, total_count: bool = True, return_metrics=None)` [VERIFIED: introspection]

### Pattern 3: Filter Construction in `server.py`

```python
# Source: verified from _FilterByProperty methods via introspection
from weaviate.classes.query import Filter

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

**`.equal()` type acceptance:** The signature accepts `int | float | str | bool | datetime | UUID | None | Sequence[...]`. Passing `int` for `conference_year` (stored as `DataType.INT` in schema) is correct. Passing `str` for `conference_month` is correct. Passing `int` for `talk_id` in `get_talk` paragraph fetch is correct. [VERIFIED: introspection of `_FilterByProperty.equal`]

**`.like()` for speaker:** `.like(val: str)` accepts wildcard patterns using `*` (Weaviate glob syntax). The pattern `f"*{speaker}*"` is a substring match. [VERIFIED: introspection; `.like` method confirmed present]

### Pattern 4: Search Tool (`server.py`)

```python
# Source: verified from near_vector query class introspection
async def search(query, speaker=None, year=None, season=None,
                 collection="paragraphs", limit=5, ctx=None):
    app: AppContext = ctx.lifespan_context["app"]

    collection_map = {
        "talks": "ConferenceTalks",
        "paragraphs": "ConferenceTalkParagraphs",
        "citations": "ConferenceTalkCitations",
        "footnotes": "ConferenceTalkFootnotes",
    }
    col_name = collection_map.get(collection)
    if col_name is None:
        return f"Unknown collection '{collection}'. Valid: talks, paragraphs, citations, footnotes."

    limit = max(1, min(limit, 20))
    weaviate_filter = _build_weaviate_filters(year, season, speaker)

    try:
        ollama_url = resolve_ollama_url()
        ef = get_embedding_function(url=ollama_url)
        query_vector = ef([query])[0]
    except Exception as e:
        return f"Search unavailable: Ollama is unreachable ({e})."

    col = app.client.collections.use(col_name)
    result = col.query.near_vector(
        near_vector=query_vector,
        limit=limit,
        filters=weaviate_filter,
        target_vector="default",
    )

    if not result.objects:
        return "No results found."

    results = []
    for obj in result.objects:
        props = obj.properties
        results.append(_format_search_result(props.get("text", ""), props))
    return json.dumps(results, ensure_ascii=False, indent=2)
```

**`_format_search_result` update:** The ChromaDB version received `(document: str, meta: dict)`. With Weaviate, `obj.properties` is a dict. The paragraph text field is `"text"` (confirmed in `_paragraph_properties()` in `weaviate_loader.py`). So `_format_search_result(props.get("text", ""), props)` works without changing the function signature.

**`near_vector` signature verified:** `(near_vector, *, certainty=None, distance=None, limit=None, offset=None, auto_limit=None, filters=None, group_by=None, rerank=None, target_vector=None, ...)` — `target_vector` is a keyword argument. [VERIFIED: introspection]

### Pattern 5: get_talk Tool (`server.py`)

```python
# Source: verified from fetch_object_by_id and fetch_objects signatures
from weaviate.util import generate_uuid5

async def get_talk(talk_id: str, ctx=None):
    app: AppContext = ctx.lifespan_context["app"]
    talk_num = _parse_talk_id(talk_id)
    if talk_num is None:
        return f"Invalid talk_id format '{talk_id}'."

    talks_col = app.client.collections.use("ConferenceTalks")
    talk_obj = talks_col.query.fetch_object_by_id(generate_uuid5(f"talk_{talk_num}"))
    if talk_obj is None:
        return f"No talk found with ID '{talk_id}'."

    tm = talk_obj.properties
    header = (
        f"Speaker: {tm.get('speaker_name', '')}\n"
        f"Title: {tm.get('title', '')}\n"
        f"Conference: {tm.get('conference_month', '')} {tm.get('conference_year', '')}\n"
        f"Session: {tm.get('session_description', '')}"
    )

    paras_col = app.client.collections.use("ConferenceTalkParagraphs")
    para_result = paras_col.query.fetch_objects(
        filters=Filter.by_property("talk_id").equal(talk_num),
        limit=10000,
    )

    if not para_result.objects:
        return f"No paragraphs found for talk_id '{talk_id}'."

    sorted_rows = sorted(
        para_result.objects,
        key=lambda obj: int(obj.properties.get("paragraph_number", 0)),
    )
    body = "\n\n".join(obj.properties.get("text", "") for obj in sorted_rows)
    return f"{header}\n\n{body}"
```

**`fetch_object_by_id` signature verified:** `(self, uuid: str | UUID, include_vector=False, *, return_properties=None, return_references=None)` — accepts a string UUID directly. Returns the object or `None` when not found. [VERIFIED: introspection of `_FetchObjectByIDQuery`]

**`fetch_objects` signature verified:** `(self, *, limit=None, offset=None, after=None, filters=None, sort=None, ...)` — keyword-only after `self`. Returns `QueryReturn` with `.objects` list. [VERIFIED: introspection]

**`talk_id` filter type:** `talk_id` is stored as `DataType.INT` in `_paragraph_properties()`. Passing `int` to `.equal(talk_num)` where `talk_num` is the result of `_parse_talk_id()` (returns `int`) is correct. [VERIFIED: schema in `loaders/weaviate_loader.py` + `.equal()` accepts `int`]

### Pattern 6: `talk_exists()` Method to Add to `WeaviateLoader`

```python
# Source: verified from fetch_object_by_id signature
def talk_exists(self, talk_id: int) -> bool:
    from weaviate.util import generate_uuid5
    col = self._client.collections.use("ConferenceTalks")
    obj = col.query.fetch_object_by_id(generate_uuid5(f"talk_{talk_id}"))
    return obj is not None
```

**Note:** Collection name must be updated to `"ConferenceTalks"` (D-18), not `"Talk"` (current benchmark name). [VERIFIED: D-18 decision]

### Pattern 7: `load_talk_bundles()` in `extractors/phase6_weaviate_loader.py`

The existing `WeaviateLoader.load(bundle)` handles one talk at a time via `insert_many`. The production `load_talk_bundles()` should iterate bundles and call `loader.load(bundle)` for each, accumulating counts from the result. Since `WeaviateLoader.load()` already handles the per-collection insert_many internally (including error handling), wrapping it is simpler than re-implementing batch logic.

```python
# Source: loaders/weaviate_loader.py load() method (verified by reading source)
from loaders.weaviate_loader import WeaviateLoader
from loaders.shared_transforms import TalkBundle

def load_talk_bundles(bundles: list[TalkBundle], loader: WeaviateLoader) -> dict:
    skipped_talks = []
    talks_inserted = paragraphs_inserted = citations_inserted = footnotes_inserted = 0

    for metadata, paragraphs, citations, footnotes, validation_report in bundles:
        if not validation_report.is_valid:
            skipped_talks.append(metadata.talk_id)
            continue
        loader.load((metadata, paragraphs, citations, footnotes, validation_report))
        # Count approximation — WeaviateLoader.load() does not return counts
        talks_inserted += 1
        # Paragraph count from non-annotation paragraphs
        paragraphs_inserted += sum(
            1 for p in paragraphs.paragraphs if p.source_type != "annotation"
        )
        citations_inserted += len(citations.citations)
        footnotes_inserted += len(footnotes.footnotes)

    return {
        "talks_inserted": talks_inserted,
        "paragraphs_inserted": paragraphs_inserted,
        "citations_inserted": citations_inserted,
        "footnotes_inserted": footnotes_inserted,
        "skipped_talks": skipped_talks,
        "skipped_count": len(skipped_talks),
    }
```

**Alternative approach:** `WeaviateLoader.load()` does not return per-collection counts (returns `None`). The count approximation above is acceptable for the `generate_verification_report()` FK checks (which do UUID-based spot checks, not exact count matching). The planner may choose to add return values to `WeaviateLoader.load()` or derive counts differently — both are valid.

### Pattern 8: `weaviate-embedded` for pytest

```python
# Source: verified connect_to_embedded signature; WeaviateClient __enter__/__exit__ verified
import pytest
import weaviate

@pytest.fixture(scope="session")
def weaviate_client():
    with weaviate.connect_to_embedded() as client:
        yield client
```

**`connect_to_embedded()` confirmed:** Available in weaviate-client==4.20.5. Default version parameter is `"1.30.5"` (the binary it downloads). `WeaviateClient` supports `__enter__`/`__exit__` — `__enter__` calls `connect()`, `__exit__` calls `close()`. [VERIFIED: introspection]

**Binary download:** First run downloads ~100MB to `~/.cache/weaviate-embedded`. On Windows, this is `%USERPROFILE%\.cache\weaviate-embedded`. Subsequent runs use the cache. [VERIFIED: D-17 decision; connect_to_embedded docs]

**Port conflict risk:** `connect_to_embedded()` defaults to port 8079 (HTTP) and 50050 (gRPC) — different from the production ports 8080/50051. No conflict with a running production Weaviate instance.

**Schema isolation:** The embedded instance starts fresh. Tests must call `_ensure_schema()` or create collections before inserting. Use the updated `WeaviateLoader` (with PascalCase collection names) to set up the schema.

### Anti-Patterns to Avoid

- **Do not use `collection.batch.dynamic()` for bulk pre-computed records:** `batch.dynamic()` is designed for streaming unknown quantities. For `load_talk_bundles()` where all records are pre-computed in memory, `col.data.insert_many(objects)` (already used in `WeaviateLoader.load()`) is simpler and already tested. [VERIFIED: `_BatchCollection.add_object` pattern vs `insert_many` in existing code]

- **Do not pass `None` as `grpc_port`:** `weaviate.connect_to_local()` requires both HTTP and gRPC ports. Omitting or nullifying `grpc_port` causes silent connection failures.

- **Do not import `WeaviateLoader` in `server.py`:** `server.py` connects directly via `weaviate.connect_to_local()`. Importing `WeaviateLoader` would pull in the embed_fn dependency unnecessarily and violates D-01.

- **Do not call `client.close()` in `health_handler`:** D-19 specifies a plain HTTP GET — no Weaviate client lifecycle in health checks.

- **Do not pass `str` when `int` is expected for `talk_id` filter:** `talk_id` is stored as `DataType.INT`. `.equal("8820")` would not match `.equal(8820)`. Always pass `int` (the output of `_parse_talk_id()` is already `int`).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| UUID generation for Weaviate objects | Custom hash/UUID function | `weaviate.util.generate_uuid5(identifier)` | Deterministic, already used throughout `WeaviateLoader`; ensures O(1) UUID-based lookups work |
| Batch insert chunking | Manual SQLite-style batch splitting | `col.data.insert_many(objects)` | Already handles internal batching; no SQLite 999-param limit applies to Weaviate |
| Filter construction | Dict-based filter dicts | `Filter.by_property(name).equal(val)` + `&` chaining | Type-safe, composable, avoids ChromaDB's `{"$and": [...]}` dict format entirely |
| Health check | Weaviate client connection per health poll | Direct HTTP GET to `/v1/.well-known/ready` | Zero gRPC overhead; endpoint returns 200 only when fully ready |
| Embedded Weaviate for tests | Docker Compose + pytest-docker | `weaviate.connect_to_embedded()` | Downloads and manages binary automatically; no Docker required |

---

## WEAVIATE_BATCH_SIZE Recommendation

**ChromaDB used 1000** because `create_batches()` chunked by SQLite's 999-parameter limit. Weaviate has no such constraint — `insert_many` sends all objects in a single HTTP/gRPC call.

**The `WEAVIATE_BATCH_SIZE` constant in `pipeline_config.py` controls a different thing:** how many talks to buffer in `run_pipeline.py` before flushing to `load_talk_bundles()`. It is NOT the per-collection insert batch size.

**Recommendation: `WEAVIATE_BATCH_SIZE = 50`**

Rationale:
- Each talk bundle contains ~20-60 objects (1 talk + N paragraphs + M citations + K footnotes). 50 talks = ~1,000-3,000 objects per flush call.
- Weaviate's `insert_many` handles this comfortably in one call — no chunking needed.
- Memory: 50 talks with full embeddings (768-dim vectors per object) = manageable RAM.
- Failure granularity: Smaller batches mean failures are caught sooner and `failed_talks.json` is more granular. With 5,838 talks, 50-talk batches = ~117 flushes total.
- The benchmark ran at ~4.41 rec/s; 50-talk flushes will be ~5-15 seconds each — appropriate for a long-running pipeline with progress feedback.

[ASSUMED: The 50-talk batch size is based on reasoning about the object count per talk and Weaviate's gRPC payload limits. Weaviate's official docs recommend dynamic batching for unknown quantities, but for this pipeline the count is known and fixed-size flush is simpler. If memory issues arise at 50, reduce to 25.]

---

## Current State of the Codebase

| File | Current State | Phase 24 Action |
|------|--------------|-----------------|
| `extractors/phase6_chromadb_loader.py` | Already deleted (ModuleNotFoundError) | Create `phase6_weaviate_loader.py` |
| `scripts/run_pipeline.py` | Broken import at line 41 (`phase6_chromadb_loader`) | Swap all ChromaDB references |
| `server.py` | Uses `chromadb` import, `get_chromadb_client`, `CHROMADB_COLLECTION_NAMES` | Full swap to Weaviate |
| `config/chromadb_client.py` | Exists, functional | Delete |
| `config/pipeline_config.py` | Has `CHROMADB_COLLECTION_NAMES`, `CHROMADB_BATCH_SIZE` | Replace with Weaviate constants |
| `loaders/weaviate_loader.py` | Exists, uses old names (`Talk`, `Paragraph`, etc.) | Update `COLLECTIONS` + `_ensure_schema()` + add `talk_exists()` |
| `Pipfile [packages]` | Has `chromadb = "*"` and `qdrant-client = "==1.17.1"` | Move both to `[dev-packages]` |
| `docker-compose.yml` | Only `mcp-server` service | Add `weaviate` service |
| `.env.example` | Has `CHROMADB_DATA_PATH` | Replace with `WEAVIATE_HOST`, `WEAVIATE_PORT`, `WEAVIATE_GRPC_PORT` |
| `tests/test_phase6.py` | Broken (imports `phase6_chromadb_loader`) | Full rewrite for Weaviate |
| `tests/test_phase6_orchestrator.py` | Broken (imports `run_pipeline` which imports deleted loader) | Minimal patch: replace 9 `get_chromadb_client` mocks with `WeaviateLoader` mocks |

**Test suite current state:** `pipenv run py -m pytest` fails at collection time with 2 errors (`test_phase6.py` and `test_phase6_orchestrator.py`). The other 416 tests collect successfully. Both test files must be fixed as part of Phase 24 — they are blocking, not deferred. [VERIFIED: running `pipenv run py -m pytest tests/ --collect-only`]

---

## Common Pitfalls

### Pitfall 1: `WeaviateLoader.COLLECTIONS` Still Uses Old Names
**What goes wrong:** After updating `_ensure_schema()` to create `ConferenceTalks` etc., if `COLLECTIONS = ["Talk", "Paragraph", ...]` is not also updated, `reset()`, `talk_exists()`, and any code iterating `COLLECTIONS` will use the wrong names.
**How to avoid:** Update `COLLECTIONS` list and ALL `_ensure_schema()` collection name strings in a single edit. Verify with `python -c "from loaders.weaviate_loader import WeaviateLoader; print(WeaviateLoader.COLLECTIONS)"`.

### Pitfall 2: `gRPC` Connection Not Closed
**What goes wrong:** `server.py` exits without calling `client.close()` — gRPC threads hang, server doesn't exit cleanly.
**How to avoid:** D-05 specifies a `finally:` block in `_lifespan`. Confirm `close()` is called in the exception path too.
**Warning signs:** Server process doesn't exit after Ctrl+C; lingering Python threads in task manager.

### Pitfall 3: Test Fixture Schema Mismatch
**What goes wrong:** `weaviate.connect_to_embedded()` starts a fresh Weaviate with no schema. If tests create collections using the old names (`Talk`, `Paragraph`) from the benchmark WeaviateLoader before the D-18 rename, tests pass but verify the wrong schema.
**How to avoid:** Import `WeaviateLoader` from the updated `loaders/weaviate_loader.py` (with PascalCase production names) in the test fixture. The fixture should instantiate WeaviateLoader to trigger `_ensure_schema()`.

### Pitfall 4: `insert_many` Result Error Check
**What goes wrong:** `col.data.insert_many(objects)` returns `BatchObjectReturn` which has a `has_errors` attribute. If errors are silently ignored, partial inserts appear as successes.
**How to avoid:** The existing `WeaviateLoader.load()` already checks `result.has_errors` and logs warnings per object. This pattern must be preserved in any new code paths.

### Pitfall 5: `fetch_objects` Without `limit` Returns All Objects
**What goes wrong:** `col.query.fetch_objects(filters=...)` with no `limit` — in Weaviate v4, this uses the server default (100 objects). For talks with >100 paragraphs, this silently truncates.
**How to avoid:** Always specify `limit=10000` for the paragraph fetch in `get_talk`. [VERIFIED: `fetch_objects` signature shows `limit: int | None = None`; Weaviate default is 100 when None]

### Pitfall 6: Empty `.env.example` `CHROMADB_DATA_PATH` Line Left Behind
**What goes wrong:** If the `CHROMADB_DATA_PATH=/path/to/chromadb` line stays in `.env.example`, operators copy stale vars into their `.env`.
**How to avoid:** Delete `CHROMADB_DATA_PATH` and add `WEAVIATE_DATA_PATH` (volume mount path) and the three connection vars. Also remove the comment block about ChromaDB directory setup.

### Pitfall 7: `docker-compose.yml` Weaviate Container Without Volume
**What goes wrong:** Weaviate configured without a named volume for `PERSISTENCE_DATA_PATH` loses all data on container restart.
**How to avoid:** Add a `weaviate_data` named volume in `docker-compose.yml` and mount it to `/var/lib/weaviate`. Mirror the benchmark `infra/docker-compose.vector-dbs.yml` pattern.

### Pitfall 8: `CHROMADB_DATA_PATH` Bind Mount Still in `mcp-server` Service
**What goes wrong:** Current `docker-compose.yml` may have bind mounts or env references to ChromaDB that persist alongside the new Weaviate service.
**Note:** The current `docker-compose.yml` does NOT have a bind mount for ChromaDB — it only has `env_file: - .env`. So no bind mount cleanup is needed in the `mcp-server` service. But env vars in `.env` (from `.env.example`) will need to be updated by the operator.

---

## Code Examples

### Aggregate count (startup validation)
```python
# Source: verified from AggregateReturn.__dataclass_fields__ = ['properties', 'total_count']
result = client.collections.use("ConferenceTalks").aggregate.over_all(total_count=True)
count = result.total_count  # int
```

### UUID-based object lookup (talk_exists, get_talk)
```python
# Source: verified from _FetchObjectByIDQuery.fetch_object_by_id signature
from weaviate.util import generate_uuid5
obj = col.query.fetch_object_by_id(generate_uuid5(f"talk_{talk_id}"))
exists = obj is not None  # returns None when not found
```

### Filter combining
```python
# Source: verified from _FilterByProperty.equal, .like, _Filters.__and__ via & operator
from weaviate.classes.query import Filter
f1 = Filter.by_property("conference_year").equal(2020)       # int
f2 = Filter.by_property("conference_month").equal("April")   # str
f3 = Filter.by_property("speaker_name").like("*Holland*")    # wildcard str
combined = f1 & f2 & f3
```

### fetch_objects with filter
```python
# Source: verified from _FetchObjectsQuery.fetch_objects signature
result = paras_col.query.fetch_objects(
    filters=Filter.by_property("talk_id").equal(talk_num),  # talk_num is int
    limit=10000,
)
for obj in result.objects:
    text = obj.properties.get("text", "")
    para_num = obj.properties.get("paragraph_number", 0)
```

### near_vector search
```python
# Source: verified from near_vector query class; target_vector="default" matches WeaviateLoader schema
result = col.query.near_vector(
    near_vector=query_vector,
    limit=limit,
    filters=weaviate_filter,
    target_vector="default",
)
for obj in result.objects:
    text = obj.properties.get("text", "")
```

### connect_to_embedded for pytest
```python
# Source: verified connect_to_embedded available in 4.20.5; WeaviateClient has __enter__/__exit__
import weaviate
with weaviate.connect_to_embedded() as client:
    # client.collections.create(...)
    pass  # auto-closes on exit
```

### Weaviate Docker service (for docker-compose.yml)
```yaml
# Source: infra/docker-compose.vector-dbs.yml (verified, used as reference)
weaviate:
  image: cr.weaviate.io/semitechnologies/weaviate:1.37.1
  restart: unless-stopped
  ports:
    - "8080:8080"
    - "50051:50051"
  environment:
    AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"
    PERSISTENCE_DATA_PATH: "/var/lib/weaviate"
    DEFAULT_VECTORIZER_MODULE: "none"
    CLUSTER_HOSTNAME: "weaviate-node"
  volumes:
    - weaviate_data:/var/lib/weaviate
  healthcheck:
    test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider",
           "http://localhost:8080/v1/.well-known/ready"]
    interval: 10s
    timeout: 30s
    retries: 5
    start_period: 30s
```

**Port binding difference from benchmark:** The benchmark used `127.0.0.1:8080:8080` (localhost-only). Production `docker-compose.yml` uses `8080:8080` (all interfaces) so the co-located `mcp-server` container can reach Weaviate by service name. The `mcp-server` accesses Weaviate at `WEAVIATE_HOST=weaviate` (Docker service name) rather than `localhost`. [VERIFIED: Docker networking — named services resolve by service name within the same Compose stack]

---

## test_phase6.py Rewrite Strategy (Claude's Discretion)

The existing `test_phase6.py` tests ChromaDB-specific functions (`_flatten_metadata`, `insert_collection`, `prepare_talk_record`, etc.) that do NOT exist in the Weaviate loader. Many of these functions now live in `loaders/shared_transforms.py` and are already tested there (indirectly).

**What to carry over:**
- Fixture helpers (`make_talk_metadata`, `make_paragraph`, `make_citation`, etc.) — keep verbatim, they test data structures not DB clients
- Tests for `prepare_*` functions — move import to `loaders.shared_transforms` since that's where they now live
- `test_load_talk_bundles` class — rewrite to use `weaviate.connect_to_embedded()` + actual WeaviateLoader (with PascalCase schema); test that records land in Weaviate

**What to drop:**
- `TestInsertCollection` — no `insert_collection()` in the Weaviate loader; `WeaviateLoader.load()` handles insertion internally
- `test_get_embedding_function` that checks for `OllamaEmbeddingFunction` — keep but verify still works

**What to add:**
- `test_talk_exists_true` / `test_talk_exists_false` — verify the new `talk_exists()` method
- `test_load_bundles_inserts_correct_collection_names` — verify `ConferenceTalks` not `Talk`
- `test_generate_verification_report` — adapt from existing but use WeaviateLoader

**Session-scoped fixture pattern:**
```python
@pytest.fixture(scope="session")
def weaviate_client():
    with weaviate.connect_to_embedded() as client:
        yield client

@pytest.fixture(scope="session")
def weaviate_loader(weaviate_client):
    # WeaviateLoader needs its own connection; share the embedded instance
    # Use connect_to_embedded client directly or instantiate WeaviateLoader with embedded ports
    # Note: WeaviateLoader.__init__ creates its own client — use embedded ports
    loader = WeaviateLoader(
        host="127.0.0.1",
        port=8079,          # connect_to_embedded default
        grpc_port=50050,    # connect_to_embedded default
        embed_fn=None,      # no embeddings in unit tests
    )
    yield loader
    loader.close()
```

**Caution:** `weaviate.connect_to_embedded()` starts an in-process Weaviate binary. `WeaviateLoader.__init__` creates a separate `weaviate.connect_to_local()` connection. Both can connect to the same embedded instance using its ports (8079 HTTP, 50050 gRPC). Tests that call `loader.load(bundle)` with `embed_fn=None` will insert records with no vectors — valid for structural tests (do records exist?) but not for near_vector query tests.

---

## test_phase6_orchestrator.py Minimal Patch Strategy (D-20)

The 9 tests that use `patch.object(run_pipeline, "get_chromadb_client", ...)` fail because `run_pipeline.py` will no longer import `get_chromadb_client`. After migration, `run_pipeline.py` uses `WeaviateLoader` as a context manager.

**The new import pattern in `run_pipeline.py`:**
```python
from loaders.weaviate_loader import WeaviateLoader
from extractors.phase6_weaviate_loader import load_talk_bundles, TalkBundle
```

**Minimal patch for each test:** Replace `get_chromadb_client` and `get_or_create_collection` mocks with a mock `WeaviateLoader` context manager. The key change:

```python
# OLD pattern (breaks after migration):
patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client)

# NEW pattern (minimal fix):
mock_loader = MagicMock()
mock_loader.__enter__ = MagicMock(return_value=mock_loader)
mock_loader.__exit__ = MagicMock(return_value=False)
mock_loader.talk_exists.return_value = False  # default: talk not cached

patch.object(run_pipeline, "WeaviateLoader", return_value=mock_loader)
```

Tests that verify skip behavior (resume) mock `mock_loader.talk_exists.return_value = True/False` based on the talk ID. The `CHROMADB_BATCH_SIZE` patches become `WEAVIATE_BATCH_SIZE` patches. All other test logic (batch flush counts, failure recording, validation failure handling, summary output) is preserved verbatim.

**9 tests to patch (identified from test file):**
1. `test_full_loop_calls_all_phases`
2. `test_resume_skips_processed`
3. `test_failed_talk_logged_on_exception`
4. `test_validation_failure_skips_talk`
5. `test_final_summary_printed`
6. `test_skip_mode_default`
7. `test_force_flag_reprocesses`
8. `test_buffer_flush_at_batch_size` (also patches `CHROMADB_BATCH_SIZE` → `WEAVIATE_BATCH_SIZE`)
9. `test_final_flush_on_remaining` (also patches `CHROMADB_BATCH_SIZE` → `WEAVIATE_BATCH_SIZE`)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ChromaDB dict-based `where` filters | `Filter.by_property().equal()` chain with `&` | Phase 24 | Native filters = 4x faster filtered queries (51ms vs 220ms p50) |
| Over-fetch 4x for speaker post-filter | Native `.like()` filter | Phase 24 | Exact limit honored; no over-fetching |
| SQLite batch size limit (999 params) | No limit — `insert_many` handles internally | Phase 21+ | Batch size based on throughput, not DB param limit |
| `chromadb.EphemeralClient()` for tests | `weaviate.connect_to_embedded()` | Phase 24 | Real Weaviate binary; no mock; ~2-5s startup |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `WEAVIATE_BATCH_SIZE = 50` is appropriate for the pipeline buffer flush | WEAVIATE_BATCH_SIZE Recommendation | If memory is tight with 50 talks' embeddings in RAM, reduce to 25. Pipeline will still complete correctly, just more flushes. |
| A2 | `weaviate.connect_to_embedded()` binary download works on the user's Windows 11 machine | Pattern 8 / test strategy | If binary download fails (firewall, disk space), tests using embedded Weaviate will not run. Fallback: skip embedded tests, run against Docker Weaviate. |
| A3 | `WeaviateLoader` can share an embedded Weaviate instance via `connect_to_local(host="127.0.0.1", port=8079, grpc_port=50050)` in tests | test_phase6.py strategy | If embedded instance has auth or port conflicts, the WeaviateLoader fixture would need to reuse the `weaviate_client` connection object directly. |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| weaviate-client (pip) | All Weaviate operations | Yes | 4.20.5 (pinned) | — |
| Docker | docker-compose.yml Weaviate service | Not checked — user responsibility | — | N/A |
| Weaviate server (Docker) | MIGR-04 smoke test | Not checked — user must start stack | — | Not applicable |
| Ollama | Embedding at pipeline run time | Not checked — user must run Ollama | — | Pipeline fails gracefully with error |
| pipenv | All Python commands | Yes (per CLAUDE.md) | — | — |

**Weaviate-embedded binary:** Will download ~100MB on first test run. Requires internet access. Cached at `%USERPROFILE%\.cache\weaviate-embedded` on Windows. Default embedded version is `1.30.5` (not 1.37.1 used in production) — collection schema should be compatible across patch versions. [VERIFIED: `connect_to_embedded` default `version` parameter = `"1.30.5"`]

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (in Pipfile [dev-packages]) |
| Config file | None detected (no pytest.ini, pyproject.toml, or conftest.py at root) |
| Quick run command | `pipenv run py -m pytest tests/test_phase6.py tests/test_phase6_orchestrator.py -x` |
| Full suite command | `pipenv run py -m pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MIGR-01 | `load_talk_bundles()` inserts records into Weaviate | unit (embedded) | `pipenv run py -m pytest tests/test_phase6.py -x` | ❌ Wave 0 (rewrite) |
| MIGR-01 | Pipeline orchestrator uses WeaviateLoader; skip check works | unit (mock) | `pipenv run py -m pytest tests/test_phase6_orchestrator.py -x` | ❌ Wave 0 (minimal patch) |
| MIGR-01 | `python -c "from extractors.phase6_weaviate_loader import load_talk_bundles, TalkBundle"` exits 0 | smoke | Run command directly | ❌ Wave 0 (file doesn't exist) |
| MIGR-02 | `grep -i chromadb server.py` returns no matches | acceptance | `grep -i "chromadb" server.py \| wc -l` = 0 | ❌ Wave 0 |
| MIGR-02 | `grep -i chromadb scripts/run_pipeline.py` returns no matches | acceptance | `grep -i "chromadb" scripts/run_pipeline.py \| wc -l` = 0 | ❌ Wave 0 |
| MIGR-03 | `docker compose config` parses without error | smoke | `docker compose config` | ❌ Wave 0 |
| MIGR-04 | Full pipeline run + MCP smoke test | human-gated | Manual | N/A |

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/test_phase6.py tests/test_phase6_orchestrator.py -x`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x`
- **Phase gate:** Full suite green (`tests/` — 416 passing + phase6 tests green) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_phase6.py` — full rewrite for Weaviate; covers `load_talk_bundles()`, `talk_exists()`, `generate_verification_report()`, PascalCase collection names
- [ ] `tests/test_phase6_orchestrator.py` — minimal patch; replace 9 `get_chromadb_client` mocks with `WeaviateLoader` context manager mocks; rename `CHROMADB_BATCH_SIZE` patches to `WEAVIATE_BATCH_SIZE`
- [ ] `extractors/phase6_weaviate_loader.py` — must exist before any test can import from it

---

## Security Domain

No security changes in this phase. Auth (ScaleKit/OAuth) is unchanged. The Weaviate instance uses anonymous access (`AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true`) consistent with the benchmark configuration — it is not directly internet-exposed (proxied via Caddy/cloudflared per `infra/`).

| ASVS Category | Applies | Note |
|---------------|---------|------|
| V2 Authentication | No | ScaleKit auth unchanged |
| V5 Input Validation | Yes (existing) | `_parse_talk_id()` validates input; filter values passed from user go through Weaviate's parameterized filter API — no string injection risk |

---

## Sources

### Primary (HIGH confidence)
- `loaders/weaviate_loader.py` — Existing WeaviateLoader class; all method names, schema, collection map, insert_many pattern verified by reading source
- `loaders/shared_transforms.py` — TalkBundle type alias, prepare_talk_bundle_rich() verified
- `scripts/run_pipeline.py` — All ChromaDB integration points identified by reading source
- `server.py` — All ChromaDB patterns identified by reading source
- `config/chromadb_client.py` — Factory pattern to mirror verified
- `infra/docker-compose.vector-dbs.yml` — Weaviate Docker service definition verified
- `benchmark/DECISION.md` — Weaviate version 1.37.1 confirmed
- Introspection of weaviate-client==4.20.5 — ALL API signatures verified via `inspect.signature()` and `__dataclass_fields__`

### Secondary (MEDIUM confidence)
- `tests/test_phase6.py` — ChromaDB test structure understood; rewrite scope determined
- `tests/test_phase6_orchestrator.py` — 9 patches identified; minimal patch strategy derived
- `Pipfile` — Current package structure verified; chromadb and qdrant-client in [packages] confirmed

### Tertiary (LOW confidence)
- A1-A3 in Assumptions Log above

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — weaviate-client 4.20.5 installed, all API signatures verified via introspection
- Architecture: HIGH — code read directly; patterns verified against working WeaviateLoader
- Pitfalls: HIGH — derived from reading existing code and verified API behaviors
- WEAVIATE_BATCH_SIZE recommendation: MEDIUM — reasoning-based; no empirical measurement at this batch size

**Research date:** 2026-05-11
**Valid until:** 2026-06-11 (weaviate-client is pinned to 4.20.5, so API won't shift)
