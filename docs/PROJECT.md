# Scripture Citation Index - Project Context & Design Philosophy

## Project Overview

### What We're Building

A vector database system that transforms an existing SQLite database of LDS General Conference talks into 4 ChromaDB collections optimized for semantic search:

1. **`conference_talks`** - Talk-level metadata and summaries
2. **`conference_talk_paragraphs`** - Searchable paragraph content (primary search surface)
3. **`conference_talk_citations`** - Scripture references with usage context
4. **`conference_talk_footnotes`** - External references (other talks, books, hymns, etc.)

### Data Source

- **Existing SQLite database** containing all General Conference talks with HTML, metadata, speakers, citations
- **Read-only extraction**: We pull from database, transform, and load into ChromaDB
- **No web scraping**: HTML parsing is from stored database content
- **No database insertion**: Database is source only; output goes to ChromaDB

### Data Flow

```
SQLite Database (7,659 talks)
    ↓
for each talk:               ← per-talk streaming loop
    Phase 1 → metadata
    Phase 2 → paragraphs
    Phase 3 → citations
    Phase 4 → footnotes
    Phase 5 → enrich + validate
    → insertion buffer
    ↓ (when buffer full)
Phase 6 → ChromaDB batch write
    ↓
ChromaDB Collections (4 collections for semantic search)
```

Phases 1–5 run sequentially per talk and cannot be skipped or reordered. Phase 6 batches across talks for efficient writes. Progress is tracked by `talk_id` to support resume.

---

## Architecture Decisions

### Chunking Strategy

- **Paragraph-level chunking** with position tracking (paragraph_number)
- Preserves natural document structure
- Enables context reconstruction (fetch ±N paragraphs around results)
- Typical chunk size: 200-800 tokens per paragraph

### Collections Design

**Why 4 collections?**

- **Talks**: High-level metadata, summary search
- **Paragraphs**: Primary semantic search surface (most queries here)
- **Citations**: Find how scriptures are used/applied in talks
- **Footnotes**: Discover cross-references and source networks

**Citations vs Footnotes:**

- **Citations collection**: Scripture references (inline OR footnote format), with surrounding context
- **Footnotes collection**: Non-scripture references only (conference talks, books, hymns, other sources)
- **Grouping logic**: By _what it references_ (content type), not _where it appears_ (location in document)

### ID Strategy

- Use existing SQLite primary keys: `talk_8820`, `para_156789`, `cite_45123`, `footnote_78945`
- Enables bidirectional lookups between ChromaDB and SQLite
- Maintains referential integrity across collections

### Data Preparation Format

Each collection needs three parallel lists for ChromaDB insertion:

```python
documents = ["text to embed...", ...]  # What gets embedded
metadatas = [{metadata dict}, ...]      # Fields for filtering/retrieval
ids = ["talk_8820", ...]                # Unique identifiers
```

---

## Core Design Philosophy

### 1. **Layered Architecture (Separation of Concerns)**

Every phase follows three distinct layers:

- **Data Access Layer**: Query database, fetch HTML/text
- **Extraction/Transformation Layer**: Parse, structure, apply business logic
- **Validation Layer**: Ensure quality, completeness, integrity

**Why**: Changes to database schema, parsing logic, or validation rules remain isolated. Modify one layer without touching others.

### 2. **Configuration-Driven Design**

Define schemas, requirements, and rules in configuration objects, not hardcoded:

```python
SCHEMA_CONFIG = {
    'field_name': {
        'required': True/False,
        'type': str/int/list,
        'validator': function,
        'default': value
    }
}
```

**Why**: Self-documenting, testable, extensible. Add fields or change rules without code changes.

### 3. **Pure Functions + Composition**

Build workflows from small, focused, pure functions:

- Same input → same output (deterministic)
- No side effects (no I/O, logging, state mutation inside extraction)
- Single responsibility per function
- Compose small functions into larger workflows

**Why**: Easy to test (no mocking), easy to debug (no hidden state), easy to parallelize, easy to reuse.

### 4. **Type Safety with Dataclasses**

Use typed dataclasses for all data structures, not raw dictionaries:

```python
@dataclass
class TalkMetadata:
    talk_id: int
    speaker: str
    talk_title: str
    # ... with validation in __post_init__

    def to_dict(self):
        return asdict(self)
```

**Why**: Type checking catches errors at dev time, IDE autocomplete, self-documenting, built-in validation, safer than string-key dicts.

### 5. **Defensive Programming**

Database data may be incomplete or malformed. Handle gracefully:

- **Required fields**: Fail-fast (raise exception immediately)
- **Optional fields**: Fail-safe (use None/default, log warning, continue)
- **Validate at boundaries**: Immediately after extraction, before passing downstream
- **Explicit error handling**: Catch specific exceptions, not generic try/except

**Why**: One bad record shouldn't crash entire batch. Log issues for review.

### 6. **Fail-Fast vs Fail-Safe Hybrid**

- **Critical data** (talk_id, speaker, title): Missing → raise exception, halt processing
- **Optional data** (session, calling): Missing → log warning, use None, continue
- **Return results + errors**: Let caller decide strict vs lenient mode

**Why**: Flexibility for development (strict) vs production batch processing (lenient).

### 7. **Structured Logging with Context**

Every log entry includes contextual metadata:

```python
logger.info("Processing", extra={
    'talk_id': 8820,
    'phase': 1,
    'action': 'extracting_metadata'
})
```

Log levels:

