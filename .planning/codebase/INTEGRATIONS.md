# External Integrations

**Analysis Date:** 2026-03-18

## APIs & External Services

**HTTP Requests (Optional):**
- General purpose - fetch external resources, fallback for data not in SQLite
  - SDK/Client: `requests` 2.32.5
  - Caching: Handled via `requests-cache` CachedSession with SQLite backend
  - Location: `cache_manager_CLAUDE.py` provides CLI to inspect cached responses

**LDS General Conference Content:**
- No external API integration; all talks sourced from local SQLite databases
- Data is pre-fetched and stored in `content.52.db` and `core.52.db`

## Data Storage

**Databases:**
- SQLite (local filesystem)
  - Primary: `db/core.52.db` - Talk metadata, speaker info, conference data, citations (7,659 talks)
  - Content: `db/content.52.db` - Raw HTML talk content
  - Archive: `db/gc.db` - General Conference reference data (deprecated)
  - Archive: `db/topic.db` - Topic index (not actively used in pipeline)
  - Client: sqlite3 (Python stdlib, read-only mode by default)
  - Connection: `db/__init__.py` defines `Database` class with timeout handling (5s default)

**Query Pattern:**
- SQL-first approach: `Database.select()`, `Database.select_one()`, `Database.scalar()` for reads
- Connection pooling: Per-query connection (no persistent pool)
- Read-only mode enforced for production safety

**File Storage:**
- No cloud storage integration
- Local filesystem only: SQLite files, cache files, logs
- HTTP cache: `http_cache.sqlite` stored in project root (requests-cache backend)

**Caching:**
- requests-cache with SQLite backend (`http_cache.sqlite`)
- Not required for core pipeline (optional HTTP caching only)
- Size: ~160 MB in current codebase
- Management: CLI tool at `cache_manager_CLAUDE.py` for inspection/cleanup

## Authentication & Identity

**Auth Provider:**
- None required - all databases are local files
- No API authentication (no external APIs called in core pipeline)

**Database Access:**
- Read-only by default for data integrity
- No authentication layer; file-system based access control

## Monitoring & Observability

**Error Tracking:**
- Custom logging via Python `logging` module (configured per module)
- No external error tracking service (Sentry, DataDog, etc.)
- Logs directed to: `stdout` via handlers configured in extractors

**Logs:**
- Approach: Python `logging` with ISO format timestamps
- Log levels: INFO, WARNING, ERROR, DEBUG
- Format: `"%(asctime)s - %(name)s - %(levelname)s - %(message)s"`
- Location: Console output (can be redirected or captured)
- Examples: `extractors/phase1_talk_metadata.py` line 28-31

## CI/CD & Deployment

**Hosting:**
- No hosting platform dependency
- Designed for local batch processing (single machine)
- Can be run on any machine with Python 3 and pipenv

**CI Pipeline:**
- None detected
- Tests are run manually via `pipenv run py -m pytest`
- No GitHub Actions, Jenkins, or cloud CI

## Environment Configuration

**Required env vars:**
- `SCI_FORCE_TIMEOUT` (optional, boolean "1") - Force query timeouts in database
- No API keys, credentials, or secrets required for core pipeline
- All configuration hardcoded in source files

**Secrets location:**
- No secrets management system (no .env file, no vault)
- Databases accessed via hardcoded paths in `db/__init__.py`
- CRITICAL: Keep database files secure (contain talk content)

## Webhooks & Callbacks

**Incoming:**
- None (batch processing only, no web server)

**Outgoing:**
- None (data flows to ChromaDB for search indexing, not a webhook pattern)
- ChromaDB integration commented in examples (not yet implemented at pipeline level)

## Data Integration Points

**ChromaDB (Planned):**
- Vector database for semantic search across talks
- Target collections (from `PIPELINE_SPEC.md`):
  - `conference_talks` - Talk-level summaries
  - `conference_talk_paragraphs` - Paragraph content
  - `conference_talk_citations` - Scripture references with context
  - `conference_talk_footnotes` - External references (talks, books, hymns)
- Status: Examples show integration patterns but not yet wired into main pipeline
- Location: `examples/phase1_example.py` shows `chromadb.Client()` usage

**Database Export Points:**
- Currently: In-memory data structures during pipeline processing
- Target: ChromaDB batch insertion via `documents`, `metadatas`, `ids` lists
- Pattern: `to_chromadb_format()` methods on dataclasses return (document_text, metadata_dict, id_string)

---

*Integration audit: 2026-03-18*
