# Vector Database Evaluation Design
**Date:** 2026-04-17
**Goal:** Evaluate ChromaDB, Weaviate, and Qdrant side-by-side to decide which vector database to adopt for the LDS Scripture Citation Index MCP server.

---

## Background

The project currently uses ChromaDB over HTTP with 4 collections:
- `conference_talks` — one record per talk
- `conference_talk_paragraphs` — one record per non-annotation paragraph
- `conference_talk_citations` — one record per citation
- `conference_talk_footnotes` — one record per footnote

The client is abstracted behind `config/chromadb_client.py`, which is the natural swap point for a future migration. The record transformation layer (`prepare_*` functions in `extractors/phase6_chromadb_loader.py`) is DB-agnostic and will be extracted into a shared module.

---

## Evaluation Criteria

| Criterion | Description |
|---|---|
| Query quality | Semantic search relevance across paragraphs and citations |
| Performance | p50/p95/p99 query latency |
| Filtering | Metadata filter accuracy alongside vector search |
| Concurrent load | Throughput and degradation under 10 and 25 parallel workers |
| Upsert speed | Records/sec per collection during bulk load |
| Recall quality | Result set overlap vs ChromaDB baseline at k=10 and k=50 |
| Memory footprint | RSS delta during concurrent query phase |

---

## Architecture

### Approach: Independent loaders + shared benchmark orchestrator

Each DB gets its own loader that handles DB-native concerns (schema, IDs, indexing). A single benchmark runner imports all three, runs identical workloads, and produces a structured report.

```
loaders/
  shared_transforms.py          # extracted prepare_* fns + rich_metadata() variant
  chromadb_loader.py            # thin wrapper over existing phase6 insertion logic
  weaviate_loader.py            # schema creation, UUID mapping, native array payloads
  qdrant_loader.py              # collection + payload index creation, string IDs

benchmark/
  runner.py                     # CLI orchestrator: load → query → concurrent → report
  queries.py                    # canonical query set
  metrics.py                    # UpsertMetrics, QueryMetrics, ConcurrencyMetrics, memory
  results/                      # output JSON/CSV reports (gitignored)

infra/
  docker-compose.vector-dbs.yml # Weaviate + Qdrant + ChromaDB services
```

`extractors/phase6_chromadb_loader.py` is **not modified** — it remains the production loader. `loaders/chromadb_loader.py` is a benchmark-only wrapper.

---

## Docker Setup

**File:** `infra/docker-compose.vector-dbs.yml`

```yaml
services:
  chromadb:
    image: chromadb/chroma:latest
    ports: ["8000:8000"]
    volumes: [chroma_data:/chroma/chroma]

  weaviate:
    image: semitechnologies/weaviate:latest
    ports: ["8080:8080", "50051:50051"]
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"
      PERSISTENCE_DATA_PATH: /var/lib/weaviate
      DEFAULT_VECTORIZER_MODULE: none
      ENABLE_MODULES: ""
    volumes: [weaviate_data:/var/lib/weaviate]

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]
    volumes: [qdrant_data:/qdrant/storage]
```

### Environment Variables

| DB | Env var | Example |
|---|---|---|
| ChromaDB | `CHROMADB_HOST` / `CHROMADB_PORT` | `192.168.1.x` / `8000` |
| Weaviate | `WEAVIATE_URL` | `http://192.168.1.x:8080` |
| Qdrant | `QDRANT_URL` | `http://192.168.1.x:6333` |
| Ollama | `OLLAMA_URL` | `http://192.168.1.x:11434` |

All ports are defaults — adjust to available ports at deploy time.

---

## Shared Transforms

**File:** `loaders/shared_transforms.py`

Extracted verbatim from `extractors/phase6_chromadb_loader.py`, plus a `rich_metadata()` variant:

```python
def flatten_metadata(meta: dict) -> dict   # existing: scalars only (ChromaDB)
def rich_metadata(meta: dict) -> dict      # strips None, keeps lists as-is (Weaviate/Qdrant)

prepare_talk_record(metadata, annotation_texts) -> tuple
prepare_paragraph_records(paragraphs, talk_metadata) -> tuple
prepare_citation_records(citations) -> list
prepare_footnote_records(footnotes) -> list
prepare_talk_bundle(metadata, paragraphs, citations, footnotes, validation_report) -> dict

TalkBundle = tuple[TalkMetadata, TalkParagraphs, TalkCitations, TalkFootnotes, ValidationReport]
```

`flatten_metadata()` is used by the ChromaDB loader. `rich_metadata()` is used by Weaviate and Qdrant loaders — it preserves native array types that ChromaDB cannot store, recovering metadata fidelity lost in the current implementation.

---

## Loaders

All three loaders expose a uniform interface consumed by the benchmark runner:

```python
def load(bundles: list[TalkBundle], client, embedding_fn) -> dict
# Returns: {talks_inserted, paragraphs_inserted, citations_inserted, footnotes_inserted, elapsed_sec}
```

