# Architecture

**Analysis Date:** 2026-03-18

## Pattern Overview

**Overall:** Layered, phase-based data extraction pipeline using pure functions and dataclasses

**Key Characteristics:**
- **6-Phase Sequential Pipeline** — Each phase depends on previous output; phases 1–5 are per-talk, phase 6 batches across talks
- **Layered Architecture** — Database Layer → Extraction/Transformation Layer → Validation Layer within each phase
- **Type-Safe Dataclasses** — All data structures use typed dataclasses with validation, no raw dictionaries
- **Pure Functions + Composition** — Deterministic, no side effects, easily testable and debuggable
- **Configuration-Driven Design** — Schemas and rules defined in config, not hardcoded
- **Idempotent Design** — Can reprocess talks safely using existing database IDs; no state accumulation

## Layers

**Data Access Layer:**
- Purpose: Query SQLite databases (core.52.db for metadata, content.52.db for HTML), fetch raw data
- Location: `db/__init__.py` provides Database class with read-only connections
- Modules: `extractors/phase1_talk_metadata.py` (talk queries), `extractors/phase2_paragraph_extraction.py` (HTML fetch)
- Depends on: SQLite via sqlite3 module
- Used by: All extraction phases

**Extraction/Transformation Layer:**
- Purpose: Parse, structure, and transform raw database data into strongly-typed business objects
- Location: `extractors/phase*_*.py` modules for phases 1–5
- Contains: HTML parsing (`extractors/html_parsing_utils.py`), paragraph splitting, citation/footnote parsing, enrichment
- Depends on: Data Access Layer, BeautifulSoup for HTML parsing, regex for pattern matching
- Used by: Validation Layer, Pipeline Orchestrator

**Validation Layer:**
- Purpose: Ensure data quality, completeness, and integrity; produce validation reports
- Location: `extractors/phase5_validation.py`, `__post_init__` methods in dataclasses
- Contains: Schema validation (`config/schemas.py`), field validators (`utils/validators.py`), integrity checks
- Depends on: Extraction Layer output, dataclass definitions
- Used by: Pipeline Orchestrator (phase 6), ChromaDB insertion

**Pipeline Orchestrator:**
- Purpose: Coordinate phases 1–4 for a single talk, share computed contexts across phases, aggregate diagnostics
- Location: `extractors/pipeline.py`
- Contains: `process_talk_pipeline()` function, shared HTML context building
- Depends on: All extraction phases, dataclass models
- Used by: Main processing scripts (UPDATE.py, process_all.py)

## Data Flow

**Per-Talk Processing Loop:**

1. **Phase 1 — Talk Metadata Extraction**
   - Query core.52.db for talk, speaker, conference, session data
   - Validate required fields (talk_id, speaker_name, title, conference_year, talk_date)
   - Return: `TalkMetadata` dataclass with extraction metadata

2. **Phase 2 — Paragraph Segmentation**
   - Fetch HTML from content.52.db
   - Parse with BeautifulSoup, find body container (div.body-block or fallback)
   - Extract paragraphs (p tags), clean HTML markup, calculate word counts
   - Return: `TalkParagraphs` container with list of `ParagraphData` objects
   - Tracks: paragraph_id, paragraph_number, text, word_count, position in talk

3. **Build Shared HTML Contexts** (between phases 2–4)
   - Create `ParagraphHTMLContext` wrapper for each paragraph's original HTML
   - Lazy parsing — parse HTML only when first accessed
   - Parser: configurable (default: html.parser)

4. **Phase 3 — Citation Extraction & Parsing**
   - For each paragraph, detect scripture reference patterns in text (inline citations and footnotes)
   - Use core.52.db citation table (primary source) with regex fallback for unmatched
   - Extract: citation_text_raw, position, parsed fields (book, chapter, verses, verse_start/end/list)
   - Extract context windows (50-100 chars before/after citation)
   - Return: `TalkCitations` with `CitationData` objects, parse_success flags, parse_confidence scores
   - Mutates: backfill citation_count on ParagraphData objects

5. **Phase 4 — Footnote Extraction & Parsing**
   - For each paragraph, detect footnote markers (superscript numbers) and extract content
   - Extract: footnote_number, footnote_text_raw, marker position in text
   - Extract context windows around marker
   - Return: `TalkFootnotes` with `FootnoteData` objects
   - Mutates: backfill footnote_count on ParagraphData objects

6. **Phase 5 — Enrich & Validate** (planned)
   - Add calculated fields to paragraphs (is_opening, is_closing flags)
   - Add enrichment to citations/footnotes (parse_source, parse_pattern, parse_confidence)
   - Validate all foreign keys, position bounds, field integrity
   - Generate validation report

7. **Phase 6 — ChromaDB Batch Insertion** (planned)
   - Buffer multiple talks' data
   - Transform to ChromaDB format: documents (text to embed), metadatas (filtering fields), ids
   - Insert into 4 collections: conference_talks, conference_talk_paragraphs, conference_talk_citations, conference_talk_footnotes
   - Verify record counts and sample search quality

**State Management:**
- No persistent state accumulation — each talk is independent
- Progress tracked by talk_id (resume support via external tracking)
- Buffering: per-talk data + insertion buffer (configurable size, e.g., 500–1000 talks) in memory
- Memory footprint: one talk's processed data + buffer, not cumulative

## Key Abstractions

