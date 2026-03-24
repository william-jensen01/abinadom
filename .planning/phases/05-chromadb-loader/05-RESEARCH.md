# Phase 5: ChromaDB Loader - Research

**Researched:** 2026-03-24
**Domain:** ChromaDB document storage, data transformation, batch insertion
**Confidence:** HIGH

## Summary

Phase 5 (project numbering "Phase 6" in PIPELINE_SPEC.md) transforms validated pipeline output bundles into four ChromaDB collections. The core work is: (1) transforming dataclass instances into ChromaDB's `documents/metadatas/ids` format with proper flattening, (2) handling annotation paragraph exclusion/folding, (3) batch inserting in dependency order, and (4) generating a post-insertion verification report.

The existing codebase already has `to_chromadb_format()` methods on all four data models (`TalkMetadata`, `ParagraphData`, `CitationData`, `FootnoteData`). However, these methods do NOT match the user's locked decisions (D-01 through D-06) -- the Phase 6 loader must implement its own transformation logic rather than delegating to these model methods. Additionally, a critical gap exists: `ParagraphData` does not have a `source_type` field, so annotation paragraphs cannot be identified from the dataclass alone. This must be addressed.

**Primary recommendation:** Build `extractors/phase6_chromadb_loader.py` with standalone transformation functions (not using the existing `to_chromadb_format()` methods), add `source_type` field to `ParagraphData`, install `chromadb` into the Pipfile, and use `chromadb.utils.batch_utils.create_batches` for batch chunking.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `conference_talks` -- store `f"{title}\n\n{talk_preview}"` when `talk_preview` is present; fall back to `title` alone when absent.
- **D-02:** `conference_talk_paragraphs` -- store `paragraph.text` (clean text, HTML stripped).
- **D-03:** `conference_talk_citations` -- store `citation.context_window` text.
- **D-04:** `conference_talk_footnotes` -- store `footnote.context_window` text.
- **D-05:** Include all non-None fields from each dataclass as metadata. No manual curation. Planner determines exact per-collection field lists by reading the model dataclasses.
- **D-06:** Flatten any nested structures (lists -> pipe-joined strings or JSON strings). ChromaDB metadata values must be scalars.
- **D-07:** Annotation paragraphs (`source_type="annotation"`) are excluded from `conference_talk_paragraphs`.
- **D-08:** Annotation text folded into `conference_talks` metadata as `annotations` field -- pipe-joined string.
- **D-09:** Citations from annotation paragraphs included in `conference_talk_citations` normally.
- **D-10:** If `validation_report.is_valid is False`, skip all 4 collection inserts for that talk. Log at WARNING.
- **D-11:** Skipped talks included in post-insertion verification summary.
- **D-12:** Use `chromadb.PersistentClient(path=CHROMADB_PATH)` with path from `config/pipeline_config.py`.
- **D-13:** Tests use `tmp_path` pytest fixture or `chromadb.EphemeralClient()`.
- **D-14:** Use `chromadb.utils.embedding_functions.OllamaEmbeddingFunction` with `model_name="nomic-embed-text"` and `url="http://localhost:11434/api/embeddings"`. Pass to `get_or_create_collection()` for all 4 collections. Ollama must be running locally with `nomic-embed-text` pulled.

