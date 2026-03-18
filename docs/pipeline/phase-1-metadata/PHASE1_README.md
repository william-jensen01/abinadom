# Phase 1: Talk Metadata Extraction

## Overview

Phase 1 extracts talk-level metadata from the SQLite database and prepares it for ChromaDB insertion. This establishes the foundational patterns and architecture that all subsequent phases (2-15) will follow.

## Architecture

### Layered Design

```
┌─────────────────────────────────────┐
│     High-Level Pipeline             │
│  extract_talks_for_chromadb()       │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
┌──────▼──────┐ ┌─────▼──────┐
│  Validation │ │  ChromaDB  │
│    Layer    │ │   Prep     │
└──────▲──────┘ └─────▲──────┘
       │               │
┌──────┴───────────────┴──────┐
│      Extraction Layer        │
│  transform_db_row_to_metadata│
└──────────────▲───────────────┘
               │
┌──────────────┴───────────────┐
│      Database Layer          │
│  fetch_all_talks()           │
│  build_talk_metadata_query() │
└──────────────────────────────┘
```

### Key Components

1. **Database Layer** (`extractors/phase1_talk_metadata.py`)
   - Pure SQL queries
   - Database connection management
   - Raw data retrieval

2. **Extraction Layer**
   - Data transformation
   - Type conversion
   - Computed fields (e.g., speaker_name from GivenNames + LastNames)

3. **Validation Layer**
   - Schema validation
   - Field validation
   - Data quality checks

4. **Models** (`models/talk_metadata.py`)
   - Type-safe dataclass representation
   - Automatic validation in `__post_init__`
   - ChromaDB format conversion

5. **Configuration** (`config/schemas.py`)
   - Schema definitions
   - Required vs. optional fields
   - Validation rules

6. **Utilities** (`utils/validators.py`)
   - Reusable validation functions
   - Field sanitization
   - Type coercion

## Installation

No additional dependencies required beyond the existing project setup:

```bash
pipenv install
pipenv shell
```

## Usage

### Command-Line Interface

Extract all talks:
```bash
python extractors/phase1_talk_metadata.py
```

Extract limited number of talks:
```bash
python extractors/phase1_talk_metadata.py --limit 100
```

Show statistics only (no extraction):
```bash
python extractors/phase1_talk_metadata.py --stats --limit 10
```

Skip validation checks:
```bash
python extractors/phase1_talk_metadata.py --no-validate
```

### Programmatic Usage

```python
from extractors.phase1_talk_metadata import extract_talks_for_chromadb

# Extract all talks in ChromaDB format
documents, metadatas, ids = extract_talks_for_chromadb()

# With limit
documents, metadatas, ids = extract_talks_for_chromadb(limit=100)

# Without validation
documents, metadatas, ids = extract_talks_for_chromadb(
    limit=100,
    validate=False
)

# Insert into ChromaDB (example)
# collection.add(
#     documents=documents,
#     metadatas=metadatas,
#     ids=ids
# )
```

### Extract Specific Talks

```python
from db import core_db
from extractors.phase1_talk_metadata import (
    fetch_talk_by_id,
    extract_talk_metadata
)

# Get single talk
row = fetch_talk_by_id(core_db, talk_id=8769)
if row:
    metadata = extract_talk_metadata(row)
    print(metadata)
```

## Database Schema

Phase 1 joins the following tables:

- **talk**: Core talk metadata (ID, Title, Date, URLs, etc.)
- **speaker**: Speaker information (GivenNames, LastNames, etc.)
- **conference**: Conference metadata (Year, Description, Annual flag)
- **conf_session**: Session details (Description, Date, Sequence)
- **conference_talk**: Links talks to sessions (Sequence, PageNum)

### Query Structure

```sql
SELECT
    t.ID as talk_id,
    t.Title,
    s.GivenNames,
    s.LastNames,
    c.Year as conference_year,
    c.Annual as conference_annual,
    cs.Description as session_description,
    ...
FROM talk t
INNER JOIN speaker s ON t.SpeakerID = s.ID
INNER JOIN conference_talk ct ON t.ID = ct.TalkID
INNER JOIN conf_session cs ON ct.SessionID = cs.ID
INNER JOIN conference c ON cs.ConferenceID = c.ID
```

## Output Format

### ChromaDB Format

Three parallel lists ready for ChromaDB insertion:

**documents** (List[str]): Text summaries for embedding
```
"Title: As a Little Child
Speaker: Jeffrey R. Holland
Conference: 2025 Annual General Conference
Session: Saturday Morning Session, 5 Apr 2025
Date: 2025-04-05"
```

**metadatas** (List[Dict]): Full metadata dictionaries
```python
{
    'talk_id': 8769,
    'speaker_id': 1125,
    'conference_id': 167,
    'title': 'As a Little Child',
    'speaker_name': 'Jeffrey R. Holland',
    'conference_year': 2025,
    'conference_month': 'April',
    'conference_description': '2025 Annual General Conference',
    'session_description': 'Saturday Morning Session, 5 Apr 2025',
    'url': '/general-conference/2025/04/12holland',
    'data_aid': '12holland',
    # ... 25+ additional fields
}
```

**ids** (List[str]): Unique identifiers
```
"talk_8769"
```

## Metadata Schema

### Required Fields

- `talk_id` (int): Unique talk identifier
- `speaker_id` (int): Speaker identifier
- `conference_id` (int): Conference identifier
- `title` (str): Talk title
- `speaker_name` (str): Full speaker name (computed)
- `conference_year` (int): Conference year (YYYY)
- `conference_month` (str): 'April' or 'October'
- `conference_description` (str): Full conference description
- `talk_date` (str): ISO format date (YYYY-MM-DD)
- `extraction_timestamp` (str): ISO timestamp of extraction
- `extraction_version` (str): Pipeline version (1.0.0)

