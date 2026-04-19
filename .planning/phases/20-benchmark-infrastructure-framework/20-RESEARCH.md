# Phase 20: Benchmark Infrastructure & Framework — Research

**Researched:** 2026-04-18
**Domain:** Docker Compose vector DB stack, Python package extraction, dataclass design
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Functions **move** to `loaders/shared_transforms.py` (not copied, not re-exported from phase6). `shared_transforms.py` contains the canonical implementations with no DB-client dependencies.
- **D-02:** `extractors/phase6_chromadb_loader.py` gets a thin import block replacing its private implementations (see exact import block in CONTEXT.md).
- **D-03:** `phase6_chromadb_loader.py` keeps a backward-compat alias `_flatten_metadata = flatten_metadata` so `tests/test_phase6.py` continues to pass without modification.
- **D-04:** `QueryMetrics` fields: `p50_ms`, `p95_ms`, `p99_ms`, `mean_ms`, `min_ms`, `max_ms`, `query_count: int`, `failed_queries: int = 0`
- **D-05:** `UpsertMetrics` fields: `total_records: int`, `elapsed_seconds: float`, `records_per_second: float`
- **D-06:** `ConcurrencyMetrics` fields: `workers: int`, `total_queries: int`, `elapsed_seconds: float`, `throughput_qps: float`
- **D-07:** `MemoryMetrics` fields: `baseline_mb: float`, `peak_mb: float`, `delta_mb: float`
- **D-08:** `k=10` for all canonical queries as default retrieval depth.
- **D-09:** Paragraph queries cover 4 doctrinal themes: doctrinal core, scripture application, historical/prophetic events, practical living. Distribute ≥5 paragraph queries across these themes.
- **D-10:** Citation queries: ≥2 entries; at least one uses `{"book_name": "John"}` filter with `query_text="light of the world"`.
- Published ports: ChromaDB → 8000, Weaviate → 8080 + 50051, Qdrant → 6333 + 6334
- Benchmark Docker network name: `benchmark` (isolated from production `proxy` network)
- Vector dimension: 768 (nomic-embed-text output dimension — never hardcode a different value)
- All Python commands use `pipenv run py`

### Claude's Discretion

- Exact `CANONICAL_QUERIES` text strings within the approved themes
- Docker image tags for Weaviate and Qdrant (researcher should pick stable recent versions)
- `TalkBundle` type definition (dataclass, TypedDict, or type alias based on Phase 21 needs)

### Deferred Ideas (OUT OF SCOPE)

- `loaders/chromadb_loader.py`, `loaders/weaviate_loader.py`, `loaders/qdrant_loader.py` — Phase 21
- `benchmark/runner.py` — Phase 22
- Loading actual talk data into the DBs — Phase 21+
- Running queries against the DBs — Phase 22+
- Ollama container in Docker Compose — Ollama runs on the host
- Modifying `extractors/phase6_chromadb_loader.py` behavior — production loader not touched
- Authentication or TLS config for the benchmark DBs
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVAL-01 | User can start ChromaDB, Weaviate, and Qdrant locally via a single Docker Compose file | Docker image tags, healthcheck endpoints, and Compose config patterns verified below |
| BENCH-01 | User can transform talk data into ChromaDB-safe flat metadata and native rich metadata via shared `flatten_metadata` / `rich_metadata` / `prepare_*` functions | Source code in `phase6_chromadb_loader.py` fully read; extraction strategy confirmed by D-01/D-02/D-03 |
| BENCH-05 | User can measure upsert speed, query latency (p50/p95/p99), concurrency throughput, and memory delta via metric dataclasses and `recall_at_k` | Field schemas locked in D-04 through D-07; stdlib dataclasses only, no new dependencies |
| BENCH-06 | User can run a canonical query set (paragraph + citation queries with and without filters) as the standard workload for all three DBs | Query schema and theme structure locked in D-08 through D-11 |
</phase_requirements>

---

## Summary

