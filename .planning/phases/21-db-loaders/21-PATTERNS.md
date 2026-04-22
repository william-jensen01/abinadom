# Phase 21: DB Loaders — Pattern Map

**Mapped:** 2026-04-21
**Files analyzed:** 13 (new/modified)
**Analogs found:** 11 / 13

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `loaders/__init__.py` | provider (ABC) | — | `benchmark/metrics.py` (dataclass pattern) | partial |
| `loaders/embeddings.py` | utility | request-response | `config/chromadb_client.py` (client factory) | role-match |
| `loaders/chromadb_loader.py` | service | CRUD | `extractors/phase6_chromadb_loader.py` | exact |
| `loaders/weaviate_loader.py` | service | CRUD | `extractors/phase6_chromadb_loader.py` | role-match |
| `loaders/qdrant_loader.py` | service | CRUD | `extractors/phase6_chromadb_loader.py` | role-match |
| `loaders/shared_transforms.py` | utility (extend) | transform | `loaders/shared_transforms.py` itself | exact |
| `tests/conftest.py` | test (new) | — | `tests/test_phase6.py` (fixture factories) | role-match |
| `tests/test_loaders_chromadb.py` | test | CRUD | `tests/test_phase6.py` (TestInsertCollection) | role-match |
| `tests/test_loaders_weaviate.py` | test | CRUD | `tests/test_phase6.py` (TestInsertCollection) | role-match |
| `tests/test_loaders_qdrant.py` | test | CRUD | `tests/test_phase6.py` (TestInsertCollection) | role-match |
| `tests/test_embeddings.py` | test | request-response | `tests/test_metrics.py` (unit style) | role-match |
| `tests/test_phase6.py` | test (modify) | — | itself | exact |
| `Pipfile` | config (modify) | — | itself | exact |

---

## Pattern Assignments

### `loaders/__init__.py` (ABC provider)

**Analog:** `benchmark/metrics.py` — module-level class definitions with `from dataclasses import dataclass`; pattern adapted to ABC.

**Imports pattern** — copy this structure:
```python
from abc import ABC, abstractmethod
from typing import Callable
from loaders.shared_transforms import TalkBundle
```

**Core ABC pattern:**
```python
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

**No error handling needed** — abstract base has no implementation body.

---

### `loaders/embeddings.py` (utility, request-response)

**Analog:** `config/chromadb_client.py` (lines 1–27) — single-responsibility factory module: module docstring, env-var constant, one public function.

**Module structure to copy from** `config/chromadb_client.py` lines 1–10:
```python
"""
<one-line purpose>

<connection/call detail paragraph>
"""

import os
import <client_lib>
```

**Core pattern** (adapt from RESEARCH.md verified pattern):
```python
import ollama

OLLAMA_URL = "http://localhost:11434"

def embed(
    text: str,
    model: str = "nomic-embed-text",
    url: str = OLLAMA_URL,
) -> list[float]:
    """Return a 768-dim vector from Ollama nomic-embed-text."""
    response = ollama.Client(host=url).embed(model=model, input=text)
    return list(response.embeddings[0])
```

**Error handling:** Let exceptions propagate — callers (loaders) handle at the batch level (D-07 skip-and-log). No try/except in embeddings.py itself.

---

### `loaders/chromadb_loader.py` (service, CRUD)

**Analog:** `extractors/phase6_chromadb_loader.py`

**Imports pattern** (lines 18–34 of phase6 loader):
```python
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle_rich
from loaders import BaseLoader

