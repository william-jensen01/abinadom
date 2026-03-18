# Codebase Structure

**Analysis Date:** 2026-03-18

## Directory Layout

```
LDS MCP/
├── .planning/              # Planning and analysis documents
│   └── codebase/          # GSD-generated architecture and conventions
├── api/                   # API integration modules (external services)
├── config/                # Configuration and schema definitions
│   ├── schemas.py         # Field schemas and validation rules (config-driven)
│   └── __init__.py
├── db/                    # Database layer and connection management
│   ├── core.52.db         # Main database: talks, speakers, conferences, sessions, citations
│   ├── content.52.db      # HTML content database: talk body HTML
│   ├── gc.db              # Temporary conference-specific database (topic.db alternative)
│   ├── topic.db           # Topic cross-reference database
│   ├── one-off-migration/ # Legacy migration scripts
│   │   ├── backfill_*.py  # Data synchronization utilities
│   │   └── __init__.py
│   ├── __init__.py        # Database class, core_db and content_db instances
│   ├── queries.sql        # SQL query templates and reference
│   └── sql-queries.md     # SQL documentation
├── docs/                  # Project documentation
│   ├── PROJECT.md         # Project overview and design philosophy
│   ├── PIPELINE_SPEC.md   # Phase 1–6 pipeline specification
│   ├── update/            # Update process documentation
│   │   └── Update_GC_PLAN.md
│   └── pipeline/          # Phase-specific implementation docs
│       ├── phase-1-metadata/
│       ├── phase-2-paragraph/
│       ├── phase-3-citation/
│       ├── phase-4-footnote/
│       └── phase-5-validation/
├── examples/              # Example scripts for each phase
│   ├── phase1_example.py
│   ├── phase2_example.py
│   ├── phase3_example.py
│   ├── phase4_example.py
│   └── ...
├── extractors/            # Phase implementation modules (core business logic)
│   ├── html_parsing_utils.py     # Shared HTML parsing, body detection, context extraction
│   ├── phase1_talk_metadata.py   # Phase 1: talk metadata extraction
│   ├── phase2_paragraph_extraction.py  # Phase 2: paragraph splitting
│   ├── phase3_citation_extraction.py   # Phase 3: scripture citation parsing
│   ├── phase4_footnote_extraction.py   # Phase 4: footnote extraction
│   ├── phase5_validation.py      # Phase 5: enrichment and validation
│   ├── pipeline.py               # Unified orchestrator (phases 1–4 per talk)
│   └── __init__.py
├── models/                # Data structure definitions (dataclasses with validation)
│   ├── talk_metadata.py   # TalkMetadata dataclass
│   ├── paragraph_data.py  # ParagraphData, TalkParagraphs dataclasses
│   ├── citation_data.py   # CitationData, TalkCitations dataclasses
│   ├── footnote_data.py   # FootnoteData, TalkFootnotes dataclasses
│   ├── validation_report.py  # ValidationReport dataclass
│   └── __init__.py
├── output/                # Generated output files and artifacts
│   ├── extract_element_text/  # Output from example runs
│   └── pipeline/              # ChromaDB results and verification reports
├── process_topic_talks/   # Topic-based processing (alternative to all-talks)
│   └── metadata/          # Topic metadata storage
├── scripts/               # Utility and maintenance scripts
├── tasks/                 # Task tracking and lessons learned
│   ├── todo.md           # Current task list
│   └── lessons.md        # Self-improvement log (patterns to avoid)
├── tests/                 # Test suite (pytest)
│   ├── test_html_parsing_utils.py
│   ├── test_phase1.py
│   ├── test_phase2.py
│   ├── test_phase3.py
│   ├── test_phase4.py
│   ├── test_phase5.py
│   └── __init__.py
├── tools/                 # Development and analysis tools
├── utils/                 # Shared utility functions
│   ├── validators.py      # Field validation functions (year, month, date, speaker name)
│   └── __init__.py (implicit)
├── UPDATE.py              # Database synchronization script (gc.db → core.52.db)
├── process_all.py         # Main pipeline runner (all talks)
├── process_topics.py      # Topic-filtered pipeline runner
├── run_phase2_tests.py    # Test runner for phase 2 validation
├── CLAUDE.md              # Project instructions and workflow rules
├── Pipfile                # pipenv dependency manifest
└── Pipfile.lock           # pipenv lock file
```

