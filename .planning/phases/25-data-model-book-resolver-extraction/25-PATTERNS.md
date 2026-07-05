# Phase 25: Data Model, Book Resolver & Extraction - Pattern Map

**Mapped:** 2026-07-05
**Files analyzed:** 7 new/modified files
**Analogs found:** 6 / 7 (book_resolver has a partial analog only)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `models/scripture_data.py` (new) | model | transform (in-memory records) | `models/talk_metadata.py` + `models/paragraph_data.py` (`TalkParagraphs`) | exact |
| `extractors/scripture_extraction.py` (new) | extractor | batch read → transform → group | `extractors/phase1_talk_metadata.py` | exact |
| `extractors/html_parsing_utils.py` (edit: add `clean_verse_text`) | utility | transform (text in → text out) | same file — `render_span_text` (lines 328-359) + `parse_html` (lines 26-47) | exact |
| `config/book_resolver.py` (new) | config/service (lookup) | build-time transform + query-time lookup | no direct analog; structural cues from `db/__init__.py` (module-level build) + `config/pipeline_config.py` conventions | partial |
| `config/pipeline_config.py` (edit: scripture constants) | config | — | same file, existing sections | exact |
| `tests/test_scripture_extraction.py` (new) | test | unit (live-DB + synthetic) | `tests/test_phase1.py` | exact |
| `tests/test_book_resolver.py` (new) | test | unit (synthetic) | `tests/test_html_parsing_utils.py` (pytest-class style) / `tests/test_phase1.py` (unittest style) | exact |

## Pattern Assignments

### `models/scripture_data.py` (model, transform)

**Analog:** `models/talk_metadata.py` (per-record dataclass) + `models/paragraph_data.py` (container)

**Imports + path-shim pattern** (`models/talk_metadata.py` lines 7-14) — every module in this repo uses this sys.path header:
```python
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
```

**Dataclass core pattern** (`models/talk_metadata.py` lines 26-57, abridged): plain `@dataclass` with required fields first, optional fields with defaults after, `__post_init__` validation raising `ValueError` (lines 90-127), and `to_dict()` via `asdict(self)` (lines 129-136). `ScriptureVerse` mirrors this shape with the SPEC §4 fields (`scripture_id`, `book`, `chapter`, `verse`, `text`, `reference`, `variant`, `source_flag`, `volume`, `cite_abbr`, …).

**Factory-from-row pattern** (`models/talk_metadata.py` lines 216-236):
```python
def create_talk_metadata_from_db_row(row: Dict[str, Any]) -> TalkMetadata:
    return TalkMetadata(
        talk_id=int(row["talk_id"]),
        ...
        session_id=row.get("session_id"),
        ...
    )
```
Note: for scriptures the transform (clean text, canonical book, reference derivation) belongs in the extractor per the research responsibility map — the model factory stays a thin mapper or may be omitted.

**Container pattern for `BookVerses`** (`models/paragraph_data.py` lines 97-141):
```python
@dataclass
class TalkParagraphs:
    """Container for all paragraphs from a single talk."""
    talk_id: int
    paragraphs: List[ParagraphData]
    total_paragraphs: int
    total_words: int
    extraction_success: bool
    extraction_errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.total_paragraphs != len(self.paragraphs):
            raise ValueError(...)

    def to_dict(self) -> Dict[str, Any]:
        return {"talk_id": self.talk_id,
                "paragraphs": [p.to_dict() for p in self.paragraphs], ...}
```
`BookVerses` = same shape keyed on `(book, chapter, variant)` holding `List[ScriptureVerse]`; exact fields are planner/executor discretion per CONTEXT.

---

### `extractors/scripture_extraction.py` (extractor, batch read → transform → group)

**Analog:** `extractors/phase1_talk_metadata.py`

**Imports pattern** (lines 14-27):
```python
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

sys.path.append(str(Path(__file__).parent.parent))

from db import core_db, Database
from models.talk_metadata import TalkMetadata, create_talk_metadata_from_db_row

logger = logging.getLogger(__name__)
```
For scriptures: `from db import core_db, Database`, `from models.scripture_data import ScriptureVerse, BookVerses`, `from config.book_resolver import ...`, `from extractors.html_parsing_utils import clean_verse_text`.