logger = logging.getLogger(__name__)
```

**Client init pattern** — from `config/chromadb_client.py` lines 16–26:
```python
self._client = chromadb.HttpClient(host=host, port=port)
```

**Collection get-or-create pattern** — from `extractors/phase6_chromadb_loader.py` lines 134–145:
```python
col = self._client.get_or_create_collection(name=coll_name)
```
Note: do NOT pass `embedding_function=` — benchmark collections use pre-computed vectors only.

**Batch chunk helper** (new private function, no existing analog):
```python
def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
```

**Core upsert pattern** (adapt from phase6 `insert_collection`, lines 57–103, but using pre-computed vectors):
```python
def load(self, bundle: TalkBundle) -> None:
    records = prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)
    for coll_name in self.COLLECTIONS:
        col = self._client.get_or_create_collection(name=coll_name)
        for batch in _chunks(records[coll_name], self.batch_size):
            ids   = [r[2] for r in batch]
            docs  = [r[0] for r in batch]
            metas = [r[1] for r in batch]
            vecs  = [r[3] for r in batch]
            try:
                col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)
            except Exception as e:
                logger.warning("ChromaDB batch failed for %s: %s", coll_name, e)
```

**_split() pattern from phase6** (lines 168–172) — not needed in new loader since we use index access `r[0]`, `r[1]`, `r[2]`, `r[3]` directly in list comprehensions (same pattern phase6 already uses internally).

**Error handling pattern** — skip-and-log per D-07: `logger.warning("... %s: %s", doc_id, e)` and `continue`. Mirror the WARNING log style used in `loaders/shared_transforms.py` lines 287–293:
```python
logger.warning(
    "Skipping talk_id=%s — failed validation. Errors: %s",
    metadata.talk_id,
    validation_report.errors,
)
```

---

### `loaders/weaviate_loader.py` (service, CRUD)

**Analog:** `extractors/phase6_chromadb_loader.py` — same class structure, same logger/logging pattern, same `__init__` + method pattern. Client library is different.

**Imports pattern:**
```python
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import DataType, Property, Configure
from weaviate.classes.query import MetadataQuery
from weaviate.util import generate_uuid5
from loaders import BaseLoader
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle_rich

logger = logging.getLogger(__name__)
```

**Constructor pattern** (extend BaseLoader `__init__`):
```python
def __init__(self, host, port, embed_fn, batch_size=100):
    super().__init__(host, port, embed_fn, batch_size)
    self._client = weaviate.connect_to_local(
        host=host, port=port, grpc_port=50051
    )
    self._ensure_schema()
```

**Schema creation (idempotent):**
```python
def _ensure_schema(self):
    if not self._client.collections.exists("Talk"):
        self._client.collections.create(
            name="Talk",
            vectorizer_config=wvc.config.Configure.Vectorizer.none(),
            properties=[...],
        )
```

**Batch insert pattern:**
```python
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
# After context exits, check failed_objects:
if col.batch.failed_objects:
    for err in col.batch.failed_objects:
        logger.warning("Weaviate batch error: %s", err)
```

**Client lifecycle — add `close()` method:**
```python
def close(self) -> None:
    self._client.close()
```

**Error handling:** Weaviate batch does NOT raise per-object — check `col.batch.failed_objects` after context manager exits.

---

### `loaders/qdrant_loader.py` (service, CRUD)

**Analog:** `extractors/phase6_chromadb_loader.py` — same structural pattern.

**Imports pattern:**
```python
import hashlib
import logging
import struct
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
from loaders import BaseLoader
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle_rich

logger = logging.getLogger(__name__)
```

**ID helper (no existing analog — new utility):**
```python
def _str_to_uint64(s: str) -> int:
    digest = hashlib.sha256(s.encode()).digest()
    return struct.unpack(">Q", digest[:8])[0]
```

**Constructor pattern:**
```python
def __init__(self, host, port, embed_fn, batch_size=100):
    super().__init__(host, port, embed_fn, batch_size)
    self._client = QdrantClient(host=host, port=port)
    self._ensure_collections()
```

**Collection creation (idempotent):**
```python
def _ensure_collections(self):
    for name in self.COLLECTIONS:
        if not self._client.collection_exists(name):
            self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=self.VECTOR_SIZE, distance=Distance.COSINE),
            )
            self._client.create_payload_index(name, "talk_id", PayloadSchemaType.INTEGER)
            self._client.create_payload_index(name, "conference_year", PayloadSchemaType.INTEGER)
            self._client.create_payload_index(name, "speaker_name", PayloadSchemaType.KEYWORD)
