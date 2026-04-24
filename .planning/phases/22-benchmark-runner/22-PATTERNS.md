# Phase 22: Benchmark Runner - Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 3 (benchmark/runner.py, benchmark/metrics.py, Pipfile)
**Analogs found:** 3 / 3

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `benchmark/runner.py` | orchestrator / CLI | batch + request-response | `scripts/run_pipeline.py` + `loaders/chromadb_loader.py` | role-match (CLI shell) + exact (class body) |
| `benchmark/metrics.py` | model (dataclass) | transform | `benchmark/metrics.py` (existing dataclasses) | exact — adding a new dataclass to the file |
| `Pipfile` | config | n/a | `Pipfile` (existing) | exact — inserting one line into `[packages]` |

---

## Pattern Assignments

### `benchmark/runner.py` (orchestrator, batch + request-response)

Three analogs contribute distinct patterns. Use all three.

---

#### Analog 1 — CLI shell and argparse: `scripts/run_pipeline.py`

**sys.path bootstrap + imports pattern** (lines 1-46):
```python
import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import content_db, core_db
from config.schemas import PARAGRAPH_CONFIG
from extractors.pipeline import process_talk_pipeline
from extractors.phase3_citation_extraction import fetch_all_books
from extractors.phase5_validation import validate_talk

logger = logging.getLogger(__name__)
```

**_get_all_gc_talk_ids() pattern** (lines 51-61):
```python
def _get_all_gc_talk_ids() -> List[int]:
    """
    Return all General Conference talk IDs from the database.

    Uses INNER JOIN conference_talk to get only GC talks (approx. 5,838),
    not all talks in the database (approx. 7,659).
    """
    rows = core_db.select(
        "SELECT t.ID FROM talk t INNER JOIN conference_talk ct ON ct.TalkID = t.ID ORDER BY t.ID"
    )
    return [row["ID"] for row in rows]
```

**Per-talk pipeline call pattern** (lines 126-163 — the talk loop body):
```python
try:
    # Phases 1-4: extraction
    result = process_talk_pipeline(
        content_db, core_db, talk_id, book_cache, PARAGRAPH_CONFIG
    )

    if not result.success:
        raise RuntimeError("; ".join(result.errors))

    # Phase 5: validation
    validation = validate_talk(
        result.metadata,
        result.paragraphs,
        result.citations,
        result.footnotes,
        db=core_db,
    )

    if not validation.is_valid:
        logger.warning("talk_id=%d validation failed", talk_id)
        continue

    bundle: TalkBundle = (
        result.metadata,
        result.paragraphs,
        result.citations,
        result.footnotes,
        validation,
    )
```

**argparse pattern** (lines 82-90):
```python
parser = argparse.ArgumentParser(
    description="Run the full LDS pipeline over all General Conference talks."
)
parser.add_argument(
    "--force",
    action="store_true",
    help="Re-process already-loaded talks (skip the ChromaDB existence check)",
)
args = parser.parse_args()
```

**logging basicConfig pattern** (lines 194-198):
```python
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    main()
```

**JSON write pattern** (lines 76-79):
```python
with open(FAILED_TALKS_PATH, "w", encoding="utf-8") as f:
    json.dump(failed_talks, f, indent=2, ensure_ascii=False)
```

---

#### Analog 2 — Loader class body pattern: `loaders/chromadb_loader.py`

**sys.path + logging pattern** (lines 14-26):
```python
import logging
import sys
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from loaders import BaseLoader
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle

logger = logging.getLogger(__name__)
```

**Class constructor + client instantiation pattern** (lines 35-55):
```python
class ChromaDBLoader(BaseLoader):
    def __init__(
        self,
        host: str,
        port: int,
        embed_fn: Callable[[str], list[float]],
        batch_size: int = 100,
    ) -> None:
        super().__init__(host, port, embed_fn, batch_size)
        self._client = chromadb.HttpClient(host=host, port=port)
```

**Per-batch try/except + WARNING log pattern** (lines 78-90):
```python
try:
    col.upsert(
        ids=ids,
        documents=docs,
        metadatas=metas,
        embeddings=vecs,
    )
except Exception as e:
    logger.warning(
        "ChromaDB batch failed for collection %s: %s",
        coll_name,
        e,
    )
```

---

#### Analog 3 — close() / context manager pattern: `loaders/weaviate_loader.py`

**close() + context manager pattern** (lines 247-256):
```python
def __enter__(self):
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()
    return False

def close(self) -> None:
    """Close the Weaviate client and release the gRPC connection (Pitfall 1)."""
    self._client.close()
```

WeaviateLoader requires `close()` after benchmarking; QdrantLoader does not. The runner must call `loader.close()` in a `finally` block (or use WeaviateLoader as a context manager) for every DB that has a non-no-op `close()`.

---

#### Analog 4 — asdict() serialization pattern: `loaders/shared_transforms.py`

