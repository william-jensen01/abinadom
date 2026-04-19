# Phase 20: Benchmark Infrastructure & Framework - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Foundation layer for the v4.0 vector DB benchmark: shared transform functions,
metric dataclasses, canonical query set, and Docker Compose stack for all three
vector DBs. All outputs are consumed by Phases 21–23; no data is loaded and no
benchmark is run in this phase.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**7 requirements are locked.** See `20-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `20-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `infra/docker-compose.vector-dbs.yml` — ChromaDB, Weaviate, Qdrant services with ports published to localhost
- `loaders/__init__.py` — package marker only
- `loaders/shared_transforms.py` — `flatten_metadata`, `rich_metadata`, `prepare_*`, `TalkBundle`
- `benchmark/__init__.py` — package marker only
- `benchmark/metrics.py` — four metric dataclasses + `recall_at_k`
- `benchmark/queries.py` — `CANONICAL_QUERIES` list
- `tests/test_shared_transforms.py` — unit tests for transform functions
- `tests/test_metrics.py` — unit tests for metric dataclasses and `recall_at_k`

**Out of scope (from SPEC.md):**
- `loaders/chromadb_loader.py`, `loaders/weaviate_loader.py`, `loaders/qdrant_loader.py` — Phase 21
- `benchmark/runner.py` — Phase 22
- Loading any actual talk data into the DBs — Phase 21+
- Running queries against the DBs — Phase 22+
- Ollama container in Docker Compose — Ollama runs on the host; `OLLAMA_URL` is an env var
- Modifying `extractors/phase6_chromadb_loader.py` behavior — production loader is not touched
- Authentication or TLS config for the benchmark DBs — local dev only, anonymous access

</spec_lock>

<decisions>
## Implementation Decisions

### prepare_* Extraction Strategy

- **D-01:** Functions **move** to `loaders/shared_transforms.py` (not copied, not re-exported from phase6). `shared_transforms.py` contains the canonical implementations with no DB-client dependencies.
- **D-02:** `extractors/phase6_chromadb_loader.py` gets a thin import block replacing its private implementations:
  ```python
  from loaders.shared_transforms import (
      flatten_metadata,
      prepare_talk_record,
      prepare_paragraph_records,
      prepare_citation_records,
      prepare_footnote_records,
      prepare_talk_bundle,
  )
  ```
  This is the minimal change needed — behavior for all callers is unchanged.
- **D-03:** `phase6_chromadb_loader.py` keeps a backward-compat alias `_flatten_metadata = flatten_metadata` so `tests/test_phase6.py` (which imports `_flatten_metadata` directly) continues to pass without modification. This satisfies the SPEC acceptance criterion: `pipenv run py -m pytest tests/test_phase6.py` exits 0 with no regression.

### Metric Dataclass Field Design

Decided field schemas (Phase 22 runner will populate these):