```

**Batch upsert pattern (skip-and-log per D-07):**
```python
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

---

### `loaders/shared_transforms.py` (utility, extend)

**Analog:** itself — extend, do not replace.

**Current 3-element tuple return type** (lines 94, 163, 211, 245):
```python
) -> tuple[str, dict[str, Any], str]:
```

**New 4-element return type for all `prepare_*` functions:**
```python
) -> tuple[str, dict[str, Any], str, list[float] | None]:
```

**Signature extension for `prepare_talk_bundle`** (line 256 in current file):
```python
def prepare_talk_bundle(
    metadata: TalkMetadata,
    paragraphs: TalkParagraphs,
    citations: TalkCitations,
    footnotes: TalkFootnotes,
    validation_report: ValidationReport,
    embed_fn=None,   # NEW optional param — backward compat when None
) -> dict[str, list[tuple[str, dict[str, Any], str, list[float] | None]]]:
```

**New `prepare_talk_bundle_rich` function** — mirrors `prepare_talk_bundle` but uses `rich_metadata` instead of `flatten_metadata` and always fills vectors:
```python
def prepare_talk_bundle_rich(
    metadata, paragraphs, citations, footnotes, validation_report,
    embed_fn=None,
) -> dict[str, list[tuple[str, dict[str, Any], str, list[float] | None]]]:
```

**New `_rich` variants of prepare_* functions** — same structure as existing `prepare_*` functions but call `rich_metadata()` instead of `flatten_metadata()`. Follow same docstring format as existing functions (lines 91–134).

**Vector fill pattern** — append at end of each record tuple:
```python
vector = embed_fn(document) if embed_fn is not None else None
return document, flat_meta, doc_id, vector
```

---

### `tests/conftest.py` (test fixture, new file)

**Analog:** `tests/test_phase6.py` lines 44–173 — factory functions `make_talk_metadata`, `make_paragraph`, `make_talk_paragraphs`, `make_citation`, `make_talk_citations`, `make_footnote`, `make_talk_footnotes`.

**Imports pattern** — copy sys.path pattern from all test files (lines 11–14 of `tests/test_phase6.py`):
```python
import socket
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest
from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport
from loaders.shared_transforms import TalkBundle
```

**Port-check helper and fixtures (new pattern, no direct analog):**
```python
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

**Shared TalkBundle fixture** (adapt from `test_phase6.py` `_make_full_bundle` helper, lines 642–701 — but minimal: talk_id=9999, 2 paras, 1 citation, 1 footnote):
```python
@pytest.fixture(scope="session")
def talk_bundle() -> TalkBundle:
    """Minimal deterministic bundle used by all 3 loader round-trip tests."""
    # ... use make_* factory functions from test_phase6.py as template
    # talk_id=9999, 2 paragraphs, 1 citation, 1 footnote, is_valid=True
```

**Factory functions:** Copy `make_talk_metadata`, `make_paragraph`, `make_talk_paragraphs`, `make_citation`, `make_talk_citations`, `make_footnote`, `make_talk_footnotes` verbatim from `tests/test_phase6.py` lines 44–173 into conftest.py (so all loader tests share the same fixtures without importing from test_phase6.py).

---

### `tests/test_loaders_chromadb.py` (test, CRUD integration)

**Analog:** `tests/test_phase6.py` class `TestInsertCollection` (lines 594–634).

**Test structure pattern** (adapt `TestInsertCollection.test_insert_collection_basic`, lines 595–607):
```python
class TestChromaDBLoader:
    def test_round_trip(self, chromadb_available, talk_bundle):
        from loaders.chromadb_loader import ChromaDBLoader
        from loaders.embeddings import embed
        loader = ChromaDBLoader("localhost", 8000, embed_fn=embed)
        loader.load(talk_bundle)
        # query with a known vector and assert returned id matches expected