**Layered-module structure** (whole file): banner-commented layers in one module — `DATABASE LAYER` (query builders returning `(query, params)`, lines 35-139), `EXTRACTION LAYER` (row → dataclass transforms, lines 222-365), high-level pipeline entry point (lines 453-500), `main()` CLI (lines 543-592). Mirror this section layout.

**Query-builder pattern** (lines 35-139, abridged) — parameterized query built as a string, params list appended per optional filter, deterministic `ORDER BY`:
```python
def build_talk_metadata_query(...) -> Tuple[str, List[Any]]:
    query = """
        SELECT t.ID as talk_id, ...
        FROM talk t
        INNER JOIN speaker s ON t.SpeakerID = s.ID
        ...
        WHERE 1=1
    """
    params = []
    if talk_id is not None:
        query += " AND t.ID = ?"
        params.append(talk_id)
    query += " ORDER BY c.Year DESC, cs.Sequence ASC, ct.Sequence ASC"
    return query, params
```
Scripture query (verified in RESEARCH Pattern 1): `FROM scripture s JOIN book b ON b.ID = s.BookID LEFT JOIN book p ON p.ID = b.ParentBookID WHERE s.Flag IN ('S','J','F') AND s.Verse IS NOT NULL ORDER BY s.BookID, s.Chapter, s.Verse, s.ID`.

**Fetch wrapper with DI + logging** (lines 142-162):
```python
def fetch_all_talks(db: Database, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    query, params = build_talk_metadata_query(limit=limit)
    logger.info(f"Fetching talks from database (limit={limit or 'none'})")
    try:
        rows = db.select(query, params)
        logger.info(f"Fetched {len(rows)} talks from database")
        return rows
    except Exception as e:
        logger.error(f"Database query failed: {e}")
        raise
```

**Per-row error-collection loop** (lines 319-365) — skip-and-log per bad row, progress every N, summary at end:
```python
for idx, row in enumerate(rows, 1):
    try:
        metadata = extract_talk_metadata(row)
        metadata_list.append(metadata)
        if idx % 100 == 0:
            logger.info(f"Processed {idx}/{len(rows)} talks")
    except Exception as e:
        logger.warning(f"Skipping talk ID {talk_id} due to error: {e}")
        errors.append({"talk_id": talk_id, "error": str(e), "row": row})
```

**Caution:** unlike talks, scripture extraction should probably fail loudly on bad rows (closed 41,996-row corpus; silent skips would break the count assertion) — planner may keep the loop shape but raise instead of collecting.

---

### `extractors/html_parsing_utils.py` — add `clean_verse_text` (utility, transform)

**Analog:** same file — `render_span_text` (lines 328-359) is the cleaning idiom; `parse_html` (lines 26-47) shows the BS4 usage/logging style. Locked D-01/D-02/D-03 give the exact shape.

**NBSP + whitespace-collapse idiom to reuse** (lines 355-358):
```python
text = span.get_text()
text = text.replace(" ", " ")  # &nbsp; → regular space
text = re.sub(r" {2,}", " ", text)  # collapse runs of spaces
return text.strip()
```

**Target implementation** (from RESEARCH Pattern 2, locked decisions):
```python
import html
def clean_verse_text(raw) -> str:
    """bytes/str in -> clean str out; guaranteed no residual HTML tags."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw   # D-03
    if "<" not in text:                                             # D-02 fast path
        cleaned = html.unescape(text.strip())
    else:
        cleaned = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    cleaned = re.sub(r"\s+", " ", cleaned.replace(" ", " ")).strip()
    return cleaned
```
Module already imports `re`, `logging`, `BeautifulSoup` (lines 11-16); only `html` is a new import. Add under a new banner section matching the file's `# ====` section style. Do NOT reuse `parse_html` (returns `None` on empty — rejected in CONTEXT D-01).

---

