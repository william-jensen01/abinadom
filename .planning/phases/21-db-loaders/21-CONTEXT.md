# Phase 21: DB Loaders — Context

**Gathered:** 2026-04-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Three vector DB loaders (ChromaDB, Weaviate, Qdrant) in `loaders/`, each accepting a
`TalkBundle` with pre-computed embedding vectors and persisting records across 4
collections (talks, paragraphs, citations, footnotes). Also adds `prepare_talk_bundle_rich()`,
extends prepare_* tuples to carry vectors, adds an embedding helper, and installs
Weaviate and Qdrant client dependencies.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**6 requirements are locked.** See `21-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `21-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `loaders/chromadb_loader.py` — benchmark ChromaDB loader (separate from production phase6 loader)
- `loaders/weaviate_loader.py` — Weaviate loader with full typed schemas
- `loaders/qdrant_loader.py` — Qdrant loader with payload indexes
- `prepare_talk_bundle_rich()` and supporting `_rich` variants in `shared_transforms.py`
- Extended record tuple `(doc, metadata, id, vector)` in both flat and rich prepare functions
- Embedding helper function (calls Ollama nomic-embed-text, returns vector)
- `weaviate-client` and `qdrant-client` added to Pipfile
- Tests for each loader (insert + query round-trip against Docker instances)

**Out of scope (from SPEC.md):**
- Modifying the production ChromaDB loader (`extractors/phase6_chromadb_loader.py`)
- Benchmark runner CLI (`benchmark/runner.py`) — Phase 22
- Full dataset loading (5,838 talks) — Phase 23
- Recall@k computation across DBs — Phase 22–23
- Collection naming conventions for production — Phase 24
- Embedding model selection or tuning

</spec_lock>

<decisions>
## Implementation Decisions

### Loader Interface Design

- **D-01:** Each loader is a **class** with connection state: `ChromaDBLoader(host, port, embed_fn, batch_size=100)`. Client is created in `__init__` and reused across `.load()` calls — efficient for the benchmark runner loading many bundles in a loop.
- **D-02:** `embed_fn` is injected at **constructor time** (not per `.load()` call). The benchmark always uses the same embedding function for the whole session, so constructor injection is cleaner.
- **D-03:** A shared **`BaseLoader` ABC** lives in `loaders/__init__.py` with abstract `load(bundle: TalkBundle) -> None`. All 3 loaders inherit from it. Phase 22 runner can type-hint `list[BaseLoader]` and iterate uniformly.

### Embedding Helper

- **D-04:** The Ollama embedding helper lives in **`loaders/embeddings.py`** — a dedicated file in the same package as the loaders. This keeps `loaders/` self-contained (everything Phase 22 imports is in one package) and avoids mixing HTTP I/O into `shared_transforms.py` (pure data transforms).
- **D-05:** The helper is **synchronous**: `embed(text: str, model: str = "nomic-embed-text", url: str = OLLAMA_URL) -> list[float]`. Phase 21 loaders are synchronous; Phase 22 can parallelize at the runner level if needed.

### Batch Size & Error Handling

- **D-06:** Batch size is a **configurable constructor argument** (`batch_size=100` default). Caller can override for testing (`batch_size=10`) or benchmarking tuning. Consistent with how Phase 6 ChromaDB loader handles write buffers.
- **D-07:** Bad records during batch insert are handled with **skip-and-log**: log a WARNING with the failing `doc_id` and exception, continue with remaining records. Upsert semantics make partial loads recoverable by re-running. Not fail-fast — a single malformed record should not abort the entire bundle.

### Integration Test Strategy

- **D-08:** Tests handle "Docker not running" via **skip-if-port-closed**: a session-scoped `conftest.py` fixture checks if the target DB port is reachable (1-second socket timeout); if not, the entire test module is skipped with a clear message. No CLI flag needed — tests auto-skip when Docker is down.
- **D-09:** A **shared `TalkBundle` fixture** in `tests/conftest.py` provides a minimal bundle (1 talk, 2 paragraphs, 1 citation, 1 footnote) used by all 3 loader round-trip tests. Identical input across DBs makes results easier to compare and changes to the model require only one update.