```

**Import style:** Copy lines 11–14 from any test file (`sys.path.append(str(Path(__file__).parent.parent))`).

**Fixture dependency pattern:** `def test_...(self, chromadb_available, talk_bundle):` — fixture args auto-skip if port closed.

---

### `tests/test_loaders_weaviate.py` (test, CRUD integration)

**Analog:** Same as ChromaDB test — same structure, different loader and port fixture.

**Weaviate teardown pattern** (add to test class):
```python
def teardown_method(self, method):
    if hasattr(self, "loader"):
        self.loader.close()  # close gRPC connection
```

**Query assertion pattern** (from RESEARCH.md verified pattern):
```python
from weaviate.classes.query import MetadataQuery
col = loader._client.collections.use("Paragraph")
results = col.query.near_vector(
    near_vector=query_vector, limit=1,
    return_metadata=MetadataQuery(distance=True),
)
assert len(results.objects) == 1
```

---

### `tests/test_loaders_qdrant.py` (test, CRUD integration)

**Analog:** Same structural pattern as ChromaDB test.

**Query assertion pattern** (from RESEARCH.md verified pattern):
```python
results = loader._client.query_points(
    collection_name="paragraphs",
    query=query_vector,
    limit=1,
    with_payload=True,
)
assert len(results.points) == 1
assert results.points[0].payload["_doc_id"] == expected_doc_id
```

---

### `tests/test_embeddings.py` (test, unit)

**Analog:** `tests/test_metrics.py` lines 1–30 — simple unit test module: module docstring, sys.path, imports, flat test functions (not class-based).

**Mock embed_fn pattern** (no existing analog — new):
```python
def mock_embed(text: str) -> list[float]:
    """Return a deterministic 768-dim vector without calling Ollama."""
    return [0.1] * 768

def test_embed_returns_list_of_floats():
    result = mock_embed("hello world")
    assert isinstance(result, list)
    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)
```

**Live embed test (skip if Ollama down):**
```python
@pytest.fixture(scope="session")
def ollama_available():
    if not _is_port_open("localhost", 11434):
        pytest.skip("Ollama not reachable — skip live embed test")

def test_embed_live(ollama_available):
    from loaders.embeddings import embed
    result = embed("test text")
    assert len(result) == 768