Phase 20 is a pure foundation phase: no DB connections are made, no data is loaded, and no benchmarks run. The four deliverables are a Docker Compose stack, a shared Python transforms module extracted from existing code, metric dataclasses, and a canonical query list. All downstream phases (21–24) depend on these outputs.

The most complex task is the `shared_transforms.py` extraction. The source functions in `extractors/phase6_chromadb_loader.py` have already been read in full. They use only stdlib (`dataclasses.asdict`) and project model imports — no chromadb dependency inside the transform functions themselves. The extraction is surgical: move five `prepare_*` functions and `_flatten_metadata` to `loaders/shared_transforms.py`, replace them in `phase6_chromadb_loader.py` with an import block, and add a `_flatten_metadata = flatten_metadata` backward-compat alias. The existing 59 tests in `test_phase6.py` are currently green and must stay green.

For Docker, three stable pinned image tags have been verified against current releases. Health check endpoints are confirmed from official sources. The Compose file follows the style of `infra/docker-compose.yml` (pinned tags, `restart: unless-stopped`, named networks).

**Primary recommendation:** Execute extraction first (BENCH-01), then metric dataclasses (BENCH-05), canonical queries (BENCH-06), Docker Compose stack (EVAL-01), package markers, and unit tests last. No new pip dependencies are required for Phase 20 itself.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Docker Compose vector DB stack | Infra / Container | — | Standalone compose file; isolated `benchmark` network; no app-layer logic |
| `flatten_metadata` / `rich_metadata` / `prepare_*` | Library (no tier) | — | Pure data-transform functions; no network, no DB client, no framework |
| Metric dataclasses + `recall_at_k` | Library (no tier) | — | Stdlib dataclasses; consumed later by Phase 22 runner |
| `CANONICAL_QUERIES` list | Library (no tier) | — | Static Python list; consumed by Phase 22 runner |
| Unit tests | Test layer | — | pytest, no DB connections |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `dataclasses` | 3.14 (installed) | `@dataclass` for metrics + `asdict()` for transforms | Already used throughout the project; zero new deps |
| Docker / Docker Compose | 28.4.0 / v2.39.2 | Run all 3 vector DBs locally | Confirmed available on this machine |
| chromadb/chroma | 1.5.7 (use same as installed) | ChromaDB benchmark container | Matches installed Python client; avoids version skew |
| cr.weaviate.io/semitechnologies/weaviate | 1.37.1 | Weaviate benchmark container | Latest stable as of 2026-04-17 |
| qdrant/qdrant | v1.17.1 | Qdrant benchmark container | Latest stable as of 2026-03-27 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | installed | Test runner | All unit tests in Phase 20 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `chromadb/chroma:1.5.7` | `chromadb/chroma:latest` | `latest` drifts; pinned tag ensures the compose stack matches the installed Python client version |
| `cr.weaviate.io/semitechnologies/weaviate:1.37.1` | `semitechnologies/weaviate:1.37.1` | `cr.weaviate.io` is the official Weaviate registry; the Docker Hub mirror is deprecated as of recent releases [CITED: docs.weaviate.io/deploy/installation-guides/docker-installation] |
| `qdrant/qdrant:v1.17.1` | `qdrant/qdrant:latest` | Pinned prevents surprise upgrades between Phase 20 and Phase 21 |

**Installation:** No new pip packages needed for Phase 20. The `loaders/` and `benchmark/` packages use only stdlib and existing project model imports.

**Version verification:** [VERIFIED: Pipfile.lock] chromadb 1.5.7 installed. [VERIFIED: github.com/chroma-core/chroma/releases] Latest stable is 1.5.8 — using 1.5.7 (installed) for the Compose tag to prevent version skew. [VERIFIED: github.com/weaviate/weaviate/releases] v1.37.1 released 2026-04-17. [VERIFIED: hub.docker.com/r/qdrant/qdrant/tags] v1.17.1 is latest stable (pushed 23 days ago as of 2026-04-18).

