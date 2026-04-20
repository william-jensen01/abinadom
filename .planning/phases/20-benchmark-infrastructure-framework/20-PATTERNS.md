# Phase 20: Benchmark Infrastructure & Framework - Pattern Map

**Mapped:** 2026-04-18
**Files analyzed:** 9 (8 new + 1 modified)
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `infra/docker-compose.vector-dbs.yml` | config | — | `infra/docker-compose.yml` | exact (same project, same stack style) |
| `loaders/__init__.py` | config | — | `extractors/__init__.py` (if exists; empty marker) | exact |
| `loaders/shared_transforms.py` | utility | transform | `extractors/phase6_chromadb_loader.py` lines 43–304 | exact (source of extracted code) |
| `benchmark/__init__.py` | config | — | `loaders/__init__.py` (new) / any empty `__init__.py` | exact |
| `benchmark/metrics.py` | model | — | `models/validation_report.py` | role-match (dataclass module) |
| `benchmark/queries.py` | utility | — | `config/pipeline_config.py` lines 44–51 | role-match (uppercase constant list/dict) |
| `tests/test_shared_transforms.py` | test | — | `tests/test_phase6.py` | exact (same functions being tested) |
| `tests/test_metrics.py` | test | — | `tests/test_phase5.py` | role-match (dataclass + pure-function tests) |
| `extractors/phase6_chromadb_loader.py` | utility | transform | self (modification only) | self |

---

## Pattern Assignments

### `infra/docker-compose.vector-dbs.yml` (config)

**Analog:** `infra/docker-compose.yml`

**Full style reference** (lines 1–33 of `infra/docker-compose.yml`):
```yaml
services:
  caddy:
    image: caddy:2-alpine          # pinned tag — never use :latest
    container_name: caddy
    restart: unless-stopped        # restart policy on every service
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - proxy                      # all services share one named network

networks:
  proxy:
    name: proxy                    # explicit name: field
    driver: bridge                 # explicit driver: bridge

volumes:
  caddy_data:
  caddy_config:
```