```

---

### `tests/test_phase6.py` (modify — 26 tuple unpack sites)

**Analog:** itself — targeted find-and-replace only.

**Pattern to find** (3-element unpack, confirmed 26 sites per RESEARCH.md):
```python
doc, meta, doc_id = prepare_talk_record(...)
doc, meta, doc_id = records[0]
_, flat_meta, _ = records[0]
```

**Pattern to replace with** (4-element unpack — explicit discard style used consistently):
```python
doc, meta, doc_id, _ = prepare_talk_record(...)
doc, meta, doc_id, _ = records[0]
_, flat_meta, _, _ = records[0]
```

**Key sites by test class** (use Grep to find all before editing):
- `TestPrepareTalkRecord`: lines 231, 238, 244, 249, 263, 269, 274 (7 sites)
- `TestPrepareParagraphRecords`: lines 296, 303, 312, 333, 343, 365, 373 (7 sites)
- `TestPrepareCitationRecords`: lines 395, 404, 411, 419 (4 sites)
- `TestPrepareFootnoteRecords`: lines 450, 459, 465, 474 (4 sites)
- `TestPrepareTalkBundle`: lines 514, 555, 573 (3 sites) — plus one index-based access at line 555 `result["paragraphs"][0][2]` which is SAFE (index, not unpack)

**Safe (do NOT change):** Lines using index access — `r[0]`, `r[1]`, `r[2]` — in `_split()` in `phase6_chromadb_loader.py` (that file is NOT being modified).

---

### `Pipfile` (config, modify)

**Analog:** itself lines 6–14.

**Pattern to add** (under `[packages]` section after the `ollama = "*"` line):
```toml
weaviate-client = "==4.20.5"
qdrant-client = "==1.17.1"
```

---

## Shared Patterns

### Logger Initialization
**Source:** `loaders/shared_transforms.py` line 23; `extractors/phase6_chromadb_loader.py` line 35
**Apply to:** All new `loaders/*.py` files
```python
logger = logging.getLogger(__name__)
```

### sys.path Insertion
**Source:** `loaders/shared_transforms.py` lines 15–16; every test file lines 11–14
**Apply to:** All new loaders, all new test files
```python
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
```

### Skip-and-Log Error Handling (D-07)
**Source:** Decision D-07; logging style from `loaders/shared_transforms.py` lines 287–293
**Apply to:** `loaders/chromadb_loader.py`, `loaders/weaviate_loader.py`, `loaders/qdrant_loader.py`
```python
except Exception as e:
    logger.warning("...[DB] skip %s: %s", doc_id, e)
    continue  # or: do not append to points list
```

### Upsert Idempotency
**Source:** `extractors/phase6_chromadb_loader.py` line 96 — `collection.upsert()`
**Apply to:** All 3 loaders — use upsert/create_or_get semantics so re-runs are safe.

### Test Factory Function Style
**Source:** `tests/test_phase6.py` lines 44–173 (make_* functions with `defaults.update(kwargs)` pattern)
**Apply to:** `tests/conftest.py` (move shared factories here), `tests/test_loaders_*.py`
```python
def make_talk_metadata(**kwargs) -> TalkMetadata:
    defaults = dict(talk_id=9999, ...)
    defaults.update(kwargs)
    return TalkMetadata(**defaults)
```

### Mock embed_fn for Tests
**Source:** No existing analog — new pattern for Phase 21.
**Apply to:** All loader test files and `tests/test_embeddings.py`
```python
def _mock_embed(text: str) -> list[float]:
    return [0.1] * 768
```
Pass as `embed_fn=_mock_embed` when instantiating loaders in unit-level tests. Use real `embed` from `loaders/embeddings.py` only in integration tests that require Ollama.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `loaders/__init__.py` (BaseLoader ABC) | provider | — | No ABC classes exist in this codebase yet; only dataclasses and plain functions |
| `loaders/embeddings.py` | utility | request-response | Closest is `config/chromadb_client.py` (factory pattern), but ollama HTTP call pattern is entirely new |

---

## Critical Implementation Notes for Planner

1. **Wave ordering is mandatory:** Update `tests/test_phase6.py` 3-element unpacks BEFORE modifying `loaders/shared_transforms.py`. Otherwise all existing phase6 tests break during implementation. This must be Wave 0 step 1.

2. **Backward compat gate:** `tests/test_shared_transforms.py` and `tests/test_phase6.py` are the backward compat gates. Run after every wave: `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_phase6.py -x`.

3. **Weaviate client must be closed:** `WeaviateLoader` must have a `close()` method. Integration tests must call `loader.close()` in teardown. Without it, gRPC connections hang and subsequent test runs fail.

4. **Qdrant integer IDs:** String doc_ids like `"para_12345"` are NOT valid Qdrant point IDs. Use `_str_to_uint64(doc_id)` and store original string in `payload["_doc_id"]`.

5. **ChromaDB no embedding_function:** Benchmark collections must be created with `embedding_function=None` (default). Passing any embedding function AND pre-computed vectors causes double-embedding.

6. **`prepare_talk_bundle_rich` needed:** Weaviate and Qdrant loaders require `rich_metadata` (lists preserved) not `flatten_metadata` (lists stringified). This is why a separate `prepare_talk_bundle_rich` function is added to `shared_transforms.py`.

---

## Metadata

**Analog search scope:** `loaders/`, `extractors/`, `config/`, `tests/`, `benchmark/`
**Files scanned:** 8 source files read in full
**Pattern extraction date:** 2026-04-21