### Claude's Discretion

- Collection/class naming: use `"talks"`, `"paragraphs"`, `"citations"`, `"footnotes"` for Qdrant (snake_case); `"Talk"`, `"Paragraph"`, `"Citation"`, `"Footnote"` for Weaviate (PascalCase required by Weaviate). ChromaDB uses same names as production collections.
- Qdrant vector field: use the **default vector** (not named vectors) — simpler API, and Phase 21 only benchmarks a single embedding model.
- Weaviate UUID derivation: use `generate_uuid5(doc_id)` from `weaviate.util` for deterministic UUIDs. `doc_id` is the same string used as the ChromaDB ID (`"talk_123"`, `"para_456"`, etc.).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 21 Requirements
- `.planning/phases/21-db-loaders/21-SPEC.md` — Locked requirements, full acceptance criteria, constraints, and in/out scope boundaries (MUST read first)

### Phase 20 Outputs (dependencies)
- `loaders/shared_transforms.py` — All prepare_* functions and TalkBundle type being extended in this phase
- `.planning/phases/20-benchmark-infrastructure-framework/20-SPEC.md` — Shared transforms, metrics, queries spec (context for what Phase 20 delivered)
- `infra/docker-compose.vector-dbs.yml` — ChromaDB 1.5.7 (:8000), Weaviate 1.37.1 (:8080), Qdrant v1.17.1 (:6333)

### Production Loader (reference only — do not modify)
- `extractors/phase6_chromadb_loader.py` — Production ChromaDB loader; Phase 21 benchmark loader must be independent (no imports from this file)

### Existing Tests (backward compat)
- `tests/test_shared_transforms.py` — Must still pass after prepare_* tuple extension
- `tests/test_phase6.py` — Must still pass; uses `_flatten_metadata` alias from phase6

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `loaders/shared_transforms.py`: `flatten_metadata`, `rich_metadata`, `prepare_talk_bundle()`, all `prepare_*` functions — Phase 21 extends these, does not replace them
- `config/chromadb_client.py`: SharedChromaDB HttpClient factory pattern — model for how ChromaDB loader should create its client (reads `CHROMADB_HOST`/`CHROMADB_PORT` env vars)
- `benchmark/metrics.py` + `benchmark/queries.py` — deliverables from Phase 20, consumed by Phase 22; Phase 21 loaders are inputs to the runner, not consumers of these

### Established Patterns
- `prepare_*` functions return `(doc, metadata, id)` tuples — extending to `(doc, metadata, id, vector)` tuples in this phase; existing callers (phase6) pass no `embed_fn` so `vector = None` (backward compat)
- Phase 6 loader uses a `WRITE_BUFFER_SIZE = 1000` constant for batch flushing — Phase 21 loaders use configurable `batch_size=100` default (smaller, more granular)
- All project Python code uses `pipenv run py` (Python Launcher) — test commands follow this pattern

### Integration Points
- Phase 22 benchmark runner will import `BaseLoader` from `loaders/__init__.py` and instantiate all 3 loaders
- `tests/conftest.py` gets a new shared `TalkBundle` fixture for loader round-trip tests
- `Pipfile` gains `weaviate-client` and `qdrant-client` (versions pinned to Docker image compatibility)

</code_context>

<specifics>
## Specific Ideas

- Loader constructor signature: `XLoader(host: str, port: int, embed_fn: Callable[[str], list[float]], batch_size: int = 100)`
- ABC method: `def load(self, bundle: TalkBundle) -> None` (raises `NotImplementedError` in base)
- Embedding helper: `loaders/embeddings.py` — `embed(text, model="nomic-embed-text", url=OLLAMA_URL) -> list[float]`
- Docker port check in conftest: `socket.create_connection((host, port), timeout=1)` — 1 second timeout, session-scoped, `pytest.skip()` on failure
- Shared fixture returns a deterministic minimal bundle (talk_id=9999 or similar) so test assertions can be exact

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 21-db-loaders*
*Context gathered: 2026-04-21*