**Additional reference** (`docker-compose.yml` lines 6–12 — healthcheck block):
```yaml
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7363/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

**Key conventions to copy:**
- Pinned image tags (e.g., `caddy:2-alpine`, not `caddy:latest`)
- `restart: unless-stopped` on every service
- Named network with explicit `name:` and `driver: bridge`
- Named volumes declared at top level
- `container_name:` on every service
- Healthcheck with `["CMD", "curl", "-f", ...]` form

**Network name for this file:** `benchmark` (not `proxy` — isolated per SPEC)

---

### `loaders/__init__.py` and `benchmark/__init__.py` (config — package markers)

**Analog:** Any empty `__init__.py` in the project.

These are empty package markers. Content is a single comment line for clarity:
```python
# Package marker — intentionally empty.
```

No imports, no code.

---

### `loaders/shared_transforms.py` (utility, transform)

**Analog:** `extractors/phase6_chromadb_loader.py`

**Source block to move verbatim** — functions to extract from `extractors/phase6_chromadb_loader.py`:

Lines 43–75 (`_flatten_metadata` — becomes `flatten_metadata`, public):
```python
def _flatten_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a metadata dict for ChromaDB insertion.

    ChromaDB metadata values must be scalars (str, int, float, bool).
    Rules applied:
      - None values: removed
      - Empty lists: removed (ChromaDB rejects empty arrays)
      - List[int]: comma-joined string (e.g., [32, 33] -> "32,33")
      - List[str]: pipe-joined string (e.g., ["a", "b"] -> "a|b")
      - str / int / float / bool: kept as-is
      - Other types: str(value)
    """
    result: dict[str, Any] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, list):
            if len(value) == 0:
                continue
            if value and isinstance(value[0], int):
                result[key] = ",".join(str(v) for v in value)
            elif value and isinstance(value[0], str):
                result[key] = "|".join(value)
            else:
                result[key] = "|".join(str(v) for v in value)
        elif isinstance(value, (str, int, float, bool)):
            result[key] = value
        else:
            result[key] = str(value)
    return result
```

Lines 83–304 — all five `prepare_*` functions and `TalkBundle` type alias (move verbatim, no logic changes).

**Module header pattern** (copy from `extractors/phase6_chromadb_loader.py` lines 16–35):
```python
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).parent.parent))

from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport
```

**`sys.path.append` rule** (from `extractors/phase6_chromadb_loader.py` line 23 and `models/paragraph_data.py` line 13):
```python
sys.path.append(str(Path(__file__).parent.parent))
```
For `loaders/shared_transforms.py`, `__file__` is `<project_root>/loaders/shared_transforms.py`; `parent.parent` resolves to `<project_root>`. Identical formula works.

**`TalkBundle` type alias** (from `extractors/phase6_chromadb_loader.py` line 366):
```python
TalkBundle = tuple[TalkMetadata, TalkParagraphs, TalkCitations, TalkFootnotes, ValidationReport]
```
Keep as a type alias (not a dataclass) so Phase 21 loaders can unpack it with `for metadata, paragraphs, citations, footnotes, validation_report in bundles`.

**Anti-pattern to avoid:** Do NOT import `chromadb`, `chromadb.utils.batch_utils`, or `config.chromadb_client` in this file. The `_flatten_metadata` and `prepare_*` functions only use `dataclasses.asdict` and model imports — confirmed at `extractors/phase6_chromadb_loader.py` lines 19–34.

---

### `extractors/phase6_chromadb_loader.py` (modified — import delegation + alias)

**Change is minimal — two blocks only.**

**Block 1: Replace lines 43–304** (the private `_flatten_metadata` function, all `prepare_*` functions, and the `TalkBundle` type alias) with this import block. Place it immediately after the existing imports (after line 34, before line 38 `logger = logging.getLogger(__name__)`):
```python
from loaders.shared_transforms import (
    flatten_metadata,
    prepare_talk_record,
    prepare_paragraph_records,
    prepare_citation_records,
    prepare_footnote_records,
    prepare_talk_bundle,
    TalkBundle,
)

# Backward-compat alias: tests/test_phase6.py imports _flatten_metadata directly.
_flatten_metadata = flatten_metadata
```

**Block 2: The alias MUST come after the import block** (per RESEARCH.md Pitfall 5) — placing it before causes `NameError`.

**Do NOT touch:** `insert_collection`, `load_talk_bundles`, `generate_verification_report` — no logic changes in these functions.

---

### `benchmark/metrics.py` (model)

**Analog:** `models/validation_report.py`

**Module header pattern** (from `models/validation_report.py` lines 1–8):
```python
"""
[module docstring]
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List
```

**Dataclass pattern with default field** (from `models/paragraph_data.py` lines 16–47):
```python
@dataclass
class ParagraphData:
    """Represents a single paragraph extracted from a talk."""

    # Identity
    paragraph_id: int
    talk_id: int
    ...
    # Fields with defaults come AFTER fields without defaults
    source_type: str = "p"
    ...
    extraction_warnings: List[str] = field(default_factory=list)
```

**Dataclass without default field** (from `models/validation_report.py` lines 11–19):
```python
@dataclass
class ValidationReport:
    """Result of cross-collection validation for a single talk."""

    talk_id: int
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    stats: Dict[str, Any]
```

**Apply to `benchmark/metrics.py`:** Four dataclasses (`QueryMetrics`, `UpsertMetrics`, `ConcurrencyMetrics`, `MemoryMetrics`) follow this same `@dataclass` pattern. `QueryMetrics.failed_queries: int = 0` is the only field with a default — it must be declared last in that class (Python `@dataclass` rule enforced by `models/paragraph_data.py` precedent).

**`recall_at_k` function** — no analog in codebase; implement directly from CONTEXT.md D-spec:
```python
def recall_at_k(baseline_ids: list[str], candidate_ids: list[str], k: int) -> float:
    if k == 0:
        return 0.0
    baseline_set = set(baseline_ids[:k])
    candidate_set = set(candidate_ids[:k])
    return len(baseline_set & candidate_set) / k