### Claude's Discretion
- Verification report format (markdown or structured text to stdout/log)
- Batch size default value (spec suggests 5000; tune as needed)
- Exact retry logic for failed ChromaDB batches

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOAD-01 | Phase 5 output transformed into `documents`, `metadatas`, `ids` format for each of the 4 ChromaDB collections | Transformation functions per collection; field inventory documented below; D-01 through D-06 define document text and metadata rules |
| LOAD-02 | Annotation paragraphs excluded from `conference_talk_paragraphs`; text folded into `conference_talks` metadata | Requires `source_type` field on ParagraphData (currently missing -- must be added); D-07, D-08 |
| LOAD-03 | Citations from annotation paragraphs still included in `conference_talk_citations` normally | No special handling needed -- citations reference `paragraph_id` which remains valid; D-09 |
| LOAD-04 | All 4 collections inserted in dependency order with configurable batch chunking | Use `chromadb.utils.batch_utils.create_batches`; insert order: talks -> paragraphs -> citations/footnotes |
| LOAD-05 | Insertion progress logged per batch for large runs | Per-batch logging with collection name, batch N/M, record count |
| LOAD-06 | Post-insertion verification report: record counts, sample document retrievals, foreign key spot checks | Report dataclass or dict; retrieve documents post-insert; spot-check talk_id/paragraph_id cross-references |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **pipenv**: All commands use `pipenv run py`, install with `pipenv install`
- **Simplicity First**: Minimal code, minimal impact
- **No Laziness**: Root causes, no temporary fixes
- **Verification Before Done**: Prove it works with tests
- **Plan First**: Detailed specs upfront
- **Project Structure Index**: Must update CLAUDE.md index when adding files to `extractors/`, `config/`, `tests/`

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| chromadb | 1.5.5 | Document and metadata storage | The target database for this entire pipeline; latest stable release 2026-03-10 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 | Test framework | Already installed as dev dependency |
| chromadb.utils.batch_utils | (bundled) | `create_batches()` utility for splitting large inserts | When inserting more than `max_batch_size` records |
| chromadb.utils.embedding_functions | (bundled) | `OllamaEmbeddingFunction` for nomic-embed-text | Pass to `get_or_create_collection()` — D-14 |
| Ollama (local) | — | Runs `nomic-embed-text` embedding model locally | Must be running at `http://localhost:11434` before insertion |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `create_batches()` | Manual list slicing | `create_batches` respects `client.max_batch_size` (SQLite parameter limits); manual slicing risks hitting limits |

**Installation:**
```bash
pipenv install chromadb
```

**Version verification:** chromadb 1.5.5 confirmed on PyPI as of 2026-03-10. Python 3.14 compatibility needs verification at install time (chromadb requires >=3.9, wheels built for cp39-abi3).

## Architecture Patterns

### Recommended Project Structure
```
extractors/
    phase6_chromadb_loader.py    # NEW: transformer + inserter + verifier
config/
    pipeline_config.py           # ADD: CHROMADB_PATH, CHROMADB_BATCH_SIZE
tests/
    test_phase6.py               # NEW: unit + integration tests
```

### Pattern 1: Standalone Transformation Functions (not model methods)

**What:** Build `prepare_talks()`, `prepare_paragraphs()`, `prepare_citations()`, `prepare_footnotes()` functions in the loader module that accept dataclass instances and return `(documents, metadatas, ids)` tuples.

**When to use:** Always. The existing `to_chromadb_format()` methods on the models do NOT match the locked decisions:
- `TalkMetadata._create_document_summary()` builds a multi-field summary; D-01 says `f"{title}\n\n{talk_preview}"` with title-only fallback
- `ParagraphData.to_chromadb_format()` removes text from metadata; D-05 says include all non-None fields
- `CitationData.to_chromadb_format()` removes `verse_list` and adds `verse_list_str`; D-05/D-06 handle this differently

**Example:**
```python
def prepare_talk_record(
    metadata: TalkMetadata,
    annotation_texts: list[str],
) -> tuple[str, dict[str, Any], str]:
    """Transform a single TalkMetadata into ChromaDB format per D-01, D-05, D-06, D-08."""
    # Document text (D-01)
    if metadata.talk_preview:
        document = f"{metadata.title}\n\n{metadata.talk_preview}"
    else:
        document = metadata.title

    # Metadata: all non-None fields (D-05)
    raw = asdict(metadata)
    meta = {k: v for k, v in raw.items() if v is not None}

    # Flatten lists/nested (D-06)
    meta = _flatten_metadata(meta)

    # Annotation text (D-08)
    if annotation_texts:
        meta["annotations"] = "|".join(annotation_texts)

    # ID
    doc_id = f"talk_{metadata.talk_id}"

    return document, meta, doc_id
```

### Pattern 2: Metadata Flattening

**What:** ChromaDB metadata values must be strings, integers, floats, booleans, or arrays of same type. No None, no nested dicts, no mixed-type arrays.

**When to use:** Every metadata dict before insertion.