---

## Architecture Patterns

### System Architecture Diagram

```
[Phase 20 Deliverables — No runtime data flow; all outputs consumed downstream]

  extractors/phase6_chromadb_loader.py
        |
        | D-01: move prepare_* + _flatten_metadata
        v
  loaders/shared_transforms.py          benchmark/metrics.py
  ┌────────────────────────────┐        ┌──────────────────────────────┐
  │ flatten_metadata()         │        │ @dataclass UpsertMetrics      │
  │ rich_metadata()            │        │ @dataclass QueryMetrics       │
  │ prepare_talk_record()      │        │ @dataclass ConcurrencyMetrics │
  │ prepare_paragraph_records()│        │ @dataclass MemoryMetrics      │
  │ prepare_citation_records() │        │ recall_at_k()                 │
  │ prepare_footnote_records() │        └──────────────┬───────────────┘
  │ prepare_talk_bundle()      │                       │
  │ TalkBundle type            │        benchmark/queries.py
  └────────────┬───────────────┘        ┌──────────────────────────────┐
               │                        │ CANONICAL_QUERIES list        │
               │ import (D-02)          │ (≥5 paragraph, ≥2 citation)   │
               v                        └──────────────────────────────┘
  extractors/phase6_chromadb_loader.py
  (thin import + _flatten_metadata alias per D-03)

  infra/docker-compose.vector-dbs.yml
  ┌──────────────────────────────────────────────────────────────┐
  │  chromadb/chroma:1.5.7   → localhost:8000 (HTTP)             │
  │  weaviate:1.37.1          → localhost:8080 (HTTP)            │
  │                             localhost:50051 (gRPC)           │
  │  qdrant/qdrant:v1.17.1    → localhost:6333 (HTTP REST)       │
  │                             localhost:6334 (gRPC)            │
  │  network: benchmark (isolated)                               │
  └──────────────────────────────────────────────────────────────┘

  Downstream consumers (Phase 21+):
  loaders/chromadb_loader.py   ← imports from shared_transforms.py
  loaders/weaviate_loader.py   ← imports from shared_transforms.py
  loaders/qdrant_loader.py     ← imports from shared_transforms.py
  benchmark/runner.py          ← imports from metrics.py, queries.py
```

### Recommended Project Structure

```
loaders/
├── __init__.py               # empty package marker
└── shared_transforms.py      # flatten_metadata, rich_metadata, prepare_*, TalkBundle

benchmark/
├── __init__.py               # empty package marker
├── metrics.py                # UpsertMetrics, QueryMetrics, ConcurrencyMetrics, MemoryMetrics, recall_at_k
└── queries.py                # CANONICAL_QUERIES list

infra/
└── docker-compose.vector-dbs.yml   # ChromaDB + Weaviate + Qdrant

tests/
├── test_shared_transforms.py  # ≥3 tests for flatten_metadata, rich_metadata, prepare_talk_bundle
└── test_metrics.py            # ≥3 tests for dataclasses and recall_at_k
```

### Pattern 1: sys.path.append Import Pattern

**What:** New modules in `loaders/` and `benchmark/` must be importable from `tests/`. The project uses `sys.path.append` at the top of every test file and extractor.

**When to use:** Every file in `loaders/` and `benchmark/` that imports from project models, plus every new test file.

**Example:**
```python
# Source: extractors/phase6_chromadb_loader.py (line 23), tests/test_phase6.py (line 14)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
```

For `loaders/shared_transforms.py` (one directory deep), `parent.parent` resolves to the project root, allowing imports of `models.*` and `config.*`.

For `tests/test_shared_transforms.py` (also one deep in `tests/`), the same `parent.parent` pattern works identically.

### Pattern 2: Dataclass with Default Field

**What:** Fields with defaults must come after fields without defaults in `@dataclass`. `QueryMetrics.failed_queries` has `default=0` so it must be last.