- DEBUG: Detailed steps
- INFO: Successful operations
- WARNING: Missing optional fields, using defaults
- ERROR: Missing required fields, parse failures
- CRITICAL: Complete phase failure

**Why**: Filter by talk_id or phase, aggregate statistics, trace specific records through pipeline, export to analysis tools.

### 8. **Idempotent Design**

Can run phases multiple times safely:

- Use existing database IDs (no new ID generation)
- Track extraction metadata (timestamp, code version, warnings)
- Support "skip if processed" and "force reprocess" modes
- No state accumulation between runs

**Why**: Reprocess when improving extraction logic, fix specific records, resume after interruption.

### 9. **Test-First Mindset**

Create fixtures and tests alongside implementation:

- Normal case (well-formed data)
- Missing optional fields
- Missing required fields
- Malformed data (bad formats, encoding issues)
- Edge cases (very short/long content, special characters)

**Why**: Find edge cases early, enable safe refactoring, document expected behavior, regression protection.

### 10. **DRY with Pragmatism**

- **DRY (Don't Repeat Yourself)**: Extract truly common operations into utilities (text cleaning, date parsing, validation frameworks)
- **WET (Write Everything Twice)**: Keep field-specific logic separate even if similar (speaker extraction ≠ title extraction, even if both "get text from HTML")

**Why**: Balance abstraction (reduce duplication) with clarity (don't obscure what's happening).

### 11. **Documentation as Executable Contracts**

Every function has explicit contracts:

```python
def extract_field(data: dict, field: str) -> Optional[str]:
    """Extract and validate field from raw data.

    Args:
        data: Raw database row as dict
        field: Field name to extract

    Returns:
        Validated field value or None if missing/invalid

    Raises:
        ValidationError: If field format invalid

    Example:
        >>> extract_field({'speaker': 'Elder Holland'}, 'speaker')
        'Elder Holland'
    """
```

**Why**: Clear expectations, self-documenting, enables contract-based testing.

### 12. **Pattern Consistency Across Phases**

Whatever works in Phase 1 becomes the template for Phases 2-6:

- Same layered architecture
- Same dataclass approach
- Same error handling strategy
- Same logging format
- Same testing patterns
- Same configuration approach

**Why**: Each new phase feels familiar, reducing cognitive load. Developers know what to expect.

### 13. **Future-Proofing Without Over-Engineering**

- Build shared utilities when you see duplication (Phase 2+)
- Add abstractions when patterns emerge, not before
- Keep Phase 1 simple and clear
- Let complexity grow organically as needs become clear

**Why**: Premature abstraction creates unnecessary complexity. But planning for reuse prevents total rewrites later.

### 14. **Performance: Correctness First, Then Speed**

- Focus on correctness in initial implementation
- Batch database queries and ChromaDB insertions (1000-5000 records)
- Stream results to avoid memory issues with large datasets
- Show progress for long-running operations
- Profile before optimizing

**Why**: Clear, correct code is fast enough. The bottleneck is I/O (database/ChromaDB), not CPU.

---

## 6-Phase Implementation Roadmap

### Phase 1: Talk Metadata Extraction ✅

Extract talk-level data from database → prepare for ChromaDB

### Phase 2: Paragraph Segmentation ✅

Parse HTML from database → split into paragraphs with position tracking

### Phase 3: Citation Extraction & Parsing

Single pass: detect citations in paragraphs, extract strings and positions, parse into structured fields (book, chapter, verses), and capture surrounding context window

### Phase 4: Footnote Extraction & Parsing

Single pass: parse footnote markers and content from HTML, classify by reference type (talk/book/hymn/scripture/other), and capture surrounding context window

### Phase 5: Enrich, Link & Validate

Add calculated fields and flags, link footnotes to other talks in the database, verify integrity and completeness across all data

### Phase 6: Load to ChromaDB

Transform validated data into documents/metadatas/ids lists, batch insert into 4 collections with progress tracking, verify counts and validate search quality

---

## Key Metadata Schemas

### Talk Metadata

- talk_id, speaker, speaker_calling, talk_title
- conference_id, conference_year, conference_month, session
- talk_url, language
- total_paragraphs, total_citations, total_footnotes

### Paragraph Metadata

- paragraph_id, talk_id, paragraph_number, text
- word_count, char_count
- is_opening, is_closing
- has_scripture_citation, has_footnote

### Citation Metadata

- citation_id, talk_id, paragraph_id, paragraph_number
- citation_text_raw, scripture_ref
- book, chapter, verses, verse_start, verse_end, verse_list
- char_position, context_before, context_after, context_window
- citation_format (inline/footnote), is_jst
- parse_success, parse_pattern, parse_confidence

### Footnote Metadata

- footnote_id, talk_id, paragraph_id, footnote_number
- footnote_text_raw, reference_type (conference_talk/book/hymn/scripture/other)
- Type-specific fields (referenced_speaker, referenced_title, author, book_title, hymn_number, etc.)
- char_position, context_before, context_after, context_window
- referenced_talk_id, has_source_text, is_internal_reference
- parse_success, parse_pattern, parse_confidence

---

## Success Metrics

### Completeness

- % of talks successfully processed
- % of citations successfully parsed
- % of footnotes successfully parsed
- % of cross-references linked

### Quality

- Parse accuracy (validate against samples)
- Context window relevance
- Foreign key integrity (100% required)
- Semantic search relevance

### Performance

- Processing time per talk
- Total extraction time
- ChromaDB insertion time
- Memory usage