### Optional Fields

Session information:
- `session_id`, `session_description`, `session_abbr`, `session_date`, `session_sequence`, `talk_sequence`

URLs and identifiers:
- `url`, `uri_l`, `uri_gc`, `data_aid`

Media URLs:
- `audio_url`, `video_low_url`, `video_med_url`, `video_high_url`

Other:
- `corpus`, `speaker_role_id`, `start_page_num`, `end_page_num`

## Validation

### Automatic Validation

TalkMetadata dataclass validates on creation:
```python
# Raises ValueError if invalid
metadata = TalkMetadata(
    talk_id=-1,  # ❌ Must be positive
    conference_month='January',  # ❌ Must be April or October
    # ...
)
```

### Schema Validation

Validate against schema definition:
```python
metadata = TalkMetadata(...)
is_valid, errors = metadata.validate_against_schema()
if not is_valid:
    print(f"Validation errors: {errors}")
```

### Pipeline Validation

Automatic validation in extraction pipeline:
```python
# Validation runs by default
documents, metadatas, ids = extract_talks_for_chromadb(validate=True)

# Skip validation for performance
documents, metadatas, ids = extract_talks_for_chromadb(validate=False)
```

## Testing

Run all unit tests:
```bash
python tests/test_phase1.py
```

Test coverage:
- ✅ Schema validation
- ✅ Field validators
- ✅ TalkMetadata dataclass
- ✅ Database transformations
- ✅ ChromaDB format conversion
- ✅ Edge cases (empty fields, NULL values)

## Performance

Typical extraction performance:

- **Small dataset** (100 talks): ~0.1 seconds
- **Medium dataset** (1,000 talks): ~1 second
- **Full dataset** (7,659 talks): ~8 seconds

Database queries use indexes on:
- `talk.ID` (PRIMARY KEY)
- `talk.SpeakerID` (FOREIGN KEY)
- `conference_talk.TalkID` (PRIMARY KEY)
- `conf_session.ID` (PRIMARY KEY)
- `conference.ID` (PRIMARY KEY)

## Design Principles Applied

### 1. Layered Architecture ✅
Separation of database, extraction, and validation layers

### 2. Configuration-Driven ✅
Schema defined in `config/schemas.py`, not hardcoded

### 3. Pure Functions ✅
No side effects in extraction functions

### 4. Type Safety ✅
Dataclasses with type hints throughout

### 5. Defensive Programming ✅
- Required fields: Fail-fast (raise exceptions)
- Optional fields: Fail-safe (use None, log warnings)
- Validation at boundaries

### 6. Structured Logging ✅
Context-rich logging with talk_id, phase, etc.

### 7. Test Coverage ✅
30 unit tests covering normal and error cases

### 8. Idempotent ✅
Can run multiple times safely, uses existing IDs

### 9. Pattern Consistency ✅
Patterns established for future phases

### 10. Clear Documentation ✅
Docstrings, type hints, inline comments

## Next Steps

Phase 1 provides the foundation for subsequent phases:

- **Phase 2**: Paragraph segmentation (follow same patterns)
- **Phase 3-7**: Citation detection and parsing
- **Phase 8-10**: Footnote extraction and parsing
- **Phase 11-12**: Metadata enrichment
- **Phase 13-15**: ChromaDB insertion and verification

Each phase should follow the same architectural patterns established here:
- Layered architecture
- Configuration-driven schemas
- Type-safe dataclasses
- Pure functions
- Defensive programming
- Comprehensive testing

## Troubleshooting

### Database Not Found

```
FileNotFoundError: Database not found: db/core.52.db
```

**Solution**: Ensure you're running from project root directory

### Validation Errors

```
ValueError: Validation failed: [...]
```

**Solution**: Check error messages for specific field issues, or skip validation with `--no-validate`

### Import Errors

```
ModuleNotFoundError: No module named 'config'
```

**Solution**: Ensure you're running from project root, or check Python path

## Examples

### Extract Sample for Development

```bash
# Extract 10 talks for testing
python extractors/phase1_talk_metadata.py --limit 10
```

### Get Extraction Statistics

```bash
# See what's in the database
python extractors/phase1_talk_metadata.py --stats --limit 100
```

Output:
```
=== Extraction Statistics ===
total_talks: 100
conferences: 10
speakers: 85
year_range: (2020, 2025)
with_session: 100
with_url: 100
with_audio: 95
with_video: 90
```

### Programmatic Integration

```python
from extractors.phase1_talk_metadata import extract_talks_for_chromadb
import chromadb

# Extract data
documents, metadatas, ids = extract_talks_for_chromadb(limit=100)

# Insert into ChromaDB
client = chromadb.Client()
collection = client.create_collection("conference_talks")
collection.add(
    documents=documents,
    metadatas=metadatas,
    ids=ids
)

# Query
results = collection.query(
    query_texts=["faith and prayer"],
    n_results=5
)
```

## File Structure

```
LDS MCP/
├── config/
│   └── schemas.py              # Schema definitions
├── extractors/
│   └── phase1_talk_metadata.py # Main extraction logic
├── models/
│   └── talk_metadata.py        # TalkMetadata dataclass
├── tests/
│   └── test_phase1.py          # Unit tests
├── utils/
│   └── validators.py           # Validation functions
└── PHASE1_README.md            # This file
```

## Version History

- **1.0.0** (2025-12-15): Initial Phase 1 implementation
  - Complete extraction pipeline
  - 30 passing unit tests
  - Full schema validation
  - ChromaDB format support

## Contact

For questions or issues with Phase 1 extraction, check:
1. Unit tests for examples
2. Docstrings in source code
3. This README for common patterns