### `config/book_resolver.py` (config/lookup, build-time + query-time)

**No direct analog** — nothing in the repo does alias-table canonicalization. Compose from:

**Module-level build-once pattern** (`db/__init__.py` lines 192-196) — build shared state at import/module level:
```python
# Global shared instances
core_db = Database(CORE_DB_PATH)
core_db.set_expected_schema(EXPECTED_CORE_TABLES, "core.52.db")
```
`book_resolver` can either follow this (module-level `_ALIASES` built lazily/on import from `core_db.select("SELECT ... FROM book")`) or accept the 99 book rows as a parameter to `canonicalize(rows)` for DB-free testing — planner discretion, but the parameterized form matches the DI style of `fetch_all_talks(db, ...)`.

**DB access** — must go through `core_db.select(...)` (parameterized, read-only); never raw `sqlite3.connect`. See `db/__init__.py` `Database.select` (lines 117-129).

**Normalization internals** (from RESEARCH Pattern 3 — pre-validated against the full 94-book inventory):
```python
_ORDINALS = {"first": "1", "second": "2", "third": "3", "fourth": "4"}

def _norm(s: str) -> str:
    s = s.lower().replace("—", " ").replace("-", " ")
    s = s.replace(".", "").replace("&", " and ")
    return re.sub(r"\s+", " ", s).strip()

def _digit_form(full_name: str) -> str:
    first, _, rest = full_name.partition(" ")
    if first.lower() in _ORDINALS and rest:
        return f"{_ORDINALS[first.lower()]} {rest}"
    return full_name
```
Plus (per RESEARCH): em-dash defensive guard `name.replace('�', '—')` in `canonicalize()` (D-04 no-op), Sections→"Doctrine and Covenants" override, prefix-stripped alias variants ("The ", "The Epistle to ", "To the ", "The Book of ") for RES-01 coverage (Pitfall 5).

**Import constraint:** stdlib + `db` only — no Weaviate/Ollama/loader imports (anti-pattern list in RESEARCH). No dependence on `server.py::_normalize_book`.

---

### `config/pipeline_config.py` (config, edit)

**Analog:** same file. Follow the banner-comment section + UPPER_SNAKE constants + dict-of-names conventions (lines 30-51):
```python
# --- Citation Extraction (Phase 3) ---
CITATION_BATCH_SIZE = 100
...
# --- Weaviate Loader (Phase 6) ---
WEAVIATE_BATCH_SIZE = 50
WEAVIATE_COLLECTION_NAMES = {
    "talks": "ConferenceTalks",
    ...
}
```
Add a new `# --- Scriptures (Phase 25+) ---` section:
```python
WEAVIATE_SCRIPTURE_COLLECTION_NAMES = {"verses": "ScriptureVerses"}
SCRIPTURE_WINDOW_RADIUS = 1
SCRIPTURE_BATCH_SIZE = 500
```
(Names per RESEARCH Integration Notes / SPEC §8.) DB paths do NOT go here (file docstring, lines 4-5).

---

### `tests/test_scripture_extraction.py` (test, live-DB + synthetic)

**Analog:** `tests/test_phase1.py`

**Header pattern** (lines 14-44): unittest-style classes run under pytest, sys.path shim, direct imports of the module under test:
```python
import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from extractors.scripture_extraction import ...
```

**Live-DB skip guard** (RESEARCH Code Example 4 — pattern sanctioned by CONTEXT; `test_phase1.py` uses in-memory SQLite, `conftest.py` uses availability skips; for a file-based DB, use skipUnless):
```python
import os
from db import CORE_DB_PATH

@unittest.skipUnless(os.path.exists(CORE_DB_PATH), "core DB not available")
class TestExtractionAgainstLiveDB(unittest.TestCase):
    def test_canonical_count_is_exactly_41996(self):
        verses = extract_scripture_verses()
        standard = [v for v in verses if v.variant == "standard"]
        self.assertEqual(len(standard), 41996)
```
Note: new tests need NO conftest changes — `tests/conftest.py` fixtures (lines 40-73) are for live Docker services this phase doesn't touch.

