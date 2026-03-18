# Scripture Citation Index - Data Extraction System

## Prime Directive

Extract and structure General Conference talk data into a multi-collection vector database system that enables semantic search across talks, paragraphs, scripture citations, and footnotes while preserving contextual relationships and citation networks.

## Ultimate Goal

Transform raw General Conference HTML into four interconnected ChromaDB collections:

1. `conference_talks` - Talk-level metadata and summaries
2. `conference_talk_paragraphs` - Searchable paragraph content
3. `conference_talk_citations` - Scripture references with usage context
4. `conference_talk_footnotes` - External references (talks, books, hymns, etc.)

Each collection must maintain referential integrity through `talk_id`, `paragraph_id`, and other linking fields, enabling both semantic search within collections and relational queries across collections.

## Success Criteria

- All General Conference talks extracted with complete metadata
- Paragraphs maintain position and context within talks
- Scripture citations parsed into structured fields (book, chapter, verses)
- Footnotes categorized by reference type with parsed metadata where possible
- Context windows extracted for all citations and footnotes
- Cross-references identified (footnotes pointing to other talks in database)
- All data ready for ChromaDB insertion without additional processing
- Extraction process is idempotent and resumable

---

## System Architecture Overview

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
Semantic Search + Relational Queries
```

### Core Components

1. **Metadata Extractor** - Parse talk-level information
2. **Content Splitter** - Segment talks into paragraphs
3. **Citation Extractor & Parser** - Detect, extract, parse, and contextualize scripture references
4. **Footnote Extractor & Parser** - Detect, extract, parse, and contextualize footnote references
5. **Enrichment & Validator** - Enrichment, cross-reference linking, and integrity checks
6. **ChromaDB Loader** - Prepare, insert, and verify all collections

---

## Processing Model

The pipeline is a **per-talk streaming loop**, not a series of independent batch jobs.

```python
for talk in database.all_talks():
    metadata   = phase_1(talk)
    paragraphs = phase_2(talk)
    citations  = phase_3(paragraphs)
    footnotes  = phase_4(paragraphs)
    record     = phase_5(metadata, paragraphs, citations, footnotes)
    buffer.add(record)

    if len(buffer) >= BATCH_SIZE:
        phase_6_insert(buffer.flush())

