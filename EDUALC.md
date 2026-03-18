# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **LDS Scripture Citation Index** system that processes General Conference talks and topic data from Church APIs, extracting scripture citations and metadata to build searchable SQLite databases. The project serves as a **Media Control Plugin (MCP)** for Claude, enabling intelligent search and navigation of LDS scripture, talks, speakers, and topical content.

**Core Mission**: Extract, process, and index General Conference talks, their scripture citations, topic relationships, and conference session organization.

## Development Setup

Install dependencies using pipenv:

```bash
pipenv install
pipenv shell
```

Dependencies: `requests>=2.31.0`, `beautifulsoup4>=4.12.0`, `requests-cache`

## Common Commands

### Process Topics and Entries (Two-Phase)

Main processing workflow that fetches topics from API, extracts entries, then processes each entry concurrently:

```bash
# Process all topics (default 15 concurrent workers)
pipenv run python process_all.py

# Process specific topic
pipenv run python process_entries.py --topic "Priesthood"

# Custom settings
pipenv run python process_entries.py --topic "Faith" --workers 20 --output faith_data.json
```

**Options**:
- `--topic, -t`: Specific topic name (case-insensitive)
- `--workers, -w`: Number of concurrent threads (default: 15)
- `--input, -i`: Input file path
- `--output, -o`: Output file path
- `--errors, -e`: Error log file path

### Build SQLite Database

```bash
# Build from processed results
pipenv run python scripts/build_database.py

# Custom files
pipenv run python scripts/build_database.py --input data_aids.json --output content.db

# Recreate database (drop existing tables)
pipenv run python scripts/build_database.py --recreate
```

### Database Queries

```bash
# Open database
sqlite3 db/core.52.db

# Example: Find talks citing Moroni 7:47
SELECT t.ID, t.Title, s.LastNames
FROM citation c
JOIN talk t ON c.TalkID = t.ID
JOIN speaker s ON t.SpeakerID = s.ID
WHERE c.BookID = 219 AND c.Chapter = 7 AND c.MinVerse <= 47 AND c.MaxVerse >= 47;
```

See `db/sql-queries.md` for comprehensive query examples and URL encoding patterns.

### HTTP Cache Management

```bash
# View cache info and statistics
python cache_manager_CLAUDE.py info

# List cached URLs
python cache_manager_CLAUDE.py list 20

# Search cache by pattern
python cache_manager_CLAUDE.py search "conference"

# Export cache summary
python cache_manager_CLAUDE.py export cache_summary.json

# Clean old entries (older than N days)
python cache_manager_CLAUDE.py older 30
```

Cache file: `http_cache.sqlite` (~155MB, persistent with NEVER_EXPIRE policy)

## Architecture

### High-Level Data Flow

```
topics.json (input)
    ↓
[Phase 1: Topic Processing]
    - Fetch topic data from Church API
    - Extract entries from collection sections
    - Output: results.json
    ↓
[Phase 2: Entry Processing - Multi-threaded]
    - Concurrent API requests (ThreadPoolExecutor)
    - Extract data-aid from HTML (h1 tags or page attributes)
    - Extract speaker/role information
    - Output: data_aids.json, errors.json
    ↓
[Phase 3: Database Population]
    - Populate conference_topic and talk_topic tables
    - Generate URI variants (URI_L, URI_GC)
    - Create indexes for fast queries
    ↓
SQLite Databases (core.52.db, content.52.db)
```

### Dual Database Approach

**`db/core.52.db`** (~50MB) - Scripture metadata and citations
- Book, scripture, citation, talk, speaker tables
- Conference sessions and metadata
- Journal of Discourses topical index (jdtopic, jdcite, jdalso)
- Topic linking tables (conference_topic, talk_topic)

**`db/content.52.db`** (~525MB) - Full talk text
- talkbody table with DEFLATE-compressed text (4-byte length prefix)
- Enables full-text search without bloating core database

### Database Layer (`db/__init__.py`)

Provides abstraction classes for database access:

```python
from db import core_db, content_db

# Read-only queries with timeout protection
results = core_db.select(query, params)
row = core_db.select_one(query, params)
value = core_db.scalar(query, params)
```