**Example:**
```python
# Source: confirmed via CONTEXT.md D-04 and Python @dataclass rules
from dataclasses import dataclass

@dataclass
class QueryMetrics:
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    query_count: int
    failed_queries: int = 0
```

### Pattern 3: Docker Compose Style (project convention)

**What:** Follow `infra/docker-compose.yml` style — pinned image tags, `restart: unless-stopped`, explicit named network with `driver: bridge`.

**Example:**
```yaml
# Source: infra/docker-compose.yml (read directly)
services:
  chromadb:
    image: chromadb/chroma:1.5.7
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - chromadb_data:/data
    networks:
      - benchmark
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

networks:
  benchmark:
    name: benchmark
    driver: bridge

volumes:
  chromadb_data:
```

### Pattern 4: recall_at_k Implementation

**What:** Intersection-based recall — count how many retrieved IDs from `candidate_ids[:k]` appear in `baseline_ids[:k]`, divide by k.

**Example:**
```python
# Source: SPEC acceptance criterion: recall_at_k(["a","b","c"], ["a","c","d"], k=3) -> 2/3
def recall_at_k(baseline_ids: list[str], candidate_ids: list[str], k: int) -> float:
    baseline_set = set(baseline_ids[:k])
    candidate_set = set(candidate_ids[:k])
    if k == 0:
        return 0.0
    return len(baseline_set & candidate_set) / k
```

### Anti-Patterns to Avoid

- **Importing chromadb inside shared_transforms.py:** The SPEC explicitly requires `loaders/shared_transforms.py` to be importable without installing chromadb. The existing `_flatten_metadata` and `prepare_*` functions in `phase6_chromadb_loader.py` use only `from dataclasses import asdict` and model imports — confirm no chromadb import leaks when moving them.
- **Using `TalkBundle` as the same tuple type in shared_transforms.py:** In `phase6_chromadb_loader.py`, `TalkBundle` is `tuple[TalkMetadata, TalkParagraphs, TalkCitations, TalkFootnotes, ValidationReport]`. The `shared_transforms.py` version should be the same definition (all five model types are importable without chromadb). Keep it as a type alias, not a new dataclass, to avoid breaking `load_talk_bundles` in phase6 which iterates `for metadata, paragraphs, citations, footnotes, validation_report in bundles`.
- **Modifying phase6_chromadb_loader.py behavior:** Only the import block and backward-compat alias are added. No logic in `insert_collection`, `load_talk_bundles`, or `generate_verification_report` is touched.
- **Using `latest` Docker tags:** Pinned tags prevent unexpected behavior when a container image is rebuilt between Phase 20 and Phase 21 testing.
- **Putting `benchmark/results/` in git:** The SPEC marks this as gitignored runtime output.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Metadata flattening for ChromaDB | Custom serializer | `_flatten_metadata` (already exists, just move it) | Logic is tested with 7 existing test cases in test_phase6.py; it handles None, empty lists, int lists, str lists, and scalar passthrough correctly |
| Metric p50/p95/p99 computation | Custom percentile logic | Stdlib `statistics` or `numpy` in Phase 22 | Phase 20 only defines the *schema*; computation happens in Phase 22's runner |
| Docker healthcheck polling | Custom shell loop | Docker Compose `healthcheck:` directive | Native Compose feature; works with `depends_on: condition: service_healthy` in Phase 21 |

**Key insight:** The transform functions already exist and are tested. The extraction is a move + import delegation, not a rewrite.

---

## Common Pitfalls

### Pitfall 1: ChromaDB API Version in Healthcheck URL

**What goes wrong:** Using `/api/v2/heartbeat` when the installed image serves `/api/v1/heartbeat`, or vice versa.

**Why it happens:** ChromaDB 1.x migrated from v1 to v2 API routes; the SPEC acceptance criterion explicitly lists `curl http://localhost:8000/api/v1/heartbeat`.