## Directory Purposes

**config/**
- Purpose: Configuration schemas and validation rules
- Contains: Field schema definitions (TALK_METADATA_SCHEMA, PARAGRAPH_CONFIG), type/requirement metadata
- Key files: `schemas.py` (centralized config-driven design)

**db/**
- Purpose: Database connections and SQL utilities
- Contains: SQLite wrapper (read-only mode, timeouts), query templates
- Key files: `__init__.py` (Database class, core_db/content_db instances), `core.52.db`, `content.52.db`

**docs/**
- Purpose: Full project documentation
- Contains: Pipeline specification, phase implementation plans, design philosophy
- Key files: `PROJECT.md` (architecture decisions), `PIPELINE_SPEC.md` (6-phase spec)

**extractors/**
- Purpose: Data extraction and transformation logic (core business logic)
- Contains: Per-phase extraction functions, shared HTML utilities, pipeline orchestrator
- Key files:
  - `phase1_talk_metadata.py` (layered: database → extraction → validation)
  - `phase2_paragraph_extraction.py` (HTML parsing, paragraph splitting)
  - `phase3_citation_extraction.py` (citation detection and parsing)
  - `phase4_footnote_extraction.py` (footnote extraction)
  - `pipeline.py` (orchestrator for phases 1–4, shared context building)
  - `html_parsing_utils.py` (BeautifulSoup helpers, context window extraction)

**models/**
- Purpose: Type-safe data structures for all extraction phases
- Contains: Typed dataclasses with validation, ChromaDB formatting methods
- Key files:
  - `talk_metadata.py` (TalkMetadata)
  - `paragraph_data.py` (ParagraphData, TalkParagraphs)
  - `citation_data.py` (CitationData, TalkCitations)
  - `footnote_data.py` (FootnoteData, TalkFootnotes)

**tests/**
- Purpose: Test suite for extraction logic
- Contains: Unit tests per phase, fixtures with known inputs/outputs
- Key files: `test_phase*.py` (one per phase), `test_html_parsing_utils.py`

**utils/**
- Purpose: Shared validation and helper functions
- Contains: Field validators (year, month, date_iso, speaker_name)
- Key files: `validators.py` (reusable validation functions)

## Key File Locations

**Entry Points:**
- `UPDATE.py`: Database synchronization script (gc.db → core.52.db)
- `process_all.py`: Main pipeline runner (processes all talks)
- `process_topics.py`: Topic-filtered processing

**Configuration:**
- `config/schemas.py`: Field schemas, type specs, validation rules
- `db/__init__.py`: Database class, connection pooling, timeout handling
- `CLAUDE.md`: Project workflow instructions and rules

**Core Logic:**
- `extractors/pipeline.py`: Orchestrator (phase 1–4 per talk, shared contexts)
- `extractors/phase1_talk_metadata.py`: Talk metadata extraction
- `extractors/phase2_paragraph_extraction.py`: Paragraph splitting (largest, ~55KB)
- `extractors/phase3_citation_extraction.py`: Scripture citation parsing
- `extractors/phase4_footnote_extraction.py`: Footnote extraction
- `extractors/html_parsing_utils.py`: Shared HTML utilities

**Data Models:**
- `models/talk_metadata.py`: Talk structure with validation
- `models/paragraph_data.py`: Paragraph with position tracking
- `models/citation_data.py`: Citation with parse metadata
- `models/footnote_data.py`: Footnote with position tracking

**Testing:**
- `tests/test_phase1.py` through `tests/test_phase5.py`: Phase-specific tests
- `tests/test_html_parsing_utils.py`: HTML parsing tests

## Naming Conventions

**Files:**
- `phase{N}_{purpose}.py`: Phase implementation modules (e.g., `phase2_paragraph_extraction.py`)
- `test_phase{N}.py`: Test files for each phase
- `*_data.py`: Data model/dataclass files (e.g., `citation_data.py`)
- `*_utils.py`: Shared utility modules (e.g., `html_parsing_utils.py`)

**Directories:**
- `phase-{N}-{name}/`: Phase documentation directories (e.g., `phase-3-citation/`)
- Lowercase with hyphens for directories, snake_case for files

**Dataclasses:**
- PascalCase for dataclass names: `TalkMetadata`, `ParagraphData`, `CitationData`, `FootnoteData`
- Plural container classes: `TalkParagraphs`, `TalkCitations`, `TalkFootnotes`
- `Result` suffix for pipeline outputs: `TalkPipelineResult`

**Functions:**
- snake_case for all functions: `fetch_talk_by_id()`, `extract_talk_metadata()`, `process_talk_paragraphs()`
- `fetch_*` for database queries
- `extract_*` for transformation/parsing
- `process_*` for orchestration

**Database IDs:**
- Format: `{resource}_{id}` for ChromaDB document IDs
  - `talk_{talk_id}` (e.g., `talk_8820`)
  - `para_{paragraph_id}` (e.g., `para_156789`)
  - `cite_{citation_id}_{paragraph_id}` (e.g., `cite_45123_156789`)
  - `fn_{footnote_id}` (e.g., `fn_78945`)

## Where to Add New Code

**New Extraction Phase (e.g., Phase 7):**
- Implementation: `extractors/phase7_*.py` (follow layered pattern: database → extraction → validation layers)
- Data model: `models/{resource}_data.py` with dataclass(es)
- Tests: `tests/test_phase7.py`
- Integration: Add import to `extractors/pipeline.py`, add orchestration function call
- Documentation: `docs/pipeline/phase-7-{name}/` with PLAN and IMPLEMENTATION files
- Config: Add schema definition to `config/schemas.py` if new field types needed

**New Validation Rule:**
- Field validator: Add function to `utils/validators.py` (e.g., `validate_isbn()`)
- Schema: Register in `config/schemas.py` under appropriate SCHEMA dict
- Dataclass: Add validation call in model `__post_init__()` method

**New Utility Function:**
- HTML parsing: Add to `extractors/html_parsing_utils.py`
- Validation: Add to `utils/validators.py`
- Database query: Add to appropriate phase module (or new `utils/queries.py`)

**New Test:**
- Location: `tests/test_{module_name}.py`
- Pattern: Use fixtures in docstrings, test normal + edge cases (missing fields, malformed data, empty results)
- Run: `pipenv run py -m pytest tests/test_*.py`

## Special Directories

**db/**
- Purpose: SQLite database storage
- Generated: No (databases come from external source)
- Committed: Yes, but .gitignore may exclude large databases
- Note: core.52.db and content.52.db are read-only via Database class

**output/**
- Purpose: Generated artifacts (ChromaDB collections, JSON exports, verification reports)
- Generated: Yes (created by process_all.py and phase 6)
- Committed: No (gitignored)

**docs/pipeline/**
- Purpose: Phase implementation documentation
- Generated: No (handwritten plans and implementation summaries)
- Committed: Yes
- Structure: One subdirectory per phase with PLAN, README, and implementation summary files

**tasks/**
- Purpose: Workflow tracking
- Generated: Yes (updated during execution)
- Committed: Yes
- Contents: `todo.md` (current tasks), `lessons.md` (pattern learning log)

---

*Structure analysis: 2026-03-18*
