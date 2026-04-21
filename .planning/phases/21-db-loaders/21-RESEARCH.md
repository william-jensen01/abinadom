# Phase 21: DB Loaders — Research

**Researched:** 2026-04-21
**Domain:** Vector DB client APIs — ChromaDB 1.5.7, Weaviate 1.37.1, Qdrant v1.17.1
**Confidence:** HIGH (all critical claims verified against PyPI registry, Context7 official docs, or live code inspection)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Each loader is a class with connection state: `ChromaDBLoader(host, port, embed_fn, batch_size=100)`. Client is created in `__init__` and reused across `.load()` calls.
- **D-02:** `embed_fn` is injected at constructor time.
- **D-03:** A shared `BaseLoader` ABC lives in `loaders/__init__.py` with abstract `load(bundle: TalkBundle) -> None`.
- **D-04:** The Ollama embedding helper lives in `loaders/embeddings.py`.
- **D-05:** The helper is synchronous: `embed(text: str, model: str = "nomic-embed-text", url: str = OLLAMA_URL) -> list[float]`.
- **D-06:** Batch size is a configurable constructor argument (`batch_size=100` default).
- **D-07:** Bad records handled with skip-and-log: WARNING with `doc_id` and exception, continue.
- **D-08:** Tests skip if Docker port not reachable: session-scoped fixture, socket check, `pytest.skip()`.
- **D-09:** Shared `TalkBundle` fixture in `tests/conftest.py` — minimal bundle (1 talk, 2 paras, 1 citation, 1 footnote).