**How to avoid:** The SPEC acceptance criterion uses `/api/v1/heartbeat`. Use that exact path in the Docker healthcheck `test:` command. Both `/api/v1/heartbeat` and `/api/v2/heartbeat` appear to be supported in current images [MEDIUM confidence: WebSearch shows both used in community examples] but the SPEC is the authoritative source for which URL the acceptance test uses.

**Warning signs:** `curl` returns 404 in the healthcheck; container stays in `starting` state indefinitely.

### Pitfall 2: Qdrant healthz Port Confusion

**What goes wrong:** Using port 6334 for `/healthz` when the HTTP REST API (including healthz) is on port 6333.

**Why it happens:** One WebSearch result stated healthz runs on 6334; the official Qdrant API reference at `api.qdrant.tech` confirms it runs on **port 6333**. Port 6334 is the gRPC port.

**How to avoid:** Use `curl http://localhost:6333/healthz` for the healthcheck. The SPEC acceptance criterion confirms `curl http://localhost:6333/healthz` returns HTTP 200.

**Warning signs:** healthcheck curl times out (no service on 6334 for HTTP).

### Pitfall 3: sys.path Not Set in loaders/ Modules

**What goes wrong:** `from models.talk_metadata import TalkMetadata` fails in `loaders/shared_transforms.py` when called from a context where the project root is not on `sys.path`.

**Why it happens:** The project has no `setup.cfg`, no `pyproject.toml`, and no `pip install -e .` — it relies on the `sys.path.append` pattern at module top.

**How to avoid:** Add the standard project path block at the top of `loaders/shared_transforms.py`:
```python
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
```
`__file__` for `loaders/shared_transforms.py` is `<project_root>/loaders/shared_transforms.py`, so `parent.parent` resolves to `<project_root>` — identical to how `extractors/phase6_chromadb_loader.py` does it.

**Warning signs:** `ModuleNotFoundError: No module named 'models'` when running tests.

### Pitfall 4: Weaviate Image Registry

**What goes wrong:** Using `semitechnologies/weaviate:1.37.1` (Docker Hub path) instead of `cr.weaviate.io/semitechnologies/weaviate:1.37.1` (official registry).

**Why it happens:** Docker Hub mirrors may lag or be deprecated. Weaviate's official Docker installation docs specify `cr.weaviate.io` as the authoritative registry.

**How to avoid:** Use the full `cr.weaviate.io/semitechnologies/weaviate:1.37.1` image path.

**Warning signs:** `docker pull semitechnologies/weaviate:1.37.1` may succeed but lag behind official releases.

### Pitfall 5: backward-compat alias placement in phase6

**What goes wrong:** `_flatten_metadata = flatten_metadata` is placed before the `from loaders.shared_transforms import ...` block, causing a `NameError`.

**Why it happens:** The alias references `flatten_metadata` which is only defined after the import.

**How to avoid:** Place the alias *after* the import block:
```python
from loaders.shared_transforms import (
    flatten_metadata,
    ...
)
_flatten_metadata = flatten_metadata   # backward-compat for tests/test_phase6.py
```

---

## Code Examples

Verified patterns from official sources and existing codebase:

### Docker Compose: Full vector-dbs Stack

```yaml
# Source: infra/docker-compose.yml (style), official docs for each DB
services:
  chromadb:
    image: chromadb/chroma:1.5.7
    container_name: chromadb-benchmark
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - chromadb_data:/data
    networks:
      - benchmark
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.37.1
    container_name: weaviate-benchmark
    restart: unless-stopped
    ports:
      - "8080:8080"
      - "50051:50051"
    environment:
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"
      PERSISTENCE_DATA_PATH: "/var/lib/weaviate"
      DEFAULT_VECTORIZER_MODULE: "none"
      CLUSTER_HOSTNAME: "weaviate-benchmark"
    volumes:
      - weaviate_data:/var/lib/weaviate
    networks:
      - benchmark
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider",
             "http://localhost:8080/v1/.well-known/ready"]
      interval: 10s
      timeout: 30s
      retries: 5
      start_period: 30s

  qdrant:
    image: qdrant/qdrant:v1.17.1
    container_name: qdrant-benchmark
    restart: unless-stopped
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - benchmark
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

networks:
  benchmark:
    name: benchmark
    driver: bridge

volumes:
  chromadb_data:
  weaviate_data:
  qdrant_data:
```