**Flattening rules (from D-06 and ChromaDB constraints):**
- `None` values: remove key entirely (D-05: "all non-None fields")
- `list[str]` (e.g., `extraction_warnings`): pipe-join to string
- `list[int]` (e.g., `verse_list`): pipe-join as comma-separated string
- `datetime` strings: keep as-is (already strings)
- Nested dicts: should not occur in these models (verify)

### Pattern 3: Dependency-Ordered Insertion

**What:** Insert collections in order: talks -> paragraphs -> citations + footnotes (citations and footnotes can be parallel since they don't depend on each other, only on talks and paragraphs).

**When to use:** Always. While ChromaDB doesn't enforce foreign keys, the PIPELINE_SPEC requires this order for logical consistency and verification.

### Anti-Patterns to Avoid
- **Using existing `to_chromadb_format()` methods:** They don't match locked decisions D-01 through D-06. Build standalone functions.
- **Storing None in metadata:** ChromaDB silently drops None values or errors. Filter them out explicitly.
- **Inserting without batching:** A full run has ~7,659 talks, ~150K+ paragraphs, ~100K+ citations. Without batching, a single `add()` call will hit SQLite parameter limits.
- **Hardcoding ChromaDB path in the module:** Use `config/pipeline_config.py` constant per D-12.

## Critical Gap: source_type Missing from ParagraphData

**What:** Phase 2 extracts `source_type` (values: "p", "stanza", "list", "bare", "table", "annotation") from HTML but does NOT preserve it in the `ParagraphData` dataclass. The field is used locally in `process_talk_paragraphs()` then discarded.

**Impact:** Phase 6 cannot identify annotation paragraphs (D-07, D-08, LOAD-02) without this field.

**Required fix:** Add `source_type: str = "p"` field to the `ParagraphData` dataclass and set it during construction in `process_talk_paragraphs()`. This is a prerequisite for Plan 1.

**Confidence:** HIGH -- verified by reading both `models/paragraph_data.py` (no `source_type` field) and `extractors/phase2_paragraph_extraction.py` lines 1074-1111 (field extracted from dict but not passed to `ParagraphData` constructor).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Batch size calculation | Manual `max_batch_size` detection | `chromadb.utils.batch_utils.create_batches(api=client, ...)` | Handles SQLite parameter limits per-platform automatically |
| Metadata type coercion | Manual type-checking per field | Simple `_flatten_metadata()` helper that walks dict once | Predictable, testable, covers all model fields |

## Common Pitfalls

### Pitfall 1: ChromaDB Metadata Type Errors
**What goes wrong:** ChromaDB raises on metadata values that are None, nested dicts, or mixed-type arrays.
**Why it happens:** `dataclasses.asdict()` preserves None values and list fields verbatim.
**How to avoid:** Filter None values and flatten all lists before insertion. Test with real dataclass instances.
**Warning signs:** `ValueError` or silent data loss on `collection.add()`.

### Pitfall 2: Duplicate IDs on Re-run
**What goes wrong:** `collection.add()` silently ignores duplicate IDs (does not update). Data from a previous run persists.
**Why it happens:** ChromaDB `add()` skips existing IDs without error.
**How to avoid:** Use `collection.upsert()` instead of `add()` for idempotent behavior. Or delete collection before re-insert if doing a full rebuild.
**Warning signs:** Record counts match but data is stale.

### Pitfall 3: SQLite Parameter Limit on Large Batches
**What goes wrong:** `sqlite3.OperationalError: too many SQL variables` when adding too many records at once.
**Why it happens:** ChromaDB uses SQLite internally; each record generates multiple SQL parameters.
**How to avoid:** Use `create_batches()` utility or manually chunk to ~5000 records.
**Warning signs:** Crashes mid-insertion on large runs.

### Pitfall 4: extraction_warnings List Not Flattened
**What goes wrong:** `ParagraphData.extraction_warnings` is `List[str]`; `CitationData.extraction_warnings` same. If passed as-is to ChromaDB metadata, it's a list of strings (valid in newer ChromaDB as array), but empty lists `[]` are NOT allowed.
**Why it happens:** `asdict()` preserves empty lists.
**How to avoid:** Convert to pipe-joined string, or omit if empty (consistent with D-05 non-None rule -- empty list is "present but empty", decide on convention).
**Warning signs:** `ValueError: empty arrays are not allowed` from ChromaDB.

### Pitfall 5: Annotation Paragraph Identification
**What goes wrong:** Cannot identify which paragraphs are annotations because `source_type` is not in `ParagraphData`.
**Why it happens:** Phase 2 extraction drops `source_type` when constructing the dataclass.
**How to avoid:** Add `source_type` field to `ParagraphData` before implementing Phase 6 loader.
**Warning signs:** All paragraphs treated equally; annotations stored in `conference_talk_paragraphs`.

## Code Examples

### Per-Collection Field Inventory (from model dataclasses)

**conference_talks** (from `TalkMetadata`):
- Document: `f"{title}\n\n{talk_preview}"` or `title` (D-01)
- ID: `f"talk_{talk_id}"`
- Metadata fields (all non-None): `talk_id`, `speaker_id`, `conference_id`, `title`, `speaker_name`, `conference_year`, `conference_month`, `conference_description`, `talk_date`, `session_id`, `session_description`, `session_abbr`, `session_date`, `session_sequence`, `talk_sequence`, `url`, `uri_l`, `uri_gc`, `data_aid`, `audio_url`, `video_low_url`, `video_med_url`, `video_high_url`, `corpus`, `speaker_role_id`, `kicker`, `talk_preview`, `start_page_num`, `end_page_num`, `extraction_timestamp`, `extraction_version`
- Additional: `annotations` (pipe-joined annotation texts, D-08)

**conference_talk_paragraphs** (from `ParagraphData`, excluding annotation source_type):
- Document: `text` (D-02)
- ID: `f"para_{paragraph_id}"`
- Metadata fields: `paragraph_id`, `talk_id`, `paragraph_number`, `text`, `text_raw`, `word_count`, `source_type`, `list_header`, `list_item_index`, `position_in_item`, `has_scripture_citation`, `has_footnote`, `citation_count`, `footnote_count`, `extraction_warnings`
- Flatten: `extraction_warnings` list -> pipe-joined string (or omit if empty)

**conference_talk_citations** (from `CitationData`):
- Document: `context_window` (D-03); fallback to `citation_text_raw` if empty
- ID: `f"cite_{citation_id}_{paragraph_id}"`
- Metadata fields: `citation_id`, `talk_id`, `paragraph_id`, `paragraph_number`, `citation_text_raw`, `char_position`, `char_end_position`, `scripture_ref`, `book`, `book_abbr`, `book_id`, `chapter`, `verses`, `verse_start`, `verse_end`, `verse_list`, `is_jst`, `citation_location`, `parse_success`, `parse_source`, `parse_pattern`, `parse_confidence`, `context_before`, `context_after`, `context_window`, `extraction_warnings`
- Flatten: `verse_list` (List[int]) -> comma-joined string; `extraction_warnings` -> pipe-joined string

**conference_talk_footnotes** (from `FootnoteData`):
- Document: `context_window` (D-04); fallback to `footnote_text_raw`
- ID: `f"fn_{footnote_id}"`
- Metadata fields: `footnote_id`, `talk_id`, `paragraph_id`, `paragraph_number`, `footnote_number`, `footnote_text_raw`, `char_position`, `context_before`, `context_after`, `context_window`, `parse_success`, `extraction_warnings`
- Flatten: `extraction_warnings` -> pipe-joined string

### Batch Insertion Pattern
```python
# Source: ChromaDB cookbook + batch_utils docs
from chromadb.utils.batch_utils import create_batches

def insert_collection(
    client: chromadb.ClientAPI,
    collection: chromadb.Collection,
    documents: list[str],
    metadatas: list[dict],
    ids: list[str],
    collection_name: str,
) -> int:
    """Insert records with automatic batching and progress logging."""
    batches = create_batches(
        api=client,
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )
    total = len(batches)
    for i, batch in enumerate(batches, 1):
        batch_ids, batch_embeddings, batch_metadatas, batch_documents = batch
        collection.upsert(
            ids=batch_ids,
            documents=batch_documents,
            metadatas=batch_metadatas,
        )
        logger.info(f"{collection_name}: batch {i}/{total} ({len(batch_ids)} records)")
    return len(ids)
```

### Metadata Flattening Helper
```python
def _flatten_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Flatten metadata values to ChromaDB-compatible scalars."""
    result = {}
    for key, value in meta.items():
        if value is None:
            continue  # D-05: non-None only
        if isinstance(value, list):
            if not value:
                continue  # empty arrays not allowed in ChromaDB
            if all(isinstance(v, int) for v in value):
                result[key] = ",".join(str(v) for v in value)
            elif all(isinstance(v, str) for v in value):
                result[key] = "|".join(value)
            else:
                result[key] = str(value)
        elif isinstance(value, (str, int, float, bool)):
            result[key] = value
        else:
            result[key] = str(value)
    return result
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `chromadb.Client()` (in-memory default) | `chromadb.PersistentClient(path=...)` | ChromaDB 0.4+ (2023) | Persistent storage is explicit, not automatic |
| Manual batching with list slicing | `chromadb.utils.batch_utils.create_batches()` | Available since ~0.4.x | Respects client's max_batch_size automatically |
| `collection.add()` for inserts | `collection.upsert()` for idempotent inserts | Available since 0.4+ | add() silently skips duplicates; upsert() updates them |

**Deprecated/outdated:**
- `chromadb.Client()` without arguments: deprecated in favor of explicit `EphemeralClient()` or `PersistentClient()`
- `chroma_db_impl` setting: removed in 0.4+

## Open Questions

1. **Python 3.14 + chromadb compatibility**
   - What we know: chromadb 1.5.5 requires Python >=3.9, wheels built for cp39-abi3
   - What's unclear: Whether abi3 wheels work correctly on Python 3.14 (very new, Dec 2025)
   - Recommendation: Attempt `pipenv install chromadb` and verify import works. If it fails, may need to pin an older chromadb version or use a compatibility shim.

2. **text_raw in paragraph metadata**
   - What we know: D-05 says include all non-None fields. `text_raw` contains full HTML markup.
   - What's unclear: Whether including raw HTML as metadata is desirable (large strings, not useful for filtering)
   - Recommendation: Include per D-05 (include everything). Downstream MCP layer can filter. This matches the "no manual curation" directive.

3. **Existing to_chromadb_format() methods**
   - What we know: All 4 models have these methods. They don't match D-01 through D-06.
   - What's unclear: Whether to update them or ignore them
   - Recommendation: Don't modify them -- they may be used elsewhere or in future. Build standalone transformation in the loader module.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.14.2 | -- |
| pipenv | Package management | Yes | (installed) | -- |
| chromadb | Core feature | **No** | -- | Must install: `pipenv install chromadb` |
| Ollama | Embedding runtime | **Assumed yes** | local | Must be running with `nomic-embed-text` pulled: `ollama pull nomic-embed-text` |
| nomic-embed-text | Embedding model | **Assumed yes** | via Ollama | Pull with `ollama pull nomic-embed-text` if not present |
| pytest | Testing | Yes | 9.0.2 | -- |

**Missing dependencies with no fallback:**
- `chromadb` -- must be installed before any implementation work

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | None (default discovery) |
| Quick run command | `pipenv run py -m pytest tests/test_phase6.py -x` |
| Full suite command | `pipenv run py -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOAD-01 | Transform Phase 5 output into 4 collection formats | unit | `pipenv run py -m pytest tests/test_phase6.py::test_prepare_talks -x` | No -- Wave 0 |
| LOAD-01 | Transform paragraphs with correct document/metadata/id | unit | `pipenv run py -m pytest tests/test_phase6.py::test_prepare_paragraphs -x` | No -- Wave 0 |
| LOAD-01 | Transform citations with correct document/metadata/id | unit | `pipenv run py -m pytest tests/test_phase6.py::test_prepare_citations -x` | No -- Wave 0 |
| LOAD-01 | Transform footnotes with correct document/metadata/id | unit | `pipenv run py -m pytest tests/test_phase6.py::test_prepare_footnotes -x` | No -- Wave 0 |
| LOAD-02 | Annotation paragraphs excluded from paragraphs collection | unit | `pipenv run py -m pytest tests/test_phase6.py::test_annotation_exclusion -x` | No -- Wave 0 |
| LOAD-02 | Annotation text folded into talk metadata | unit | `pipenv run py -m pytest tests/test_phase6.py::test_annotation_folding -x` | No -- Wave 0 |
| LOAD-03 | Citations from annotation paragraphs included normally | unit | `pipenv run py -m pytest tests/test_phase6.py::test_annotation_citation_included -x` | No -- Wave 0 |
| LOAD-04 | Dependency-ordered insertion (talks -> paragraphs -> citations/footnotes) | integration | `pipenv run py -m pytest tests/test_phase6.py::test_insertion_order -x` | No -- Wave 0 |
| LOAD-04 | Batch chunking works for large record sets | integration | `pipenv run py -m pytest tests/test_phase6.py::test_batch_chunking -x` | No -- Wave 0 |
| LOAD-05 | Per-batch progress logged | unit | `pipenv run py -m pytest tests/test_phase6.py::test_batch_logging -x` | No -- Wave 0 |
| LOAD-06 | Verification report with record counts | integration | `pipenv run py -m pytest tests/test_phase6.py::test_verification_counts -x` | No -- Wave 0 |
| LOAD-06 | Verification report with sample retrievals | integration | `pipenv run py -m pytest tests/test_phase6.py::test_verification_retrievals -x` | No -- Wave 0 |
| LOAD-06 | Foreign key spot checks in verification | integration | `pipenv run py -m pytest tests/test_phase6.py::test_verification_fk_checks -x` | No -- Wave 0 |
| D-10 | Invalid talks skipped | unit | `pipenv run py -m pytest tests/test_phase6.py::test_invalid_talk_skipped -x` | No -- Wave 0 |
| D-05/D-06 | Metadata flattening (None removal, list flattening) | unit | `pipenv run py -m pytest tests/test_phase6.py::test_flatten_metadata -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/test_phase6.py -x`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_phase6.py` -- all tests above (new file)
- [ ] `chromadb` package -- `pipenv install chromadb`
- [ ] `source_type` field on `ParagraphData` -- prerequisite for LOAD-02 tests

## Sources

### Primary (HIGH confidence)
- `models/talk_metadata.py` -- TalkMetadata dataclass with 30+ fields, existing `to_chromadb_format()` method
- `models/paragraph_data.py` -- ParagraphData dataclass, confirmed NO `source_type` field
- `models/citation_data.py` -- CitationData dataclass with `verse_list` (List[int]) needing flattening
- `models/footnote_data.py` -- FootnoteData dataclass
- `models/validation_report.py` -- ValidationReport with `is_valid`, `errors`, `warnings`, `stats`
- `extractors/phase2_paragraph_extraction.py` lines 755-766 -- annotation handling, `source_type` set but not passed to ParagraphData
- `extractors/pipeline.py` -- TalkPipelineResult container showing Phase 1-4 output structure
- `config/pipeline_config.py` -- existing constants, where CHROMADB_PATH should be added
- `docs/PIPELINE_SPEC.md` Phase 6 section -- canonical spec for data preparation, annotation handling, insertion, verification

### Secondary (MEDIUM confidence)
- [ChromaDB PyPI](https://pypi.org/project/chromadb/) -- version 1.5.5, 2026-03-10
- [ChromaDB Cookbook Batching](https://cookbook.chromadb.dev/strategies/batching/) -- `create_batches` utility pattern
- [ChromaDB Add Data Docs](https://docs.trychroma.com/docs/collections/add-data) -- metadata types: strings, ints, floats, booleans, typed arrays; no empty arrays
- [ChromaDB Manage Collections Docs](https://docs.trychroma.com/docs/collections/manage-collections) -- `get_or_create_collection`, collection management

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- chromadb is the only new dependency; well-documented
- Architecture: HIGH -- all model fields inventoried from source code; transformation rules derived from locked decisions
- Pitfalls: HIGH -- metadata type constraints verified from official docs; source_type gap confirmed from source code

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (chromadb API stable; model fields change only with pipeline changes)