**Synthetic-fixture tests** for `clean_verse_text` edge cases (bytes in, `&nbsp;` → space not `\xa0`, `<br />` word-jam via `get_text(separator=" ")`, empty) — no DB needed. `tests/test_html_parsing_utils.py` must stay green after the edit.

---

### `tests/test_book_resolver.py` (test, synthetic)

**Analog:** `tests/test_html_parsing_utils.py` (pytest-class style, lines 1-35) or unittest style from `test_phase1.py` — repo mixes both under pytest; pick one and stay consistent within the file:
```python
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pytest
from config.book_resolver import canonicalize, resolve
```
Feed `canonicalize()` a hand-built book-row list (dicts matching `ID/FullName/Abbr/CiteAbbr/ParentBookID`) to stay DB-free (RESEARCH Pattern 4). Key assertions per Pitfall 1: no U+FFFD after canonicalize; book 404 works with a real U+2014; do NOT build fixtures containing U+FFFD to test "repair".

## Shared Patterns

### sys.path import shim
**Source:** every module (`models/talk_metadata.py` lines 10-14, `extractors/phase1_talk_metadata.py` lines 20-21, all tests)
**Apply to:** all 4 new .py files + both test files
```python
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
```

### Read-only DB access via `db.core_db`
**Source:** `db/__init__.py` lines 100-129, 192-194
**Apply to:** `scripture_extraction.py`, `book_resolver.py` (book-table read)
```python
from db import core_db          # Database(CORE_DB_PATH, read_only=True), 5s timeout, dict rows
rows = core_db.select(query, params)   # parameterized only
```
Optional hardening (RESEARCH Pattern 1 note): extend `EXPECTED_CORE_TABLES` in `db/__init__.py` with `"scripture": ["ID","BookID","Chapter","Verse","Flag","Text"]` and add `CiteAbbr`/`ParentBookID`/`NumChapters` to `book` (currently only `["ID","Abbr","FullName"]`, line 33).

### Module logger + log-level conventions
**Source:** `extractors/phase1_talk_metadata.py` line 27; conventions in `config/pipeline_config.py` docstring lines 7-11
**Apply to:** extractor and resolver
```python
logger = logging.getLogger(__name__)
# INFO = progress/counts, WARNING = skipped/suspicious, ERROR = halting failures
```

### Error handling
**Source:** `models/talk_metadata.py` `__post_init__` (raise `ValueError` on bad data); `extractors/phase1_talk_metadata.py` lines 303-316 (log + re-raise `KeyError/ValueError/TypeError`)
**Apply to:** model validation and extractor transforms. No custom exception hierarchy exists in this repo — plain `ValueError` is the convention (except `db.SchemaError`).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `config/book_resolver.py` (alias-table internals) | lookup service | build+query | No existing canonicalization/alias code; `server.py::_normalize_book` explicitly must NOT be extended or reused (RESEARCH anti-patterns). Use RESEARCH Pattern 3 code sketches instead. |

## Anti-Patterns (from CONTEXT/RESEARCH — do not copy)

- `parse_html()` for verse text (returns `None` on empty; wrong semantics for fragments)
- Regex tag-stripping; `ftfy`; per-verse name normalization; SQL `LIKE` on `Text` (BLOB cells return `bytes` — Pitfall 4)
- `(BookID, Chapter, Verse)` as unique key — 30,837 S/J duplicates; dedup key is `scripture.ID` (Pitfall 8)
- Modifying `server.py`, loaders, or talk extractors

## Metadata

**Analog search scope:** `models/`, `extractors/`, `config/`, `db/`, `tests/`
**Files scanned:** 8 (talk_metadata.py, paragraph_data.py, phase1_talk_metadata.py, html_parsing_utils.py, db/__init__.py, pipeline_config.py, test_phase1.py, conftest.py, test_html_parsing_utils.py)
**Pattern extraction date:** 2026-07-05
**Reminder for planner:** CLAUDE.md Project Structure Index must be updated with the 4-5 new files (maintenance rule); all commands via `pipenv run py`.