### shared_transforms.py: Module Header

```python
# Source: extractors/phase6_chromadb_loader.py (pattern)
"""
Shared data transformation utilities for all vector DB loaders.

Contains flatten_metadata, rich_metadata, and all prepare_* functions.
Importable without installing chromadb, weaviate-client, or qdrant-client.
"""
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).parent.parent))

from models.talk_metadata import TalkMetadata
from models.paragraph_data import TalkParagraphs
from models.citation_data import TalkCitations
from models.footnote_data import TalkFootnotes
from models.validation_report import ValidationReport

# Type alias — kept as tuple to match phase6 iteration pattern
TalkBundle = tuple[TalkMetadata, TalkParagraphs, TalkCitations, TalkFootnotes, ValidationReport]
```

### benchmark/queries.py: CANONICAL_QUERIES Structure

```python
# Source: CONTEXT.md D-08 through D-11
from typing import Any

CANONICAL_QUERIES: list[dict[str, Any]] = [
    # Theme 1: Doctrinal core
    {
        "query_text": "the Atonement of Jesus Christ brings healing and hope to all who repent",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # Theme 2: Scripture application
    {
        "query_text": "how prophets applied the scriptures to teach eternal truths",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # Theme 3: Historical/prophetic events
    {
        "query_text": "the restoration of the gospel through the Prophet Joseph Smith",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # Theme 4: Practical living
    {
        "query_text": "family prayer and scripture study strengthen the home",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # Theme 1 (second): Faith and resurrection
    {
        "query_text": "faith in the resurrection of Jesus Christ overcomes death",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # Theme 4 (second): Temple and missionary work
    {
        "query_text": "temple worship and missionary service as expressions of discipleship",
        "k": 10,
        "collection": "paragraphs",
        "filter": None,
    },
    # Citation query 1: filtered (D-10)
    {
        "query_text": "light of the world",
        "k": 10,
        "collection": "citations",
        "filter": {"book_name": "John"},
    },
    # Citation query 2: unfiltered
    {
        "query_text": "love one another as I have loved you",
        "k": 10,
        "collection": "citations",
        "filter": None,
    },
]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ChromaDB `/api/v1/heartbeat` | `/api/v2/heartbeat` also available in 1.5.x | ~1.4.x | Both endpoints work; SPEC acceptance criterion uses v1 path; use `/api/v1/heartbeat` |
| `semitechnologies/weaviate` Docker Hub image | `cr.weaviate.io/semitechnologies/weaviate` | ~1.24+ | Official registry; Docker Hub mirror may lag |
| Weaviate `v1/meta` readiness poll | `v1/.well-known/ready` | Long-standing | `/v1/.well-known/ready` is the official healthcheck path |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `chromadb/chroma:1.5.7` is the correct Docker image tag to match the installed Python client | Standard Stack | Mismatch between Python client and server version may cause API errors; mitigated by using exact installed version |
| A2 | Weaviate `DEFAULT_VECTORIZER_MODULE: "none"` is the correct env var to disable auto-vectorization (no Ollama inside container) | Code Examples | Weaviate may attempt to call a vectorizer and fail on startup; confirm via `docker compose logs weaviate` |
| A3 | Qdrant requires no mandatory environment variables for a local dev instance (no auth, default storage path) | Standard Stack | If a config file is required, the container may exit immediately; mitigated by official Qdrant quickstart example which shows no env vars needed |
| A4 | `loaders/` and `benchmark/` directories do not yet exist and need to be created | Architecture | Confirmed: `ls` showed neither directory exists in the project root |
| A5 | `wget` is available inside the Weaviate container for the healthcheck (using `--spider` flag) | Code Examples | If wget is absent, use `curl` instead; Weaviate docs show both patterns [CITED: weaviate.io] |

---

## Open Questions

1. **ChromaDB Docker volume path**
   - What we know: The official Compose example uses `/data` as the volume target for `chromadb/chroma`
   - What's unclear: Whether the Chroma server respects `IS_PERSISTENT=TRUE` env var or uses `/data` by default
   - Recommendation: Use `volumes: chromadb_data:/data` as shown in official docs; no env var needed for default persistence

2. **Weaviate CLUSTER_HOSTNAME**
   - What we know: Weaviate docs recommend setting `CLUSTER_HOSTNAME` for single-node to avoid log warnings
   - What's unclear: Whether it is truly required or just recommended for single-node local dev
   - Recommendation: Include `CLUSTER_HOSTNAME: "weaviate-benchmark"` as a precaution; it has no downside

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | `infra/docker-compose.vector-dbs.yml` | ✓ | 28.4.0 | — |
| Docker Compose | `infra/docker-compose.vector-dbs.yml` | ✓ | v2.39.2 | — |
| Python | `loaders/`, `benchmark/`, `tests/` | ✓ | 3.14.2 | — |
| pipenv | All Python commands | ✓ | (installed) | — |
| pytest | `tests/test_shared_transforms.py`, `tests/test_metrics.py` | ✓ | (installed) | — |
| chromadb Python client | `tests/test_phase6.py` (existing) | ✓ | 1.5.7 | — |
| weaviate-client | Phase 20 Python code | Not needed | — | No client used in Phase 20 |
| qdrant-client | Phase 20 Python code | Not needed | — | No client used in Phase 20 |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** weaviate-client and qdrant-client are not needed in Phase 20 (no DB connections are made). They will be needed in Phase 21.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (installed in virtualenv) |
| Config file | None (uses default pytest discovery) |
| Quick run command | `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py tests/test_phase6.py -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BENCH-01 | `flatten_metadata` removes None, joins lists correctly | unit | `pipenv run py -m pytest tests/test_shared_transforms.py -x` | ❌ Wave 0 |
| BENCH-01 | `rich_metadata` strips None, preserves lists | unit | `pipenv run py -m pytest tests/test_shared_transforms.py -x` | ❌ Wave 0 |
| BENCH-01 | `prepare_talk_bundle` returns dict with 4 keys | unit | `pipenv run py -m pytest tests/test_shared_transforms.py -x` | ❌ Wave 0 |
| BENCH-01 | `test_phase6.py` regression (59 tests still green) | unit | `pipenv run py -m pytest tests/test_phase6.py -x -q` | ✅ (59 passing) |
| BENCH-05 | `recall_at_k(["a","b","c"], ["a","c","d"], k=3)` returns `2/3` | unit | `pipenv run py -m pytest tests/test_metrics.py -x` | ❌ Wave 0 |
| BENCH-05 | All four metric dataclasses are importable | unit | `pipenv run py -m pytest tests/test_metrics.py -x` | ❌ Wave 0 |
| BENCH-06 | `CANONICAL_QUERIES` has ≥7 entries, all required keys | unit | Can be verified as part of test_metrics.py or a separate quick smoke | ❌ Wave 0 |
| EVAL-01 | Docker Compose `up -d` exits 0, health checks pass | manual smoke | `docker compose -f infra/docker-compose.vector-dbs.yml up -d` + curl | — (runtime) |