**TalkMetadata (`models/talk_metadata.py`):**
- Purpose: Represents all talk-level metadata from database
- Examples: speaker, title, conference, session, media URLs, corpus code
- Pattern: Dataclass with typed fields, `__post_init__` validation, `to_chromadb_format()` method for insertion
- Validation: `validate_against_schema()` checks against TALK_METADATA_SCHEMA

**ParagraphData (`models/paragraph_data.py`):**
- Purpose: Represents a single paragraph with position tracking within a talk
- Examples: text, word_count, paragraph_number, is_opening/closing flags
- Pattern: Dataclass with downstream citation/footnote flags (populated by phases 3–4)
- Validation: text non-empty, word_count non-negative, paragraph_number >= 1

**CitationData (`models/citation_data.py`):**
- Purpose: Represents a scripture citation with parsed fields and context
- Examples: scripture_ref (normalized), book, chapter, verses, verse_start/end/list
- Pattern: Dataclass with parse_success, parse_confidence, context_window fields
- ID Format: `cite_{citation_id}_{paragraph_id}` for ChromaDB uniqueness

**FootnoteData (`models/footnote_data.py`):**
- Purpose: Represents a footnote with position and context
- Examples: footnote_number, footnote_text_raw, context_before/after
- Pattern: Dataclass with parse_success flag
- ID Format: `fn_{footnote_id}` for ChromaDB uniqueness

**TalkPipelineResult (`extractors/pipeline.py`):**
- Purpose: Aggregated output from all 4 phases for a single talk
- Contains: metadata, paragraphs, citations, footnotes, warnings, errors lists
- Pattern: Dataclass with `success` property (all phases non-error)

**ParagraphHTMLContext (`extractors/html_parsing_utils.py`):**
- Purpose: Lazy-parsed HTML wrapper for a single paragraph, shared across phases 3–4
- Stores: raw HTML, parser choice, cached BeautifulSoup object
- Pattern: Single instance per paragraph reused by citation and footnote extractors
- Benefit: Parse HTML once, use for citation detection, footnote marker position finding, context extraction

**Database (`db/__init__.py`):**
- Purpose: Wrapper for SQLite connections with read-only mode and timeout handling
- Methods: `select()` (query), `select_one()` (single row), `scalar()` (single value), `execute()` (write, raises if read-only)
- Instances: `core_db`, `content_db` (module-level singletons)
- Timeouts: Configurable, default 5 seconds; progress handler for interruption

## Entry Points

**UPDATE.py:**
- Location: `/c/Users/wbjen/OneDrive/Documents/LDS MCP/UPDATE.py`
- Triggers: Invoked manually to sync conference-specific database (gc.db) to core and JSON files
- Responsibilities: Database synchronization, topic/speaker role/talk relationship updates

**process_all.py:**
- Location: `/c/Users/wbjen/OneDrive/Documents/LDS MCP/process_all.py`
- Triggers: Invoked to process all talks through the 6-phase pipeline
- Responsibilities: Iterate talks, call pipeline.process_talk_pipeline(), buffer results, trigger phase 6 insertion

**process_topics.py:**
- Location: `/c/Users/wbjen/OneDrive/Documents/LDS MCP/process_topics.py`
- Triggers: Specific to topic-based processing
- Responsibilities: Topic filtering and talk selection

**Extraction Phase Runner Functions:**
- `process_talk_pipeline()` in `extractors/pipeline.py` — Main orchestrator
- Each phase has a `process_talk_*()` function:
  - `process_talk_paragraphs()` in phase2_paragraph_extraction.py
  - `process_talk_citations()` in phase3_citation_extraction.py
  - `process_talk_footnotes()` in phase4_footnote_extraction.py

## Error Handling

**Strategy:** Fail-safe for optional data, fail-fast for required data

**Patterns:**
- **Required Fields** (talk_id, speaker_name, title, conference_year) — Missing → raise exception immediately, halt talk processing
- **Optional Fields** (session, media URLs) — Missing → use None/default, log warning, continue processing
- **Extraction Failures** — Mark parse_success=False, log warning with context, include in extraction_errors list
- **Database Errors** — Catch sqlite3.OperationalError (timeout, locked), log and retry or return empty result
- **Validation Errors** — Catch ValueError from dataclass `__post_init__`, log with talk_id context, flag in report

**Logging:**
- Framework: Python logging module
- Context fields: talk_id, paragraph_id, phase name, action description
- Levels: DEBUG (detailed steps), INFO (successful extraction), WARNING (missing optional fields), ERROR (parse/validation failures), CRITICAL (phase failure)
- File logging: Configured in each phase module via basicConfig

## Cross-Cutting Concerns

**Logging:** Contextual logging in each phase module; logger instances configured per module (talk_metadata, paragraph_extraction, etc.)

**Validation:**
- Field-level: validators in `utils/validators.py` (validate_year, validate_month, validate_date_iso, validate_speaker_name, validate_positive_int)
- Schema-level: `config/schemas.py` defines TALK_METADATA_SCHEMA, PARAGRAPH_CONFIG; `validate_schema()` function checks against schema
- Dataclass-level: `__post_init__` methods in all model classes validate required fields and consistency

**Authentication:** Not applicable — read-only database connections, no user auth required

**Performance Optimization:**
- Lazy HTML parsing via ParagraphHTMLContext (parse once, reuse across phases 3–4)
- Shared book cache for Phase 3 (pre-loaded scripture book reference data from core.52.db)
- Batch insertion to ChromaDB (buffer talks, insert in 1000–5000 record chunks)
- Timeout handling for long queries (5-second default, configurable)

---

*Architecture analysis: 2026-03-18*