- **D-04: `QueryMetrics`** — full latency profile:
  ```python
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

- **D-05: `UpsertMetrics`** — minimal standard fields:
  ```python
  @dataclass
  class UpsertMetrics:
      total_records: int
      elapsed_seconds: float
      records_per_second: float
  ```

- **D-06: `ConcurrencyMetrics`** — minimal standard fields:
  ```python
  @dataclass
  class ConcurrencyMetrics:
      workers: int
      total_queries: int
      elapsed_seconds: float
      throughput_qps: float
  ```

- **D-07: `MemoryMetrics`** — minimal standard fields:
  ```python
  @dataclass
  class MemoryMetrics:
      baseline_mb: float
      peak_mb: float
      delta_mb: float
  ```

### Canonical Query Set Design

- **D-08:** `k=10` for all queries as the default retrieval depth. Matches the MCP server's typical usage and aligns with `recall@k10` as the primary evaluation metric in REQUIREMENTS.md.
- **D-09:** Paragraph queries cover all 4 doctrinal themes: (1) doctrinal core (faith, atonement, resurrection, eternal family, repentance), (2) scripture application (how prophets applied scriptures in teaching), (3) historical/prophetic events (Restoration, pioneer sacrifice, Joseph Smith teachings), (4) practical living (family prayer, Sabbath, temple, missionary work). Distribute ≥5 paragraph queries across these themes.
- **D-10:** Citation queries: ≥2 entries in the `citations` collection. At least one citation query uses `{"book_name": "John"}` as the non-None filter (e.g., `query_text="light of the world"` filtered to citations from the Gospel of John).
- **D-11:** Claude's discretion on exact query texts within the approved themes — choose queries that represent realistic user searches against the GC corpus.

### Claude's Discretion

- Exact `CANONICAL_QUERIES` text strings — user approved themes and filter structure; Claude selects the specific query texts
- Docker image tags for Weaviate and Qdrant (user did not select this area — researcher should pick stable recent versions)
- `TalkBundle` type definition (if needed as a named type in shared_transforms)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and Specification
- `.planning/phases/20-benchmark-infrastructure-framework/20-SPEC.md` — Locked requirements — MUST read before planning (7 requirements, boundaries, acceptance criteria, constraints)
- `.planning/REQUIREMENTS.md` — v4.0 requirement IDs: BENCH-01 (Phase 20 transforms), BENCH-05 (metrics), BENCH-06 (queries), EVAL-01 (Docker Compose)

### Existing Code to Extract From
- `extractors/phase6_chromadb_loader.py` — Source of all `prepare_*` functions and `_flatten_metadata`; move these to shared_transforms.py per D-01

### Existing Infrastructure Reference
- `infra/docker-compose.yml` — Caddy + cloudflared compose; use as style reference for the new vector-dbs compose file (network naming, restart policies)
- `docker-compose.yml` — MCP server compose; shows how the project uses bind mounts and env_file

### Existing Tests Reference
- `tests/test_phase6.py` — Must continue to pass after extraction (SPEC acceptance criterion); imports `_flatten_metadata` — covered by backward-compat alias (D-03)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_flatten_metadata()` in `extractors/phase6_chromadb_loader.py`: Move to `shared_transforms.py` as `flatten_metadata()` (public). Logic is ~25 lines — already well-documented with clear rules.
- `prepare_talk_record`, `prepare_paragraph_records`, `prepare_citation_records`, `prepare_footnote_records`, `prepare_talk_bundle` in `extractors/phase6_chromadb_loader.py`: All move to `shared_transforms.py`. These use `asdict()` from `dataclasses` and model imports — no chromadb dependency in the functions themselves (only in the insertion functions later in the file).
- `config/chromadb_client.py`: Shows the existing ChromaDB connection pattern (env vars `CHROMADB_HOST`/`CHROMADB_PORT`). The benchmark Docker Compose should publish ChromaDB on port 8000 (same default) so existing `CHROMADB_HOST=localhost CHROMADB_PORT=8000` works for the benchmark instance.

### Established Patterns
- **Dataclasses everywhere**: All data models use `@dataclass` with type hints. `benchmark/metrics.py` should follow the same pattern.
- **`from dataclasses import asdict`**: Used in phase6's `prepare_*` functions. `shared_transforms.py` will use the same stdlib import.
- **`sys.path.append(str(Path(__file__).parent.parent))`**: Standard project import pattern — new modules in `loaders/` and `benchmark/` will need this or equivalent.
- **Uppercase constants**: `CANONICAL_QUERIES` follows the existing `CHROMADB_COLLECTION_NAMES`, `PARAGRAPH_CONFIG` pattern.
- **Docker Compose style**: `infra/docker-compose.yml` uses `image: caddy:2-alpine` pinned tags, `restart: unless-stopped`, named networks. Follow the same style.

### Integration Points
- `loaders/shared_transforms.py` will be imported by `extractors/phase6_chromadb_loader.py` (after extraction) AND by the Phase 21 loaders (`loaders/chromadb_loader.py`, `loaders/weaviate_loader.py`, `loaders/qdrant_loader.py`)
- `benchmark/metrics.py` will be imported by `benchmark/runner.py` (Phase 22)
- `benchmark/queries.py` `CANONICAL_QUERIES` will be consumed by `benchmark/runner.py` (Phase 22)
- `infra/docker-compose.vector-dbs.yml` is standalone (isolated `benchmark` Docker network); does NOT join the `proxy` network used by Caddy/cloudflared

</code_context>

<specifics>
## Specific Ideas

- Benchmark Docker network name: `benchmark` (isolated from production `proxy` network per SPEC constraint)
- Published ports per SPEC: ChromaDB → 8000, Weaviate → 8080 + 50051, Qdrant → 6333 + 6334
- At least one `CANONICAL_QUERIES` entry: `{"query_text": "light of the world", "k": 10, "collection": "citations", "filter": {"book_name": "John"}}`
- `recall_at_k` example from SPEC: `recall_at_k(["a","b","c"], ["a","c","d"], k=3)` → 2/3 ≈ 0.667 (2 overlapping IDs / k=3)

</specifics>

<deferred>
## Deferred Ideas

- Docker image version selection for Weaviate and Qdrant — researcher should determine stable recent versions (not selected for discussion by user)
- `TalkBundle` named type design — planner can decide whether this is a dataclass, TypedDict, or just a type alias based on Phase 21 needs

</deferred>

---

*Phase: 20-benchmark-infrastructure-framework*
*Context gathered: 2026-04-18*