phase_6_insert(buffer.flush())  # remaining
```

**Key constraints:**

- Phases 1–5 are a **locked sequence**. Each phase depends on the output of the previous. You cannot skip a phase or run them out of order.
- If reprocessing is needed, restart from Phase 1 for the affected talk(s).
- Phase 6 is the only phase that spans multiple talks — it buffers records and writes in batches for ChromaDB efficiency.
- Progress is tracked by `talk_id`. A failed or interrupted run resumes from the last successfully processed talk.
- Memory footprint at any point = one talk's worth of data + the write buffer (configurable, default 500–1000 talks).

---

## Implementation Phases

### Phase 1: Talk Metadata Extraction ✅

**Objective:** Extract and validate basic talk-level information

**Input:** SQLite database (talks table)
**Output:** Dictionary containing talk metadata

**Key Fields to Extract:**

- talk_id (from existing database)
- speaker name
- speaker calling/position
- talk title
- conference identifier (YYYY-MM format)
- conference year
- conference month
- session name
- talk URL
- language
- delivery date

**Validation Checks:**

- All required fields present
- Conference ID format valid
- Speaker name not empty
- URL accessible

**Error Handling:**

- Log missing fields
- Flag unparseable metadata
- Continue processing with warnings

---

### Phase 2: Paragraph Segmentation ✅

**Objective:** Split talk content into individual paragraphs with position tracking

**Input:** Raw HTML talk content from SQLite
**Output:** List of paragraph dictionaries

**Key Fields per Paragraph:**

- paragraph_id (from database)
- talk_id (foreign key)
- paragraph_number (sequential position)
- text (cleaned paragraph content)

**Processing Steps:**

- Extract all paragraph tags from HTML
- Clean whitespace and formatting
- Number sequentially
- Filter empty paragraphs
- Exclude headers/footers

**Validation Checks:**

- Text not empty after cleaning
- Sequential numbering
- Total count reasonable (typically 10-50 paragraphs)

**Error Handling:**

- Skip empty paragraphs
- Log unusual paragraph counts
- Preserve original text for debugging

---

### Phase 3: Citation Extraction & Parsing ✅

**Objective:** In a single pass — detect citations, extract strings and positions, parse into structured fields, and capture context windows

**Input:** Paragraph dictionaries from Phase 2
**Output:** List of fully-parsed citation dictionaries with context

**Key Fields per Citation:**

- citation_id (generated)
- talk_id (foreign key)
- paragraph_id (foreign key)
- paragraph_number (for ordering)
- citation_text_raw (exact string found)
- char_position (start position in paragraph)
- char_end_position (end position in paragraph)
- scripture_ref (normalized reference)
- book (full book name)
- book_abbr (if abbreviated in source)
- chapter (integer)
- verses (string: "3", "3-10", "3,5,7", or None)
- verse_start (integer or None)
- verse_end (integer or None)
- verse_list (list of integers or None)
- is_jst (boolean for Joseph Smith Translation)
- parse_success (boolean)
- parse_pattern (which regex matched)
- parse_confidence (high/medium/low)
- context_before (text before citation)
- context_after (text after citation)
- context_window (combined context around citation)

**Detection Logic:**

- Basic scripture reference patterns
- Common book name abbreviations
- Chapter:verse format
- Range and list formats

**Extraction Logic:**

- Use regex to find scripture patterns
- Capture start/end positions
- Extract exact matched text
- Handle multiple citations per paragraph

**Parsing Logic:**

- Try patterns from most specific to most general
- Handle book name variations and abbreviations
- Parse verse ranges (e.g., "3-10") and lists (e.g., "3,5,7")
- Detect JST prefix
- Normalize book names to standard form

**Context Extraction Logic:**

- Define context window size (e.g., 50-100 characters each side)
- Extract text before and after citation position
- Combine into full context window
- Handle paragraph boundaries

**Validation Checks:**

- Pattern matches not false positives
- Positions within paragraph bounds
- Verse ranges valid (start <= end)
- Book name recognized
- Context windows not empty

**Error Handling:**

- Mark parse_success=False for failures
- Adjust context window if near paragraph boundaries
- Log unrecognized patterns and position errors
- Preserve raw text always

---

### Phase 4: Footnote Extraction & Parsing ✅

**Objective:** In a single pass — detect footnote markers, extract content, and capture context windows

**Input:** Paragraph dictionaries from Phase 2 (HTML structure and text)
**Output:** List of fully-parsed footnote dictionaries with context

**Key Fields per Footnote:**

- footnote_id (generated)
- talk_id (foreign key)
- paragraph_id (foreign key)
- paragraph_number (for ordering)
- footnote_number (superscript number)
- footnote_text_raw (full footnote text)
- char_position (where superscript appears in paragraph)
- context_before, context_after, context_window
- parse_success (boolean)
- extraction_warnings (list of strings)

**Extraction Logic:**

- Identify footnote markers (superscripts) in HTML
- Match markers to footnote content
- Extract full footnote text and marker position

**Context Extraction Logic:**

- Same window approach as Phase 3
- Account for superscript markers in position calculation

**Validation Checks:**

- Footnote numbers sequential
- All markers have corresponding content
- Reference type assigned
- Type-specific fields populated correctly

**Error Handling:**

- Fall back to 'other' type if parsing fails
- Log unrecognized formats
- Handle non-sequential numbering
- Preserve original text always

---

### Phase 5: Enrich, Link & Validate

**Objective:** Add calculated fields and flags, and verify integrity across all data

**Input:** All data structures from Phases 1–4
**Output:** Enriched and validated data ready for loading; validation report

#### Enrichment

**Paragraph Enrichment:**

- word_count, char_count
- is_opening (first 1-2 paragraphs), is_closing (last 1-2 paragraphs)
- has_citation (boolean), citation_count (integer)
- has_footnote (boolean), footnote_count (integer)

**Citation Enrichment:**

- citation_format (inline vs footnote)
- has_source_text (always True for scriptures)

**Footnote Enrichment:**

- has_source_text (True if we have referenced content)
- is_internal_reference (True if points to talk in our DB)
- is_scripture (True if reference_type is scripture)

#### Data Validation

**Talk-Level:**

- All required fields present
- No duplicate talk_ids
- Conference IDs follow format
- Reasonable paragraph counts

**Paragraph-Level:**

- All paragraphs link to valid talk_id
- Sequential paragraph numbering
- No empty text fields
- is_opening/is_closing flags logical

**Citation-Level:**

- All citations link to valid talk_id and paragraph_id
- Positions within paragraph bounds
- Parsed scripture references valid
- Context windows not empty

**Footnote-Level:**

- All footnotes link to valid talk_id and paragraph_id
- Footnote numbers reasonable
- referenced_talk_ids (if set) exist in database
- Reference types assigned

**Cross-Collection Integrity:**

- All foreign keys resolve
- Citation/footnote counts match actual records
- No orphaned records

**Error Handling:**

- Separate critical vs warning issues
- Auto-fix minor issues where safe
- Generate full validation report

---

### Phase 6: Load to ChromaDB

**Objective:** Transform validated data into ChromaDB-ready format, batch insert into 4 collections, and verify correctness

**Input:** Enriched, validated data structures from Phase 5
**Output:** Populated ChromaDB collections; verification report

#### Data Preparation

Transform each record into three parallel lists per collection:

_conference_talks:_

- documents = talk summaries/titles for embedding
- metadatas = talk metadata dicts
- ids = talk_id strings (e.g., "talk_8820")

_conference_talk_paragraphs:_

- documents = paragraph text for embedding
- metadatas = paragraph metadata dicts
- ids = paragraph_id strings (e.g., "para_156789")

_conference_talk_citations:_

- documents = context_window text for embedding
- metadatas = citation metadata dicts
- ids = citation_id strings (e.g., "cite_45123")

_conference_talk_footnotes:_

- documents = context_window text for embedding
- metadatas = footnote metadata dicts
- ids = footnote_id strings (e.g., "footnote_78945")

**Transformation Rules:**

- Flatten any nested structures in metadata
- Handle None/null values appropriately
- Ensure all three lists are the same length per collection

#### Annotation Handling (`source_type="annotation"`)

Paragraphs emitted by Phase 2 with `source_type="annotation"` represent publisher/editorial notes (`div.annotation` in the talk HTML). They flow through the pipeline as normal paragraphs so Phase 3 can extract any citations they contain, but Phase 6 handles them specially:

- **Excluded** from `conference_talk_paragraphs` — not embedded; annotation text is not talk body content
- **Folded into** `conference_talks` metadata as `annotations` (pipe-joined string of all annotation texts for that talk)
- **Citations inside annotations** are included in `conference_talk_citations` normally — their `paragraph_id` remains valid even though the parent paragraph is not embedded

#### Insertion

**Strategy:**

- Create/get collections with appropriate embedding function
- Insert in dependency order: talks → paragraphs → citations/footnotes
- Batch in chunks (e.g., 5000 records) to avoid memory issues
- Show progress for large batches

**Error Handling:**

- Retry failed batches
- Log insertion errors with context
- Provide insertion summary report

#### Post-Insertion Verification

**Record Counts:**

- Counts match expected totals
- Cross-reference counts align

**Sample Queries:**

- Semantic search on paragraphs works
- Metadata filtering works
- Citation lookup by scripture reference works
- Footnote lookup by reference type works

**Data Integrity:**

- Foreign keys resolvable across collections
- Context windows contain expected text
- Embeddings generated for all documents

**Error Handling:**

- Report specific failures with remediation suggestions
- Flag data quality issues

---

## Error Handling Strategy

### Error Categories

1. **Critical Errors** - Stop processing (e.g., database connection failure)
2. **Data Errors** - Skip record, log, continue (e.g., unparseable citation)
3. **Warnings** - Log but process anyway (e.g., low parse confidence)

### Logging Requirements

- Timestamp all log entries
- Include context (talk_id, paragraph_number, etc.)
- Categorize by severity (ERROR, WARNING, INFO)
- Log to file for later review
- Provide summary statistics

### Recovery Mechanisms

- Save progress after each phase/batch
- Support resume from last successful point
- Checkpoint data to disk
- Allow reprocessing of failed records

---

## Testing Strategy

### Unit Testing

- Test each parser function independently
- Use fixtures with known inputs/outputs
- Test edge cases and error conditions
- Validate regex patterns

### Integration Testing

- Test phase-to-phase data flow
- Verify foreign key relationships
- Test batch processing
- Test ChromaDB insertion

### Data Quality Testing

- Sample manual review of parsed citations
- Review parse failure rates
- Check context window quality
- Verify cross-references

### Performance Testing

- Measure extraction time per talk
- Monitor memory usage during batching
- Test with full dataset scale
- Optimize bottlenecks

---

## Configuration and Customization

### Configurable Parameters

- Context window size (characters)
- Batch size for ChromaDB insertion
- Embedding model selection
- Parse confidence thresholds
- Logging verbosity
- Output file paths

### Source Data Configuration

- SQLite database path and connection details
- Starting talk_id/range
- Language filtering

### Processing Options

- Skip already processed talks
- Force reprocess option
- Dry run mode (extract but don't insert)

---

## Expected Outputs

### Per-Phase Outputs

- JSON/CSV files with extracted data
- Validation reports
- Error logs
- Progress statistics

### Final Outputs

- 4 populated ChromaDB collections
- Complete extraction log
- Data quality report
- Insertion summary
- Cross-reference mapping file
- Failed records report (if any)

### Documentation Outputs

- Schema documentation for each collection
- Sample queries and results
- Statistics (total talks, paragraphs, citations, footnotes)
- Parse success rates by type

---

## Success Metrics

### Completeness Metrics

- % of talks successfully processed
- % of citations successfully parsed
- % of footnotes successfully parsed
- % of cross-references linked

### Quality Metrics

- Parse accuracy (manual sample validation)
- Context window relevance
- Foreign key integrity (100% required)
- Semantic search relevance

### Performance Metrics

- Processing time per talk
- Total extraction time
- ChromaDB insertion time
- Memory usage