```

**No `sys.path.append` needed** in `benchmark/metrics.py` — this module imports only stdlib (`dataclasses`) and no project models.

---

### `benchmark/queries.py` (utility — constant list)

**Analog:** `config/pipeline_config.py` lines 44–51

**Uppercase constant pattern** (from `config/pipeline_config.py` lines 44–51):
```python
# --- ChromaDB Loader (Phase 6) ---
CHROMADB_BATCH_SIZE = 1000
CHROMADB_COLLECTION_NAMES = {
    "talks": "conference_talks",
    "paragraphs": "conference_talk_paragraphs",
    "citations": "conference_talk_citations",
    "footnotes": "conference_talk_footnotes",
}
```

**Apply to `benchmark/queries.py`:** `CANONICAL_QUERIES` is an uppercase module-level constant — same convention as `CHROMADB_COLLECTION_NAMES`. Type annotation: `list[dict[str, Any]]`.

**Module header** — only `from typing import Any`. No `sys.path.append` needed (no project model imports).

**Required entry per CONTEXT.md D-10** (must be present verbatim):
```python
{
    "query_text": "light of the world",
    "k": 10,
    "collection": "citations",
    "filter": {"book_name": "John"},
},
```

---

### `tests/test_shared_transforms.py` (test)

**Analog:** `tests/test_phase6.py`

**Module header pattern** (from `tests/test_phase6.py` lines 1–36):
```python
"""
Unit tests for [module].
...
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest
from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
...
from loaders.shared_transforms import (
    flatten_metadata,
    prepare_talk_record,
    prepare_paragraph_records,
    prepare_citation_records,
    prepare_footnote_records,
    prepare_talk_bundle,
)
```

**Factory function pattern** (from `tests/test_phase6.py` lines 45–63):
```python
def make_talk_metadata(**kwargs) -> TalkMetadata:
    """Create a TalkMetadata with sensible defaults."""
    defaults = dict(
        talk_id=8820,
        speaker_id=100,
        conference_id=10,
        title="The Test Talk",
        speaker_name="Elder Tester",
        ...
    )
    defaults.update(kwargs)
    return TalkMetadata(**defaults)
```

**Test class organization** (from `tests/test_phase6.py` lines 181–476):
```python
class TestFlattenMetadata:
    def test_flatten_metadata_removes_none_values(self): ...
    def test_flatten_metadata_removes_empty_lists(self): ...
    def test_flatten_metadata_joins_int_list_with_comma(self): ...
    def test_flatten_metadata_joins_str_list_with_pipe(self): ...
    def test_flatten_metadata_preserves_scalars(self): ...

class TestPrepareTalkRecord:
    def test_prepare_talk_record_with_preview(self): ...

class TestPrepareTalkBundle:
    def test_prepare_talk_bundle_returns_correct_keys(self): ...
```

**Assertion style** (from `tests/test_phase6.py` lines 183–186):
```python
def test_flatten_metadata_removes_none_values(self):
    meta = {"a": 1, "b": None, "c": "hello"}
    result = _flatten_metadata(meta)
    assert "b" not in result
    assert result["a"] == 1
    assert result["c"] == "hello"
```

**Minimum tests required** (per RESEARCH.md BENCH-01):
- `flatten_metadata`: None removal, empty list removal, int-list comma join, str-list pipe join, scalar passthrough
- `rich_metadata`: None removal, list preservation (rich_metadata does NOT flatten — it preserves lists for non-ChromaDB DBs)
- `prepare_talk_bundle`: returns dict with 4 required keys, valid bundle produces non-empty lists

**Note:** `test_shared_transforms.py` imports from `loaders.shared_transforms`, NOT from `extractors.phase6_chromadb_loader`. The function name is `flatten_metadata` (public), not `_flatten_metadata` (private).

---

### `tests/test_metrics.py` (test)

**Analog:** `tests/test_phase5.py`

**Module header pattern** (from `tests/test_phase5.py` lines 1–25):
```python
"""
Unit tests for [module].
"""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from benchmark.metrics import (
    QueryMetrics,
    UpsertMetrics,
    ConcurrencyMetrics,
    MemoryMetrics,
    recall_at_k,
)
from benchmark.queries import CANONICAL_QUERIES
```

**Dataclass instantiation test pattern** (from `tests/test_phase5.py` lines 166–173):
```python
class TestValidationReport:
    def test_repr(self):
        report = ValidationReport(
            talk_id=1, is_valid=True, errors=[], warnings=[], stats={}
        )
        assert "talk_id=1" in repr(report)
        assert "valid=True" in repr(report)
```

**Apply to `benchmark/metrics.py` tests:**
```python
class TestQueryMetrics:
    def test_query_metrics_instantiation(self):
        m = QueryMetrics(p50_ms=10.0, p95_ms=20.0, p99_ms=30.0,
                         mean_ms=15.0, min_ms=5.0, max_ms=35.0,
                         query_count=100)
        assert m.failed_queries == 0        # default value
        assert m.query_count == 100

class TestRecallAtK:
    def test_recall_at_k_basic(self):
        # SPEC acceptance criterion: recall_at_k(["a","b","c"], ["a","c","d"], k=3) -> 2/3
        result = recall_at_k(["a", "b", "c"], ["a", "c", "d"], k=3)
        assert abs(result - 2/3) < 1e-9

    def test_recall_at_k_zero_k(self):
        assert recall_at_k(["a"], ["a"], k=0) == 0.0

class TestCanonicalQueries:
    def test_canonical_queries_minimum_count(self):
        assert len(CANONICAL_QUERIES) >= 7

    def test_canonical_queries_all_have_required_keys(self):
        for q in CANONICAL_QUERIES:
            assert "query_text" in q
            assert "k" in q
            assert "collection" in q
            assert "filter" in q
            assert q["k"] == 10

    def test_canonical_queries_has_john_filter(self):
        john_queries = [q for q in CANONICAL_QUERIES
                        if q.get("filter") and q["filter"].get("book_name") == "John"]
        assert len(john_queries) >= 1
```

---

## Shared Patterns

### sys.path.append Import Pattern
**Source:** `extractors/phase6_chromadb_loader.py` line 23; `models/paragraph_data.py` line 13; `tests/test_phase6.py` line 14
**Apply to:** Every file in `loaders/`, `tests/test_shared_transforms.py`, `tests/test_metrics.py`
```python
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
```
`__file__` for any file one directory deep from project root: `parent.parent` = project root. This is the canonical path-resolution pattern for the entire project.

### Dataclass Declaration Pattern
**Source:** `models/validation_report.py` lines 11–19; `models/paragraph_data.py` lines 16–47
**Apply to:** `benchmark/metrics.py` (all four metric dataclasses)
```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SomeMetrics:
    required_field: float        # required fields first (no default)
    another_required: int
    optional_field: int = 0      # defaulted fields last (Python @dataclass rule)
```

### Uppercase Module-Level Constants
**Source:** `config/pipeline_config.py` lines 44–51
**Apply to:** `benchmark/queries.py` (`CANONICAL_QUERIES`)
```python
SOME_CONSTANT = {
    "key": "value",
}
```
No encapsulation in classes or functions — bare module-level names in SCREAMING_SNAKE_CASE.

### Test Factory Function Pattern
**Source:** `tests/test_phase6.py` lines 45–63; `tests/test_phase5.py` lines 35–46
**Apply to:** `tests/test_shared_transforms.py`
```python
def make_talk_metadata(**kwargs) -> TalkMetadata:
    """Create a TalkMetadata with sensible defaults."""
    defaults = dict(talk_id=8820, ...)
    defaults.update(kwargs)
    return TalkMetadata(**defaults)
```
Factory functions (not pytest fixtures) for model objects — use `**kwargs` merge so individual tests can override specific fields.

### Compose File: restart + healthcheck
**Source:** `docker-compose.yml` lines 8–14; `infra/docker-compose.yml` lines 3–4
**Apply to:** `infra/docker-compose.vector-dbs.yml` (all three services)
```yaml
restart: unless-stopped
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:PORT/ENDPOINT"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

## No Analog Found

No files in this phase lack a codebase analog. All patterns have direct matches.

---

## Metadata

**Analog search scope:** `extractors/`, `tests/`, `models/`, `config/`, `infra/`, project root
**Files read:** `extractors/phase6_chromadb_loader.py`, `tests/test_phase6.py`, `tests/test_phase5.py`, `models/validation_report.py`, `models/paragraph_data.py`, `config/pipeline_config.py`, `infra/docker-compose.yml`, `docker-compose.yml`
**Pattern extraction date:** 2026-04-18