### ChromaDB (`loaders/chromadb_loader.py`)

Thin wrapper. Reuses `insert_collection()` and collection management from `phase6_chromadb_loader.py`. Uses `flatten_metadata()`.

### Weaviate (`loaders/weaviate_loader.py`)

Additional responsibilities:
- `create_schema(client)` — defines 4 Weaviate collections with typed properties before insert
- `to_uuid(string_id) -> UUID` — deterministic `uuid5(NAMESPACE_DNS, string_id)` so IDs are stable across runs
- Uses `rich_metadata()` — native array support
- Inserts pre-computed Ollama vectors via `client.batch.dynamic()`

### Qdrant (`loaders/qdrant_loader.py`)

Additional responsibilities:
- `create_collections(client, vector_dim=768)` — creates 4 collections with `Cosine` distance metric; 768 is the output dimension of `nomic-embed-text`
- `create_payload_indexes(client)` — indexes `speaker_name`, `conference_year`, `conference_month`, `book` for O(log n) filtering
- Uses `rich_metadata()` — full JSON payload support
- Inserts as `PointStruct` batches with string IDs (no UUID mapping needed)

---

## Benchmark Runner

### Canonical Query Set (`benchmark/queries.py`)

**Paragraph queries** (against `conference_talk_paragraphs`):

| Query | k | Filter | Purpose |
|---|---|---|---|
| "faith in Jesus Christ" | 10 | none | baseline semantic search |
| "tithing and consecration" | 10 | none | topical semantic search |
| "revelation and personal prayer" | 10 | speaker_name: Russell M. Nelson | filtered semantic search |
| "covenant path" | 10 | conference_year: 2020 | year filter |
| "eternal life" | 50 | conference_year: 2021 | high-k + filter stress case |

**Citation queries** (against `conference_talk_citations`):

| Query | k | Filter | Purpose |
|---|---|---|---|
| "faith and doubt" | 10 | book: Moroni | semantic + book filter |
| "faith hope charity" | 20 | none | broad citation recall |

### Metrics (`benchmark/metrics.py`)

```python
@dataclass
class UpsertMetrics:
    total_elapsed_sec: float
    records_per_sec: dict[str, float]   # per collection

@dataclass
class QueryMetrics:
    p50_ms: float
    p95_ms: float
    p99_ms: float
    per_query: list[dict]               # latency per canonical query

@dataclass
class ConcurrencyMetrics:
    workers: int                        # 10 or 25
    total_queries: int
    elapsed_sec: float
    throughput_qps: float
    error_count: int

@dataclass
class MemoryMetrics:
    rss_before_mb: float
    rss_after_mb: float
    delta_mb: float
```

Memory is captured via `psutil.Process().memory_info().rss` before and after the concurrent query phase.

Recall is computed as result-set overlap between each DB and the ChromaDB baseline:
```python
def recall_at_k(baseline_ids: list[str], candidate_ids: list[str], k: int) -> float
```

### Runner CLI (`benchmark/runner.py`)

```
pipenv run py benchmark/runner.py [options]

Options:
  --upsert-limit INT    talks to load for upsert benchmarking (default: 500)
  --query-limit INT     talks loaded before query benchmarking (default: 2000)
  --dbs TEXT            comma-separated subset to run, e.g. chromadb,qdrant (default: all)
```

**Execution flow:**
1. Connect to all three DBs and Ollama; validate reachability
2. Load `--upsert-limit` bundles into each DB; record `UpsertMetrics`
3. Top up to `--query-limit` bundles (upsert delta only)
4. Run canonical paragraph + citation queries against each DB; record `QueryMetrics`
5. Run concurrent load at 10 workers → `ConcurrencyMetrics`
6. Run concurrent load at 25 workers → `ConcurrencyMetrics`
7. Capture `MemoryMetrics` around step 6
8. Compute recall overlap (ChromaDB as baseline)
9. Write `benchmark/results/YYYY-MM-DD-HH-MM.json`
10. Print summary table to stdout

### Output Format

```json
{
  "run_at": "2026-04-17T14:32:00",
  "upsert_limit": 500,
  "query_limit": 2000,
  "dbs": {
    "chromadb": {
      "upsert": { ... },
      "queries": { ... },
      "concurrency_10": { ... },
      "concurrency_25": { ... },
      "memory": { ... }
    },
    "weaviate": { ... },
    "qdrant": { ... }
  },
  "recall": {
    "weaviate_vs_chromadb": { "k10": 0.87, "k50": 0.91 },
    "qdrant_vs_chromadb":   { "k10": 0.93, "k50": 0.95 }
  }
}
```

---

## Out of Scope

- Weaviate cross-references between collections (object graph features)
- Hybrid search (vector + BM25 keyword) — evaluate post-migration if adopted
- Authentication configuration for the DBs
- MCP server migration — this evaluation produces the data to make that decision; migration is a separate phase