**Import and usage** (lines 11, 129):
```python
from dataclasses import asdict

# usage — converts dataclass to plain dict for JSON
raw_meta = asdict(metadata)
```

The runner uses `dataclasses.asdict(metric_obj)` for every metric dataclass before building the report dict, and `json.dump(report, f, indent=2)` to write the file.

---

### `benchmark/metrics.py` — add `ScalabilityCurveEntry` dataclass

**Analog:** `benchmark/metrics.py` (existing file, lines 1-72)

**Existing dataclass pattern to copy** (lines 12-51):
```python
from dataclasses import dataclass


@dataclass
class UpsertMetrics:
    """Measures bulk insert performance."""
    total_records: int
    elapsed_seconds: float
    records_per_second: float


@dataclass
class ConcurrencyMetrics:
    """Measures throughput under concurrent query load."""
    workers: int
    total_queries: int
    elapsed_seconds: float
    throughput_qps: float
```

**New dataclass to add** — place after the existing four dataclasses, before `recall_at_k()`:
```python
@dataclass
class ScalabilityCurveEntry:
    """Per-worker-level result for the scalability curve benchmark (SPEC Req 7)."""
    workers: int
    throughput_qps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
```

Fields exactly match `scalability_curve` array entry schema from SPEC Req 7 and D-09.

---

### `Pipfile` — add psutil dependency

**Analog:** `Pipfile` (existing file, lines 1-24)

**Current `[packages]` block** (lines 6-16):
```toml
[packages]
requests = ">=2.31.0"
beautifulsoup4 = ">=4.12.0"
requests-cache = "*"
html5lib = "*"
chromadb = "*"
ollama = "*"
weaviate-client = "==4.20.5"
qdrant-client = "==1.17.1"
tqdm = "*"
fastmcp = "*"
```

**Pattern for new dependency** — add one line using the `"*"` wildcard (matching `tqdm`, `fastmcp`, etc. which have no version pin):
```toml
psutil = "*"
```

Insert immediately after `fastmcp = "*"` (or at end of `[packages]` block). No version pin needed — psutil has a stable API and no known conflicts with the stack.

---

## Shared Patterns

### sys.path bootstrap
**Source:** All files in `loaders/` (lines 14-19 in `chromadb_loader.py`) and `scripts/run_pipeline.py` (line 29)
**Apply to:** `benchmark/runner.py` — it lives in `benchmark/` (one level below project root)
```python
sys.path.insert(0, str(Path(__file__).parent.parent))
```
Note: loaders use `sys.path.append`; `scripts/run_pipeline.py` uses `sys.path.insert(0, ...)`. Either works; `insert(0, ...)` is preferred to avoid shadowing installed packages.

### Logger instantiation
**Source:** Every loader and script file
**Apply to:** `benchmark/runner.py`
```python
logger = logging.getLogger(__name__)
```

### Per-record WARNING + continue pattern
**Source:** `loaders/chromadb_loader.py` (lines 85-90), `loaders/qdrant_loader.py` (lines 127-128)
**Apply to:** `benchmark/runner.py` talk-loading loop and any query that may fail
```python
except Exception as e:
    logger.warning("ChromaDB batch failed for collection %s: %s", coll_name, e)
```

### dataclasses.asdict() serialization
**Source:** `loaders/shared_transforms.py` (line 11, used throughout)
**Apply to:** `benchmark/runner.py` report assembly — all metric dataclasses serialized via `asdict()` before `json.dump()`
```python
from dataclasses import asdict
# ...
"upsert": asdict(upsert_metrics),
"memory_upsert": asdict(memory_upsert_metrics),
```

### Path.mkdir(parents=True, exist_ok=True)
**Source:** `scripts/run_pipeline.py` (line 76)
**Apply to:** `benchmark/runner.py` output directory creation
```python
Path(args.output).mkdir(parents=True, exist_ok=True)
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `benchmark/runner.py` — memory polling thread | utility (internal) | event-driven | No existing background thread pattern in codebase; use `threading.Thread(target=_poll_memory, args=(samples, stop_event), daemon=True)` per D-06 in CONTEXT.md |
| `benchmark/runner.py` — ThreadPoolExecutor concurrency harness | utility (internal) | batch | No existing concurrent query pattern; use `concurrent.futures.ThreadPoolExecutor(max_workers=N)` with `submit()` + `as_completed()` per SPEC Req 7 |
| `benchmark/runner.py` — Jaccard determinism scoring | utility (internal) | transform | No existing set-similarity pattern; implement as `len(set.intersection(*all_run_id_sets)) / len(set.union(*all_run_id_sets))` per SPEC Req 11 description |

---

## Metadata

**Analog search scope:** `benchmark/`, `loaders/`, `scripts/`, `config/`, `loaders/shared_transforms.py`
**Files scanned:** 9 source files read in full
**Pattern extraction date:** 2026-04-24