### Sampling Rate

- **Per task commit:** `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py -x -q`
- **Per wave merge:** `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py tests/test_phase6.py -q`
- **Phase gate:** Full suite above green + `docker compose -f infra/docker-compose.vector-dbs.yml up -d` health checks pass

### Wave 0 Gaps

- [ ] `tests/test_shared_transforms.py` — covers BENCH-01 (flatten_metadata, rich_metadata, prepare_talk_bundle)
- [ ] `tests/test_metrics.py` — covers BENCH-05 (dataclasses, recall_at_k) and BENCH-06 (CANONICAL_QUERIES structure)

*(No framework install needed — pytest already installed)*

---

## Security Domain

> `security_enforcement` is not set to false in `.planning/config.json` — section included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Local dev only; benchmark network isolated; anonymous access per SPEC |
| V3 Session Management | No | No sessions; pure data transforms and Docker stack |
| V4 Access Control | No | No multi-user; single-developer local benchmark |
| V5 Input Validation | Minimal | `recall_at_k` parameter validation (k > 0 guard) |
| V6 Cryptography | No | No secrets, tokens, or encryption in Phase 20 |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Exposed vector DB ports on non-loopback | Information Disclosure | Compose publishes to `127.0.0.1:PORT` (loopback only) — enforce via `"127.0.0.1:8000:8000"` port syntax if on a shared machine |
| No authentication on benchmark DBs | Spoofing | Acceptable — local dev only per SPEC; do not add auth in Phase 20 |