**Global instances**: `core_db`, `content_db` for direct queries
**Path constants**: `CORE_DB_PATH`, `CONTENT_DB_PATH`

### Multi-Threaded Processing Design

Entry processing uses `ThreadPoolExecutor` with configurable concurrency:

- **MAX_WORKERS=15** (default): Balance between speed and API rate limits
- **Thread-safe**: Lock-protected print statements and shared data structures
- **Error tracking**: Per-thread error collection with topic/index/uri details
- **Progress reporting**: Real-time statistics on successes/failures

## Key Directories

### `/api/`
Church API interaction layer. Queries endpoints, parses JSON/HTML responses, extracts structured data.

**Key file**: `extract_conference_sections.py` - Extract structured conference data

### `/db/`
Database layer with schema management and query abstractions.

**Structure**:
- `core.52.db` - Main scripture/citation/speaker database
- `content.52.db` - Full talk text (compressed)
- `sql-queries.md` - Comprehensive SQL documentation (1645 lines) with URL encoding formulas
- `one-off-migration/` - Database population scripts (backfill_topics.py, backfill_talk_uri.py, etc.)

### `/process_topic_talks/`
Talk metadata extraction and topic mapping workflows.

**Key files**:
- `fetch_talk_topics_h1.py` / `fetch_talk_topics_pg.py` - Extract topics via h1[data-aid] or page attributes
- `extract_talk_metadata.py` - Backfill talk metadata (title, data-aid, speaker role)
- `process_talkbody.py` - Decompress DEFLATE-compressed talk text
- `process_entries.py` - Multi-threaded entry processor
- `metadata/` - JSON results from extraction runs

### `/scripts/`
Database utilities and URI processing.

**Key files**:
- `build_database.py` - Build SQLite from JSON, create indexes
- `generate_uri_variants.py` - Generate URI_L (literal) and URI_GC (General Conference normalized)
- `db_schema_extractor.py` - Display schema information

### `/tools/`
Text processing utilities.

**Key file**: `text_processing.py`
- `find_all_occurrences()` - Case-insensitive pattern matching
- `build_windows()` - Create context windows around matches with overlap merging
- `format_speaker_name()` - Standardize speaker names

## Critical Patterns & Conventions

### URI Normalization

Two URI variants generated by `scripts/generate_uri_variants.py`:

**URI_L (Literal)**: Keeps session paths intact, minimal processing

**URI_GC (General Conference)**: Normalized for consistent API access
- Normalize month: Jan→Oct(prev year), Feb-Jul→Apr, Aug-Dec→Oct
- Extract identifier from last path component
- Format: `/general-conference/{year}/{month}/{identifier}`

### Data-Aid Extraction

Two methods for extracting unique content identifiers:

1. **h1 element**: `soup.find("h1", {"data-aid": True})["data-aid"]`
2. **Page attributes**: `json_data["content"]["meta"]["pageAttributes"]["data-aid"]`

Fallback between methods when one fails.

### Talk Text Decompression

`content.52.db` stores compressed talk text with custom format:

```python
# Decompress from talkbody.Text column
import zlib
length_prefix = data[:4]  # First 4 bytes = length
compressed = data[4:]     # Remaining bytes = DEFLATE data
text = zlib.decompress(compressed, -zlib.MAX_WBITS)  # Raw DEFLATE, no zlib wrapper
```

See `process_topic_talks/process_talkbody.py` for implementation.

### URL Encoding Scheme

Scripture Citation Index uses hexadecimal encoding for URLs (documented in `db/sql-queries.md`):

**Patterns**:
- Book view: `#{bookID_hex}::`
- Chapter view: `#{bookID_hex}{chapter_decimal}::`
- Citation for verse: `#{scriptureBookID_hex}{scriptureChapter_hex}::c{citationBookID_hex}{citationChapter_decimal}{verse_decimal}`
- Talk view: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:c{citationRef}`

**Examples**:
- Genesis (ID 101 = 0x65): `#065::`
- Moroni Ch 10 (ID 219 = 0xDB, Ch 10): `#0db0a::`
- Talks citing Moroni 7:47: `#0db0a::c0db0747`

### Idempotent Migrations

Database population scripts use `ON CONFLICT DO NOTHING` for safe re-runs:

```sql
INSERT INTO conference_topic (name, slug)
VALUES (?, ?)
ON CONFLICT(slug) DO NOTHING
```

Allows running migrations multiple times without errors or duplicate data.

### HTTP Caching Strategy

Uses `requests-cache` with SQLite backend (`http_cache.sqlite`):

- **Expiration**: NEVER_EXPIRE (persistent cache)
- **Purpose**: Reduce API load during development/testing
- **Management**: `cache_manager_CLAUDE.py` CLI for inspection and cleanup

## Database Schema Highlights

### Core Tables

**book** - Scripture book metadata
Fields: ID, ParentBookID, Abbr, FullName, NumChapters, CitationCount
Hierarchies: Testament (1-5) → Books → Chapters

**scripture** - Verse text
Fields: BookID, Chapter, Verse, Flag (S=KJV, F=JST footnoted, J=JST only), Text

**citation** - Talk citations to scripture
Fields: TalkID, BookID, Chapter, Verses, MinVerse, MaxVerse
Links talks to specific scripture references

**talk** - Talk metadata
Fields: ID, Title, Date, Corpus, SpeakerID, URL, URI_L, URI_GC, URI_Success

**speaker** - Speaker information
Fields: ID, GivenNames, LastNames, Abbr, Info

**conference_talk** - Conference session linking
Fields: TalkID, SessionID, StartPageNum, EndPageNum

**conf_session** - Conference session details
Fields: ID, Description, Abbr, Date, Sequence, ConferenceID

**conference** - Conference metadata
Fields: ID, Description, Year, Annual (A/S for April/October)

### Journal of Discourses Tables

**jdtopic** - Topical index (hierarchical, 46,191 entries)
Fields: ID, ParentID, TopicText, TargetID, TargetType (X/C/A)
Organized alphabetically by letter

**jdcite** - JD topic citations
Fields: JdtopicID, SpeakerID, Pages, TargetVolume, TargetPage, TargetDiscourse

**jdalso** - Cross-reference "see also" links
Fields: ID, AlsoText, JdtopicID, TargetJdtopicID

### Topic Linking Tables

**conference_topic** - Topic metadata
Fields: topic_id (PK), name, slug (UNIQUE)

**talk_topic** - Topic-to-talk relationships
Fields: id (PK), topic_id (FK), talk_id (FK), content_identifier (data-aid)

## Configuration

### API Endpoints

```python
# Topic API
BASE_URL_TOPICS = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri=/general-conference/topics"

# Entry/Talk API
BASE_URL_ENTRIES = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri="

# Fallback API
BASE_URL_FALLBACK = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/content?lang=eng&uri="
```

### Performance Settings

```python
MAX_WORKERS = 15          # Concurrent threads for entry processing
WORKER_COUNT = 1-2        # Conservative for metadata extraction
REQUEST_TIMEOUT = 30      # Seconds per request
CACHE_EXPIRATION = NEVER  # Persistent HTTP cache
```

Adjust `MAX_WORKERS` based on API rate limits:
- Lower (5-10): More conservative, better for rate-limited APIs
- Higher (15-20): Faster processing if API can handle it
- Very high (20+): Only if API has no rate limits

## Input/Output Formats

### topics.json (input)
```json
[
  {"title": "Topic Name", "uri": "/path/to/topic"}
]
```

### results.json (intermediate - from Phase 1)
```json
[
  {
    "topic": "Topic Name",
    "entries": [
      {"uri": "/path/to/entry", "title": "Entry Title", ...}
    ]
  }
]
```

### data_aids.json (output - from Phase 2)
```json
[
  {
    "topic": "Topic Name",
    "data_aids": ["aid1", "aid2", "aid3"],
    "total_entries": 50,
    "successful_extractions": 48,
    "failed_extractions": 2,
    "all_results": [...],
    "errors": [...]
  }
]
```

### errors.json (error log)
```json
[
  {
    "topic": "Topic Name",
    "index": 5,
    "uri": "/path/to/entry",
    "title": "Entry Title",
    "error": "Detailed error message"
  }
]
```
- Do not open database files directly, instead use @scripts\db_schema_extractor.py with specific arguments.
- Ignore @process_topic_talks\ as it's no longer relevant.