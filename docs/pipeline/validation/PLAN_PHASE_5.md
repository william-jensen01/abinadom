# Phase 5: Validation Gate

## Scope

Phase 5 is a **read-only validation gate** between extraction (Phases 1-4) and ChromaDB insertion (Phase 6). No enrichment, no mutations, no auto-fixing, no skipping. It produces a validation report — that's it.

## Design Decisions

- **No enrichment**: All useful enrichment already happens in Phases 1-4 where the data is naturally available
- **No mutations**: Data objects pass through untouched
- **No auto-fixing**: Fixes have side effects; report problems, let humans decide
- **No skipping**: Phase 6 decides what to do with the report
- **Field stripping for ChromaDB**: Phase 6's concern, not Phase 5's
- **Deprecated**: `is_scripture`, `is_internal_reference`, `has_source_text` on footnotes; `char_count`, `is_opening`, `is_closing` on paragraphs; cross-reference linking — all deemed noise

## Input

Per-talk data bundle from Phases 1-4:

- `TalkMetadata` (Phase 1)
- `TalkParagraphs` (Phase 2)
- `TalkCitations` (Phase 3)
- `TalkFootnotes` (Phase 4)

## Output

`ValidationReport` dataclass:

```python
@dataclass
class ValidationReport:
    talk_id: int
    is_valid: bool                  # go/no-go for Phase 6
    errors: list[str]               # integrity violations
    warnings: list[str]             # suspicious but not blocking
    stats: dict[str, Any]           # counts for summary aggregation
```

Follows existing `ValidationResult` pattern used throughout the codebase.

---

## Validation Checks

### 1. Cross-Collection Integrity (the core value of Phase 5)

- [ ] Every citation's `paragraph_id` exists in the paragraph list
- [ ] Every footnote's `paragraph_id` exists in the paragraph list
- [ ] Every citation's `talk_id` matches the talk metadata's `talk_id`
- [ ] Every footnote's `talk_id` matches the talk metadata's `talk_id`
- [ ] `citation_count` on each paragraph matches actual CitationData record count for that paragraph
- [ ] `footnote_count` on each paragraph matches actual FootnoteData record count for that paragraph
- [ ] `has_scripture_citation` is True iff citation_count > 0 (and vice versa)
- [ ] `has_footnote` is True iff footnote_count > 0 (and vice versa)

### 2. Citation DB Validation

- [ ] `citation_id` exists in core.52.db `citation` table
- [ ] `talk_id` exists in the source database talks table
- [ ] `paragraph_id` follows expected formula: `talk_id * 10000 + paragraph_number`

### 3. Paragraph Sanity

- [ ] Sequential numbering (1, 2, 3, ...) — no gaps, no duplicates
- [ ] Reasonable count: WARNING if < 3 or > 150
- [ ] `paragraph_id` follows expected formula: `talk_id * 10000 + paragraph_number`

### 4. ChromaDB Readiness

- [ ] Document text is not empty for every record across all 4 collections (what `to_chromadb_format()` would return as document)
- [ ] IDs are unique within each collection (no duplicate talk_ids, paragraph_ids, citation composite ids, footnote_ids)

### 5. Footnote Sanity

- [ ] `footnote_number` values are reasonable (≥ 1)
- [ ] `footnote_text_raw` is not empty (already enforced by `__post_init__` but belt-and-suspenders)
- [ ] `footnote_id` follows expected formula: `talk_id * 100000 + paragraph_number * 100 + footnote_number` (1-based)

---

## Error vs Warning Classification

**Errors** (is_valid = False):

- Foreign key mismatch (citation/footnote references nonexistent paragraph)
- talk_id mismatch across collections
- citation_id not found in source database
- Duplicate IDs within a collection
- Empty document text (would fail ChromaDB insertion)

**Warnings** (is_valid = True, logged for review):

- Low paragraph count (< 3)
- High paragraph count (> 150)
- citation_count/footnote_count flag mismatch (inconsistency but not fatal)
- Non-sequential footnote numbering

---

## Implementation Plan

- [x] Create `ValidationReport` dataclass in `models/`
- [x] Create `extractors/validation.py` with:
    - `validate_talk(metadata, paragraphs, citations, footnotes, db_conn) -> ValidationReport`
    - Internal helpers for each check category
- [x] DB access: reuse existing database utilities for citation/talk lookups
- [x] Tests: `tests/test_validation.py`

## Result

Implemented 2026-03-10. 31/31 tests passing.
- `models/validation_report.py` — `ValidationReport` dataclass
- `extractors/validation.py` — `validate_talk()` + 5 check helpers
- `tests/test_validation.py` — 31 tests covering all check categories

## Stats Dict Structure

```python
stats = {
    "paragraph_count": int,
    "citation_count": int,
    "footnote_count": int,
    "cross_collection_checks_passed": int,
    "cross_collection_checks_failed": int,
    "db_checks_passed": int,
    "db_checks_failed": int,
}
```