**Collection/class naming (Claude's Discretion — locked via CONTEXT.md):**
- Qdrant: `"talks"`, `"paragraphs"`, `"citations"`, `"footnotes"` (snake_case)
- Weaviate: `"Talk"`, `"Paragraph"`, `"Citation"`, `"Footnote"` (PascalCase, Weaviate requirement)
- ChromaDB: same names as production (from `CHROMADB_COLLECTION_NAMES` in `config/pipeline_config.py`)

**Qdrant vector field:** default vector (not named vectors).
**Weaviate UUID:** `generate_uuid5(doc_id)` from `weaviate.util`.

### Claude's Discretion

- ChromaDB benchmark collection naming: use same names as production (`CHROMADB_COLLECTION_NAMES`)
- Qdrant: default vector field, not named vectors
- Weaviate UUID derivation: `generate_uuid5(doc_id)`

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BENCH-02 | ChromaDB benchmark loader — standalone, accepts pre-computed vectors, 4 collections | ChromaDB `collection.upsert(embeddings=...)` verified; `get_or_create_collection` for idempotency |
| BENCH-03 | Weaviate loader — typed schemas, deterministic UUIDs, batch insert with explicit vectors | weaviate-client v4 verified via Context7; `connect_to_local(host, port, grpc_port)` confirmed; `Configure.Vectorizer.none()` confirmed |
| BENCH-04 | Qdrant loader — payload indexes, batch upsert as PointStruct | `qdrant-client==1.17.1` matches Docker exactly; `create_payload_index`, `upsert`, `collection_exists` all confirmed |

</phase_requirements>

---

## Summary

This phase adds three vector DB loaders in `loaders/` that accept pre-computed embedding vectors and persist talk bundles across 4 collections each. It also extends the `shared_transforms.py` tuple shape from `(doc, metadata, id)` to `(doc, metadata, id, vector)` and adds an Ollama embedding helper. All three client libraries have verified API patterns.

The most important implementation risk is **backward compatibility with `test_phase6.py`**, which contains 26 sites of 3-element tuple unpacking (`doc, meta, doc_id = prepare_talk_record(...)`) that will throw `ValueError: too many values to unpack` if the tuple grows to 4 elements. The plan must address this — the tests must be updated to use `doc, meta, doc_id, _ = ...` or `doc, meta, doc_id, *_ = ...` across all affected functions.

For Weaviate, `connect_to_local(host, port, grpc_port)` is the correct synchronous connection function — it accepts host and port as keyword arguments, not positional. The Docker Compose file exposes both HTTP port 8080 and gRPC port 50051. Weaviate v4 client uses `client.collections.exists()` for idempotent creation, and `Configure.Vectorizer.none()` to disable server-side vectorization.

For Qdrant, `qdrant-client==1.17.1` is the exact match to the Docker image version and is available on PyPI. `client.collection_exists(name)` handles idempotency. `client.upsert(collection_name, points=[PointStruct(...)])` with integer IDs derived from a hash of the string doc_id is the standard pattern.

**Primary recommendation:** Pin `weaviate-client==4.20.5` and `qdrant-client==1.17.1`. Fix all 26 3-element tuple unpack sites in `test_phase6.py` as part of the vector tuple extension. Use `ollama.embed(model, input)` (not `ollama.embeddings()`) for the embedding helper since the `ollama` library v0.6.1 is already installed.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Embedding generation | `loaders/embeddings.py` | — | Isolated HTTP I/O; injected into loaders at constructor time |
| Record transformation | `loaders/shared_transforms.py` | — | Pure data transforms; no DB client dependency |
| ChromaDB persistence | `loaders/chromadb_loader.py` | `config/chromadb_client.py` (pattern ref) | Benchmark loader independent from production phase6 loader |
| Weaviate persistence | `loaders/weaviate_loader.py` | `weaviate-client` (new dep) | Schema creation + batch insert + near-vector query |
| Qdrant persistence | `loaders/qdrant_loader.py` | `qdrant-client` (new dep) | Collection creation + payload index + upsert |
| Loader interface | `loaders/__init__.py` (BaseLoader ABC) | — | Phase 22 runner imports `BaseLoader` and iterates uniformly |
| Test fixtures | `tests/conftest.py` | — | Shared TalkBundle; per-DB port-check skip fixtures |

---

## Standard Stack

### Core (new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| weaviate-client | `==4.20.5` | Weaviate v4 Python client | Latest stable; compatibility matrix shows 1.36.x→4.20.x; 1.37.x is newer so 4.20.x is correct [VERIFIED: PyPI registry] |
| qdrant-client | `==1.17.1` | Qdrant Python client | Exact version match to Docker image `qdrant/qdrant:v1.17.1` [VERIFIED: PyPI `pip index versions qdrant-client`] |

### Existing (already in Pipfile, confirmed working)

| Library | Version | Purpose |
|---------|---------|---------|
| chromadb | `*` (installed: 1.5.7) | ChromaDB client — matches Docker `chromadb/chroma:1.5.7` [VERIFIED: `pip show chromadb`] |
| ollama | `*` (installed: 0.6.1) | Ollama embed API — `ollama.embed()` available [VERIFIED: `import ollama; dir(ollama)`] |
| requests | `>=2.31.0` | HTTP fallback if needed | Already installed |

**Installation (additions to Pipfile only):**
```bash
pipenv install "weaviate-client==4.20.5" "qdrant-client==1.17.1"
```

**Version verification (performed 2026-04-21):**
- `weaviate-client`: latest on PyPI is `4.20.5` [VERIFIED: `pip index versions weaviate-client`]
- `qdrant-client`: `1.17.1` is current stable and exact Docker match [VERIFIED: `pip index versions qdrant-client`]

---

## Architecture Patterns

### System Architecture Diagram

```
TalkBundle (5-tuple)
      |
      v
shared_transforms.prepare_talk_bundle() / prepare_talk_bundle_rich()
      |
      v                    embed_fn (injected at constructor time)
  4-element tuples ──────────────────────────────────────┐
  (doc, meta, id, vector=None)                            |
      |                                               loaders/embeddings.py
      |                                               ollama.embed(text)
      |                                                   |
      └──────── vector filled by loader ←─────────────────┘
      |
  ┌───┴──────────────────────────────────┐
  v                                      v
ChromaDBLoader                     WeaviateLoader / QdrantLoader
  |                                      |
collection.upsert(                 batch insert with
  ids, documents,                  explicit vectors
  metadatas, embeddings)                 |
  |                                      v
ChromaDB                          Weaviate / Qdrant
(:8000)                           (:8080/:50051 / :6333)
```

### Recommended Project Structure

```
loaders/
├── __init__.py          # BaseLoader ABC (abstract load(bundle) -> None)
├── shared_transforms.py # Extended with _rich variants + 4-element tuples
├── embeddings.py        # embed() helper calling ollama.embed()
├── chromadb_loader.py   # ChromaDBLoader class
├── weaviate_loader.py   # WeaviateLoader class
└── qdrant_loader.py     # QdrantLoader class

tests/
├── conftest.py          # TalkBundle fixture + 3x port-check fixtures (NEW)
├── test_loaders_chromadb.py
├── test_loaders_weaviate.py
└── test_loaders_qdrant.py
```

### Pattern 1: BaseLoader ABC in `loaders/__init__.py`

```python
# Source: Context7 /weaviate/weaviate-python-client + design decision D-03
from abc import ABC, abstractmethod
from typing import Callable
from loaders.shared_transforms import TalkBundle

class BaseLoader(ABC):
    def __init__(
        self,
        host: str,
        port: int,
        embed_fn: Callable[[str], list[float]],
        batch_size: int = 100,
    ) -> None:
        self.host = host
        self.port = port
        self.embed_fn = embed_fn
        self.batch_size = batch_size

    @abstractmethod
    def load(self, bundle: TalkBundle) -> None: ...
```

### Pattern 2: Embedding Helper in `loaders/embeddings.py`

```python
# Source: ollama library v0.6.1 (VERIFIED: installed, dir(ollama) shows embed)
import ollama

OLLAMA_URL = "http://localhost:11434"

def embed(
    text: str,
    model: str = "nomic-embed-text",
    url: str = OLLAMA_URL,
) -> list[float]:
    """Return a 768-dim vector from Ollama nomic-embed-text."""
    response = ollama.Client(host=url).embed(model=model, input=text)
    # EmbedResponse.embeddings: Sequence[Sequence[float]]
    # Single input → embeddings[0] is the vector
    return list(response.embeddings[0])
```

**IMPORTANT:** `ollama.embed()` is the v2 API (ollama >= 0.2.0). The v0.6.1 installed version supports it. The response is `EmbedResponse` with `.embeddings: Sequence[Sequence[float]]` — for single text input, take `[0]`. [VERIFIED: `inspect.getsource(ollama.EmbedResponse)`]

### Pattern 3: ChromaDB Loader

```python
# Source: VERIFIED chromadb==1.5.7 installed; Collection.upsert() signature confirmed
import chromadb
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle, flatten_metadata

class ChromaDBLoader(BaseLoader):
    COLLECTIONS = ["talks", "paragraphs", "citations", "footnotes"]

    def __init__(self, host, port, embed_fn, batch_size=100):
        super().__init__(host, port, embed_fn, batch_size)
        self._client = chromadb.HttpClient(host=host, port=port)

    def load(self, bundle: TalkBundle) -> None:
        records = prepare_talk_bundle(*bundle, embed_fn=self.embed_fn)
        for coll_name in self.COLLECTIONS:
            col = self._client.get_or_create_collection(name=coll_name)
            for batch in _chunks(records[coll_name], self.batch_size):
                ids = [r[2] for r in batch]
                docs = [r[0] for r in batch]
                metas = [r[1] for r in batch]
                vecs = [r[3] for r in batch]
                try:
                    col.upsert(
                        ids=ids,
                        documents=docs,
                        metadatas=metas,
                        embeddings=vecs,  # list[list[float]]
                    )
                except Exception as e:
                    logger.warning("ChromaDB batch failed: %s", e)
```

**ChromaDB collection.upsert() signature (VERIFIED):**
```
upsert(self,
    ids: str | List[str],
    embeddings: ... | List[Sequence[float]] | None = None,
    metadatas: ... | None = None,
    documents: str | List[str] | None = None,
    ...
) -> None
```
`embeddings` accepts `List[Sequence[float]]` for batch upsert with pre-computed vectors. Pass `None` for embedding_function when creating collections intended for benchmark use. [VERIFIED: `inspect.signature(chromadb.Collection.upsert)` in live env]

**ChromaDB query (for round-trip test):**
```python
# Source: VERIFIED chromadb==1.5.7 Collection.query() signature
results = col.query(
    query_embeddings=[query_vector],
    n_results=1,
    include=["metadatas", "documents", "distances"],
)
```

### Pattern 4: Weaviate Loader

```python
# Source: Context7 /weaviate/weaviate-python-client (HIGH confidence)
import weaviate
import weaviate.classes as wvc
from weaviate.util import generate_uuid5

class WeaviateLoader(BaseLoader):
    COLLECTIONS = ["Talk", "Paragraph", "Citation", "Footnote"]

    def __init__(self, host, port, embed_fn, batch_size=100):
        super().__init__(host, port, embed_fn, batch_size)
        # connect_to_local accepts host, port, grpc_port as kwargs
        self._client = weaviate.connect_to_local(
            host=host,
            port=port,
            grpc_port=50051,  # Weaviate Docker also exposes 50051
        )
        self._ensure_schema()

    def _ensure_schema(self):
        """Create collections if they don't exist (idempotent)."""
        if not self._client.collections.exists("Talk"):
            self._client.collections.create(
                name="Talk",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=[
                    wvc.config.Property(name="talk_id", data_type=wvc.config.DataType.INT),
                    wvc.config.Property(name="title", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="speaker_name", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="conference_year", data_type=wvc.config.DataType.INT),
                    wvc.config.Property(name="conference_month", data_type=wvc.config.DataType.TEXT),
                    # ... all metadata fields explicitly typed
                ],
            )
        # ... repeat for Paragraph, Citation, Footnote

    def load(self, bundle: TalkBundle) -> None:
        records = prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)
        col = self._client.collections.use("Paragraph")
        with col.batch.fixed_size(batch_size=self.batch_size) as batch:
            for doc, meta, doc_id, vector in records["paragraphs"]:
                try:
                    batch.add_object(
                        properties=meta,
                        uuid=generate_uuid5(doc_id),
                        vector=vector,
                    )
                except Exception as e:
                    logger.warning("Weaviate skip %s: %s", doc_id, e)
```

**Weaviate connection (VERIFIED via Context7):**
```python
# connect_to_local() signature:
# connect_to_local(host='localhost', port=8080, grpc_port=50051, ...)
weaviate.connect_to_local(host="localhost", port=8080, grpc_port=50051)
```

**No-vectorizer config (VERIFIED via Context7 — Vectorizers enum):**
```python
# Configure.Vectorizer.none() is the factory method
# Vectorizers.NONE = 'none' in enum
vectorizer_config=wvc.config.Configure.Vectorizer.none()
```

**Collection idempotency (VERIFIED via Context7):**
```python
exists = client.collections.exists("Talk")  # returns bool
```

**Weaviate near-vector query (VERIFIED via Context7):**
```python
from weaviate.classes.query import MetadataQuery
results = col.query.near_vector(
    near_vector=query_vector,
    limit=1,
    return_metadata=MetadataQuery(distance=True),
)
for obj in results.objects:
    print(obj.properties, obj.metadata.distance)
```

**UUID generation (VERIFIED via Context7 docs):**
```python
from weaviate.util import generate_uuid5
uuid = generate_uuid5("para_12345")  # deterministic UUID from string
```

**IMPORTANT — Weaviate client lifecycle:** The `connect_to_local()` function returns a `WeaviateClient` that MUST be closed. Either call `client.close()` in the loader's `__del__` or store it and close explicitly. The context-manager form (`with weaviate.connect_to_local() as client:`) is cleanest but requires the connection be opened/closed per `.load()` call — inefficient if loading many bundles. Store the client as `self._client` and close in a `close()` method.

### Pattern 5: Qdrant Loader

```python
# Source: Context7 /qdrant/qdrant-client (HIGH confidence)
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, PayloadSchemaType
)
import hashlib, struct

def _str_to_uint64(s: str) -> int:
    """Convert a string doc_id to a stable uint64 for Qdrant."""
    digest = hashlib.sha256(s.encode()).digest()
    return struct.unpack(">Q", digest[:8])[0]

class QdrantLoader(BaseLoader):
    COLLECTIONS = ["talks", "paragraphs", "citations", "footnotes"]
    VECTOR_SIZE = 768  # nomic-embed-text output dimension

    def __init__(self, host, port, embed_fn, batch_size=100):
        super().__init__(host, port, embed_fn, batch_size)
        self._client = QdrantClient(host=host, port=port)
        self._ensure_collections()

    def _ensure_collections(self):
        for name in self.COLLECTIONS:
            if not self._client.collection_exists(name):
                self._client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                # Create payload indexes for all metadata fields
                self._client.create_payload_index(name, "talk_id", PayloadSchemaType.INTEGER)
                self._client.create_payload_index(name, "conference_year", PayloadSchemaType.INTEGER)
                self._client.create_payload_index(name, "speaker_name", PayloadSchemaType.KEYWORD)
                # ... all filterable metadata fields

    def load(self, bundle: TalkBundle) -> None:
        records = prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)
        for coll_name in self.COLLECTIONS:
            for batch in _chunks(records[coll_name], self.batch_size):
                points = []
                for doc, meta, doc_id, vector in batch:
                    try:
                        points.append(PointStruct(
                            id=_str_to_uint64(doc_id),
                            vector=vector,
                            payload={**meta, "_doc_id": doc_id, "_doc": doc},
                        ))
                    except Exception as e:
                        logger.warning("Qdrant skip %s: %s", doc_id, e)
                if points:
                    self._client.upsert(collection_name=coll_name, points=points, wait=True)
```

**Qdrant constructor (VERIFIED via Context7):**
```python
QdrantClient(host="localhost", port=6333)
```

**Collection idempotency (VERIFIED via Context7):**
```python
if not client.collection_exists("talks"):
    client.create_collection(...)
```

**Qdrant vector search (VERIFIED via Context7):**
```python
results = client.query_points(
    collection_name="paragraphs",
    query=query_vector,
    limit=1,
    with_payload=True,
)
for point in results.points:
    print(point.payload, point.score)
```

**CRITICAL — Qdrant point IDs must be uint64 or UUID strings.** String doc_ids like `"para_12345"` are NOT valid Qdrant IDs. Either hash to uint64 (using `hashlib.sha256` truncated to 8 bytes as uint64) or store the string as a payload field. The recommended approach: use `_str_to_uint64(doc_id)` for the Qdrant point ID and store `"_doc_id": doc_id` in the payload for retrieval. [VERIFIED: Context7 shows `PointStruct(id=1, ...)` with integer IDs; string IDs must be UUID format]

### Pattern 6: Port-Check Skip in `tests/conftest.py`

```python
# Source: Decision D-08; socket.create_connection verified in live env
import socket
import pytest

def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

@pytest.fixture(scope="session")
def chromadb_available():
    if not _is_port_open("localhost", 8000):
        pytest.skip("ChromaDB not available on localhost:8000")

@pytest.fixture(scope="session")
def weaviate_available():
    if not _is_port_open("localhost", 8080):
        pytest.skip("Weaviate not available on localhost:8080")

@pytest.fixture(scope="session")
def qdrant_available():
    if not _is_port_open("localhost", 6333):
        pytest.skip("Qdrant not available on localhost:6333")
```

**Fixture usage in loader tests:**
```python
def test_chromadb_round_trip(chromadb_available, talk_bundle_fixture):
    loader = ChromaDBLoader("localhost", 8000, embed_fn=embed)
    loader.load(talk_bundle_fixture)
    # ... query and assert
```

The skip happens inside the fixture (not `pytest.mark.skipif`) because port checks are runtime decisions, not import-time. Session scope means the check runs once per test session. [VERIFIED: socket.create_connection confirmed working in live env]

### Anti-Patterns to Avoid

- **Starting Weaviate client inside each `.load()` call:** Opens/closes a gRPC connection on every call. Create once in `__init__`, expose a `close()` method.
- **Using `vectorizer_config` instead of `vectorizer_config=Configure.Vectorizer.none()`:** Weaviate v4 uses `Configure.Vectorizer.none()`, not a string `"none"`. The `Vectorizers.NONE = 'none'` enum exists but is set via the factory.
- **Using `v3` import patterns:** `client.schema.create()`, `client.data_object.create()` — these are Weaviate v3 patterns. v4 uses `client.collections.create()` and `collection.data.insert_many()`.
- **Qdrant string doc_id as point ID:** `PointStruct(id="para_123", ...)` will fail — IDs must be uint64 integers or UUID format strings. Hash string IDs to uint64 and store original as payload field `_doc_id`.
- **3-element tuple unpack after extending to 4-element:** `doc, meta, id = prepare_talk_record(...)` throws `ValueError`. Anywhere existing tests unpack 3 elements, must update to `doc, meta, id, _ = ...` or `doc, meta, id, *_ = ...`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Weaviate UUID from string | Custom hash function | `weaviate.util.generate_uuid5(doc_id)` | Deterministic, spec-compliant UUID5, handles collisions correctly |
| ChromaDB batch split | Manual chunking with `range(0, n, batch_size)` | Built-in `chromadb.utils.batch_utils.create_batches()` | Used in production phase6 loader; handles SQLite param limits |
| Ollama embedding HTTP | `requests.post("/api/embed")` | `ollama.Client(host=url).embed(model, input)` | Already installed (v0.6.1); handles connection, serialization |
| Port availability check | `requests.get()` with timeout | `socket.create_connection((host, port), timeout=1)` | Faster, no HTTP overhead, no import dependency |

---

## Critical Finding: Tuple Backward Compatibility

### The Break

`test_phase6.py` imports `prepare_talk_record`, `prepare_paragraph_records`, `prepare_citation_records`, `prepare_footnote_records`, and `prepare_talk_bundle` from `extractors.phase6_chromadb_loader` (which re-exports from `loaders.shared_transforms`).

It contains **26 sites** of 3-element tuple unpacking:
```python
doc, meta, doc_id = prepare_talk_record(...)  # BREAKS with 4-tuple
doc, meta, doc_id = records[0]                # BREAKS
_, flat_meta, _ = records[0]                  # BREAKS
```

**Confirmed:** Python raises `ValueError: too many values to unpack (expected 3, got 4)` when a 4-element tuple is unpacked into 3 variables. [VERIFIED: live test in project virtualenv]

### The Fix

Update all 3-element unpack sites to 4-element form. Two styles work:
```python
doc, meta, doc_id, _ = prepare_talk_record(...)   # explicit discard
doc, meta, doc_id, *_ = records[0]                # star-discard (more robust)
_, flat_meta, _, _ = records[0]                   # explicit 4-element
```

**File to update:** `tests/test_phase6.py` — 26 sites total.

**Files that are SAFE (use index access, not unpack):**
- `extractors/phase6_chromadb_loader.py` — `_split()` uses `r[0]`, `r[1]`, `r[2]` — NOT broken
- `loaders/shared_transforms.py` — source of truth, will change

**Additional callers to check:**
- `extractors/phase1_talk_metadata.py:398` — `doc, meta, doc_id = metadata.to_chromadb_format()` — different method, not affected by shared_transforms change
- `extractors/phase2_paragraph_extraction.py:1462` — similar; `to_chromadb_format()` method, not affected

### Implementation strategy

The `prepare_talk_bundle()` function signature should gain an optional `embed_fn` parameter:
```python
def prepare_talk_bundle(
    metadata, paragraphs, citations, footnotes, validation_report,
    embed_fn=None,  # NEW: when provided, fills vector field
) -> dict[str, list[tuple[str, dict, str, list[float] | None]]]:
```
When `embed_fn=None` (existing callers including phase6), `vector=None` in all tuples. Backward compat for production loader is maintained in behavior, but the tuple shape changes. **The test file update is unavoidable.**

---

## Weaviate v4 vs v3 API Changes

| Old (v3) | New (v4) | Impact |
|----------|----------|--------|
| `client.schema.create_class()` | `client.collections.create()` | Phase 21 must use v4 |
| `client.data_object.create()` | `collection.data.insert()` / `insert_many()` | v4 only |
| `client.batch` (global) | `collection.batch.fixed_size()` (per-collection) | v4 only |
| `client.query.get()` | `collection.query.fetch_objects()` / `near_vector()` | v4 only |
| `client.schema.contains()` | `client.collections.exists()` | v4 only |
| `generate_uuid5` | same: `weaviate.util.generate_uuid5()` | unchanged |

**Import structure for weaviate-client v4:** [VERIFIED: Context7]
```python
import weaviate                      # connect_to_local, connect_to_custom
import weaviate.classes as wvc       # wvc.config, wvc.query, wvc.data
from weaviate.classes.config import DataType, Property, Configure
from weaviate.classes.query import MetadataQuery
from weaviate.util import generate_uuid5
```

---

## ChromaDB: Benchmark vs Production Collection Names

The production loader (`extractors/phase6_chromadb_loader.py`) uses:
```python
CHROMADB_COLLECTION_NAMES = {
    "talks": "conference_talks",
    "paragraphs": "conference_talk_paragraphs",
    ...
}
```

Per Claude's Discretion decision: the benchmark loader uses the same names. This means the benchmark loader will share data with production if both are run against the same ChromaDB instance. **For isolated benchmarking, the Docker Compose ChromaDB instance (port 8000) is separate from any production ChromaDB instance.** No action needed, but the planner should note this in Wave 0 setup instructions.

---

## Common Pitfalls

### Pitfall 1: Weaviate Client Not Closed

**What goes wrong:** `WeaviateClient` holds a gRPC connection. If `client.close()` is not called, tests may hang or leave dangling connections.
**Why it happens:** Context-manager pattern (`with weaviate.connect_to_local() as client:`) auto-closes; storing as `self._client` without explicit close does not.
**How to avoid:** Add `def close(self) -> None: self._client.close()` to `WeaviateLoader`. Tests call `loader.close()` in a teardown fixture.
**Warning signs:** Test hangs on second test run; gRPC connection errors.

### Pitfall 2: Qdrant Point ID Type Error

**What goes wrong:** `PointStruct(id="para_12345", ...)` raises an error — Qdrant requires IDs to be unsigned 64-bit integers OR UUID-format strings.
**Why it happens:** The project uses string doc_ids like `"para_12345"` throughout. These are NOT UUID format.
**How to avoid:** Hash the string to uint64 using `hashlib.sha256(doc_id.encode())[:8]` unpacked as `struct.unpack(">Q", ...)`. Store the original `doc_id` string in `payload["_doc_id"]`.
**Warning signs:** `qdrant_client.http.exceptions.UnexpectedResponse` with status 422.

### Pitfall 3: Weaviate gRPC Port Missing in connect_to_local

**What goes wrong:** `weaviate.connect_to_local(host="localhost", port=8080)` without `grpc_port=50051` will fail when the Weaviate server has gRPC enabled (which it does in the Docker Compose).
**Why it happens:** Weaviate v4 client defaults `grpc_port=50051` but the Docker Compose maps `50051:50051` explicitly. If the port isn't listening, the client init fails.
**How to avoid:** Always pass `grpc_port=50051` explicitly when connecting to the benchmark Docker instance.
**Warning signs:** `WeaviateConnectionError` during `connect_to_local`.

### Pitfall 4: ChromaDB `upsert()` with `embedding_function` on Collection

**What goes wrong:** If `get_or_create_collection(name=..., embedding_function=some_fn)` is called and then `upsert(embeddings=[...])` is also called, ChromaDB may try to apply the embedding function again.
**How to avoid:** For the benchmark loader, create collections with `embedding_function=None` (default). Pass pre-computed vectors only via the `embeddings=` parameter in `upsert()`.
**Warning signs:** Vectors in ChromaDB have wrong dimension; embedding calls to Ollama during `upsert`.

### Pitfall 5: Weaviate Batch Error Handling

**What goes wrong:** Errors in `collection.batch.fixed_size()` context manager are not immediately raised per-object. They accumulate in `collection.batch.failed_objects`.
**Why it happens:** Weaviate v4 batch is designed for throughput — errors don't abort the batch.
**How to avoid:** After the batch context exits, check `col.batch.failed_objects` and log warnings for each failure. The skip-and-log D-07 requirement maps to checking this list after the `with batch:` block.
**Warning signs:** Batch succeeds (no exception) but inserted count is lower than expected.

### Pitfall 6: `test_phase6.py` Tuple Unpack Breakage (26 sites)

**What goes wrong:** `ValueError: too many values to unpack (expected 3, got 4)` on every test in `test_phase6.py`.
**Why it happens:** Extending `prepare_talk_record()` and related functions to return 4-element tuples while the test file still unpacks 3.
**How to avoid:** Phase 21 Wave 0 must include updating all 26 unpack sites in `test_phase6.py` before modifying `shared_transforms.py`.
**Warning signs:** All `TestPrepareTalkRecord` tests fail immediately.

---

## Code Examples

### Verified: ChromaDB upsert with pre-computed embeddings

```python
# Source: VERIFIED chromadb==1.5.7 live inspection
client = chromadb.HttpClient(host="localhost", port=8000)
col = client.get_or_create_collection(name="paragraphs")
col.upsert(
    ids=["para_1", "para_2"],
    documents=["text of para 1", "text of para 2"],
    metadatas=[{"talk_id": 1, "speaker_name": "Elder A"}, {"talk_id": 1, "speaker_name": "Elder A"}],
    embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...]],  # List[Sequence[float]]
)
```

### Verified: Weaviate collection create with no vectorizer

```python
# Source: Context7 /weaviate/weaviate-python-client (HIGH confidence)
import weaviate
import weaviate.classes as wvc

with weaviate.connect_to_local(host="localhost", port=8080, grpc_port=50051) as client:
    if not client.collections.exists("Paragraph"):
        client.collections.create(
            name="Paragraph",
            vectorizer_config=wvc.config.Configure.Vectorizer.none(),
            properties=[
                wvc.config.Property(name="talk_id", data_type=wvc.config.DataType.INT),
                wvc.config.Property(name="speaker_name", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="conference_year", data_type=wvc.config.DataType.INT),
                wvc.config.Property(name="topics", data_type=wvc.config.DataType.TEXT_ARRAY),
                # ... full schema
            ],
        )
```

### Verified: Weaviate batch insert with explicit vector

```python
# Source: Context7 /weaviate/weaviate-python-client (HIGH confidence)
from weaviate.util import generate_uuid5

col = client.collections.use("Paragraph")
with col.batch.fixed_size(batch_size=100) as batch:
    batch.add_object(
        properties={"talk_id": 123, "speaker_name": "Elder A"},
        uuid=generate_uuid5("para_456"),
        vector=[0.1, 0.2, 0.3, ...],  # list[float], 768 dims
    )
# After context exits, check for errors:
if col.batch.failed_objects:
    for err in col.batch.failed_objects:
        logger.warning("Weaviate batch error: %s", err)
```

### Verified: Qdrant create collection + payload index

```python
# Source: Context7 /qdrant/qdrant-client (HIGH confidence)
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

client = QdrantClient(host="localhost", port=6333)
if not client.collection_exists("paragraphs"):
    client.create_collection(
        collection_name="paragraphs",
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )
    client.create_payload_index("paragraphs", "talk_id", PayloadSchemaType.INTEGER)
    client.create_payload_index("paragraphs", "conference_year", PayloadSchemaType.INTEGER)
    client.create_payload_index("paragraphs", "speaker_name", PayloadSchemaType.KEYWORD)
```

### Verified: Qdrant upsert with uint64 ID

```python
# Source: Context7 /qdrant/qdrant-client (HIGH confidence)
import hashlib, struct
from qdrant_client.models import PointStruct

def _str_to_uint64(s: str) -> int:
    digest = hashlib.sha256(s.encode()).digest()
    return struct.unpack(">Q", digest[:8])[0]

client.upsert(
    collection_name="paragraphs",
    points=[
        PointStruct(
            id=_str_to_uint64("para_456"),
            vector=[0.1, 0.2, ...],        # list[float], 768 dims
            payload={"_doc_id": "para_456", "talk_id": 123},
        )
    ],
    wait=True,
)
```

### Verified: Ollama embed call

```python
# Source: VERIFIED ollama==0.6.1 in project virtualenv
import ollama

OLLAMA_URL = "http://localhost:11434"

def embed(text: str, model: str = "nomic-embed-text", url: str = OLLAMA_URL) -> list[float]:
    response = ollama.Client(host=url).embed(model=model, input=text)
    return list(response.embeddings[0])
```

`EmbedResponse.embeddings` is `Sequence[Sequence[float]]`. For single text input, `embeddings[0]` is the 768-element vector. [VERIFIED: `inspect.getsource(ollama.EmbedResponse)` in live env]

### Verified: Port-check conftest.py fixture

```python
# Source: socket.create_connection verified in live project virtualenv
import socket, pytest

def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

@pytest.fixture(scope="session")
def chromadb_available():
    if not _is_port_open("localhost", 8000):
        pytest.skip("ChromaDB not reachable at localhost:8000 — start Docker Compose")

@pytest.fixture(scope="session")
def weaviate_available():
    if not _is_port_open("localhost", 8080):
        pytest.skip("Weaviate not reachable at localhost:8080 — start Docker Compose")

@pytest.fixture(scope="session")
def qdrant_available():
    if not _is_port_open("localhost", 6333):
        pytest.skip("Qdrant not reachable at localhost:6333 — start Docker Compose")
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Weaviate v3 `client.schema.create_class()` | v4 `client.collections.create()` | BREAKING: v3 import style fails with weaviate-client >= 4.0 |
| Weaviate v3 `client.batch.add_data_object()` | v4 `collection.batch.fixed_size()` context manager | Different API entirely |
| Qdrant `client.search()` (deprecated) | `client.query_points()` | `search()` still works but `query_points()` is universal API |
| `ollama.embeddings()` (legacy) | `ollama.embed()` | Both available in v0.6.1; `embed()` is current |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| chromadb | ChromaDB loader | Yes | 1.5.7 | — |
| ollama (library) | embeddings.py | Yes | 0.6.1 | — |
| Ollama (server) | embed() calls | Not checked | — | Tests mock embed_fn; skip if unavailable |
| weaviate-client | Weaviate loader | No (not installed) | — | Must `pipenv install` |
| qdrant-client | Qdrant loader | No (not installed) | — | Must `pipenv install` |
| Docker / docker-compose | Integration tests | Not verified | — | Tests auto-skip via port check |
| ChromaDB server (:8000) | Integration test | Not running | — | Test auto-skips |
| Weaviate server (:8080) | Integration test | Not running | — | Test auto-skips |
| Qdrant server (:6333) | Integration test | Not running | — | Test auto-skips |

**Missing dependencies with no fallback:**
- `weaviate-client` and `qdrant-client` must be installed before any loader code can be imported. Wave 0 must add them to Pipfile and run `pipenv install`.

**Missing dependencies with fallback:**
- Ollama server: embedding helper needs it at runtime, but tests can inject a mock `embed_fn` that returns a fixed vector of correct dimension.
- Docker DB services: all loader integration tests auto-skip when ports are closed.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already installed) |
| Config file | None (no pytest.ini — pytest discovers tests/ directory) |
| Quick run command | `pipenv run py -m pytest tests/test_loaders_chromadb.py -x` |
| Full suite command | `pipenv run py -m pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BENCH-02 | ChromaDB upsert with pre-computed vectors; query returns expected para | integration | `pipenv run py -m pytest tests/test_loaders_chromadb.py -x` | Wave 0 |
| BENCH-03 | Weaviate typed schema creation; near-vector query returns expected object | integration | `pipenv run py -m pytest tests/test_loaders_weaviate.py -x` | Wave 0 |
| BENCH-04 | Qdrant payload indexes created; vector search returns expected point | integration | `pipenv run py -m pytest tests/test_loaders_qdrant.py -x` | Wave 0 |
| backward compat | test_shared_transforms.py still passes after 4-element tuples | unit | `pipenv run py -m pytest tests/test_shared_transforms.py -x` | Yes |
| backward compat | test_phase6.py still passes after tuple extension | unit | `pipenv run py -m pytest tests/test_phase6.py -x` | Yes (needs unpack fixes) |
| embed helper | embed() returns list[float] of len 768 | unit | `pipenv run py -m pytest tests/test_embeddings.py -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_phase6.py -x` (backward compat gate)
- **Per wave merge:** `pipenv run py -m pytest tests/ -x` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work` (integration tests may skip if Docker is down)

### Wave 0 Gaps

- [ ] `tests/conftest.py` — port-check fixtures + shared TalkBundle fixture
- [ ] `tests/test_loaders_chromadb.py` — insert + round-trip test for ChromaDB
- [ ] `tests/test_loaders_weaviate.py` — insert + near-vector test for Weaviate
- [ ] `tests/test_loaders_qdrant.py` — insert + vector search test for Qdrant
- [ ] `tests/test_embeddings.py` — unit test for `embed()` helper with mock Ollama
- [ ] Pipfile additions: `weaviate-client==4.20.5` and `qdrant-client==1.17.1`
- [ ] `tests/test_phase6.py` — update 26 tuple unpack sites before modifying shared_transforms

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `weaviate-client==4.20.5` is compatible with Weaviate server 1.37.1 | Standard Stack | Server 1.37 is newer than the 1.36.x→4.20.x documented matrix row; compatibility table shows 4.20 covers 1.36+; official docs state v4 requires >= 1.23.7 — 1.37 far exceeds this; risk LOW |
| A2 | `ollama.Client(host=url).embed(model, input)` is the correct multi-host call pattern | Code Examples | `ollama.embed()` module-level function uses default localhost; client instantiation with custom URL is standard but not explicitly tested here. Risk: LOW — documented pattern |
| A3 | Weaviate `col.batch.failed_objects` is a list accessible after the context manager exits | Pitfall 5 | Context7 shows `failed_objects` attribute on batch; if API changed this could be wrong. Risk LOW |

**If this table is empty for A1-A3:** Low-risk assumptions only. All critical API patterns (constructor signatures, upsert args, query methods) were verified against Context7 official docs or live code inspection.

---

## Open Questions

1. **Weaviate rich metadata type mapping for all fields**
   - What we know: `DataType.TEXT`, `DataType.INT`, `DataType.TEXT_ARRAY` are confirmed. `TalkMetadata` has `conference_month: str`, `topics: list[str]`, `verse_list: list[int]`.
   - What's unclear: Full list of Weaviate DataType values needed for every field in TalkMetadata, ParagraphData, CitationData, FootnoteData.
   - Recommendation: During implementation, iterate `asdict(model_instance)` to get all field names and types, then map to Weaviate DataType. A helper function that builds property lists from a dataclass type is cleaner than a hardcoded list.

2. **Qdrant payload index types for all metadata fields**
   - What we know: `INTEGER` for int fields, `KEYWORD` for string fields, `FLOAT` for float fields.
   - What's unclear: Which fields need indexes? All filterable fields or only high-cardinality ones?
   - Recommendation: Index at minimum: `talk_id` (INTEGER), `conference_year` (INTEGER), `speaker_name` (KEYWORD), `paragraph_id` (INTEGER), `book` (KEYWORD), `chapter` (INTEGER). Additional indexes can be added later; Qdrant allows adding indexes to existing collections.

3. **ChromaDB benchmark collection naming conflict with production**
   - What we know: Both benchmark and production ChromaDB loaders use `CHROMADB_COLLECTION_NAMES`.
   - What's unclear: Is the benchmark Docker instance (port 8000) always isolated from production?
   - Recommendation: Document clearly in loader docstring that `ChromaDBLoader` uses the production collection names. The benchmark Docker Compose is a separate instance, so naming collision only occurs if both services share a ChromaDB.

---

## Sources

### Primary (HIGH confidence)
- Context7 `/weaviate/weaviate-python-client` — connection, collection CRUD, batch insert, near_vector query, DataType, Vectorizer.none()
- Context7 `/qdrant/qdrant-client` — QdrantClient constructor, create_collection, create_payload_index, upsert, query_points, collection_exists
- Live code inspection (project virtualenv) — `inspect.signature(chromadb.Collection.upsert)`, `inspect.getsource(ollama.EmbedResponse)`, socket check behavior

### Secondary (MEDIUM confidence)
- PyPI registry (`pip index versions`) — weaviate-client 4.20.5 current, qdrant-client 1.17.1 current and exact Docker match
- Weaviate official docs (docs.weaviate.io) — v4 requires >= 1.23.7 (confirmed); 1.36.x → 4.20.x compatibility row confirmed

### Tertiary (LOW confidence)
- None — all critical claims were verified.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against live PyPI registry
- Architecture: HIGH — API patterns verified against Context7 official docs and live code inspection
- Backward compat analysis: HIGH — confirmed with live Python unpack test in project virtualenv
- Pitfalls: HIGH — Qdrant point ID constraint verified from Context7; Weaviate lifecycle verified from docs

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (30 days — all three clients are stable, not fast-moving for these APIs)