**Note:** The SPEC explicitly scopes this to local dev, anonymous access only. No security hardening is in scope for Phase 20.

---

## Sources

### Primary (HIGH confidence)

- `extractors/phase6_chromadb_loader.py` — read in full; all 5 `prepare_*` functions and `_flatten_metadata` confirmed present; no chromadb import inside transform functions
- `tests/test_phase6.py` — read in full; 59 tests confirmed passing via `pipenv run py -m pytest`; confirmed `_flatten_metadata` is imported directly by tests
- `Pipfile.lock` — chromadb 1.5.7 installed; Python 3.14.2 confirmed
- Docker CLI — version 28.4.0; Compose v2.39.2 confirmed available
- `.planning/phases/20-benchmark-infrastructure-framework/20-CONTEXT.md` — all locked decisions read
- `.planning/phases/20-benchmark-infrastructure-framework/20-SPEC.md` — all 7 requirements and acceptance criteria read
- [docs.weaviate.io/deploy/installation-guides/docker-installation](https://docs.weaviate.io/deploy/installation-guides/docker-installation) — v1.37.0 image tag, env vars, health endpoint confirmed
- [api.qdrant.tech/api-reference/service/healthz](https://api.qdrant.tech/api-reference/service/healthz) — `/healthz` on port 6333 confirmed
- [github.com/chroma-core/chroma/releases](https://github.com/chroma-core/chroma/releases) — 1.5.8 latest stable; 1.5.7 used to match installed client
- [github.com/weaviate/weaviate/releases](https://github.com/weaviate/weaviate/releases) — v1.37.1 latest stable (2026-04-17)
- [hub.docker.com/r/qdrant/qdrant/tags](https://hub.docker.com/r/qdrant/qdrant/tags) — v1.17.1 latest stable (pushed 23 days ago)

### Secondary (MEDIUM confidence)

- [weaviate.io — /v1/.well-known/ready healthcheck](https://weaviate.io/developers/weaviate/api/rest_legacy/well-known) — confirmed correct healthcheck path with wget `--spider`
- [docs.trychroma.com/guides/deploy/docker](https://docs.trychroma.com/guides/deploy/docker) — `/api/v1/heartbeat` endpoint confirmed; volume path `/data` confirmed
- [qdrant.tech/documentation/guides/installation](https://qdrant.tech/documentation/guides/installation/) — ports 6333 (HTTP) and 6334 (gRPC) confirmed

### Tertiary (LOW confidence)

- WebSearch result claiming healthz is on port 6334 — CONTRADICTED by official API reference; use port 6333

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified via Pipfile.lock, GitHub releases, Docker Hub
- Architecture: HIGH — all source files read; extraction plan directly derived from existing code
- Docker Compose: HIGH — official docs for all three DBs read; healthcheck endpoints confirmed
- Pitfalls: HIGH — derived from reading actual source code and tests, not generic advice

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (stable stack; Weaviate and Qdrant release frequently — re-verify image tags if planning is delayed)
