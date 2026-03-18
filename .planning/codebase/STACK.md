# Technology Stack

**Analysis Date:** 2026-03-18

## Languages

**Primary:**
- Python 3.x - Core extraction pipeline, database operations, and data processing

## Runtime

**Environment:**
- Python 3+ (no specific version pinned, requires pipenv)

**Package Manager:**
- pipenv - Virtual environment and dependency management
- Lockfile: `Pipfile.lock` present and locked

## Frameworks

**Core:**
- BeautifulSoup4 4.14.2 - HTML parsing for scripture talk content extraction
- Requests 2.32.5 - HTTP client for fetching resources (optional, for external content)
- Requests-Cache 1.2.1 - HTTP response caching with SQLite backend, configured via `CachedSession`

**Testing:**
- pytest 9.0.2 - Test runner and assertion library

**Build/Dev:**
- None explicitly configured; uses pipenv for dependency isolation

## Key Dependencies

**Critical:**
- BeautifulSoup4 - Parses raw HTML from SQLite database containing General Conference talks
- Requests - Handles HTTP operations (not required for core pipeline, fallback for external fetches)
- Requests-Cache - Caches HTTP responses in SQLite (`http_cache.sqlite`), prevents redundant API calls

**Data/Serialization:**
- cattrs 25.3.0 - Type conversion and object serialization (dataclass support)
- typing-extensions 4.15.0 - Extended type hints for Python 3.9+

**Infrastructure:**
- sqlite3 (stdlib) - Primary data source: `core.52.db`, `content.52.db`
- url-normalize 2.2.1 - URL normalization for canonical storage

**Supporting:**
- certifi 2025.11.12 - SSL certificate bundle for HTTPS
- charset-normalizer 3.4.4 - Character encoding detection
- urllib3 2.6.0 - HTTP library (dependency of requests)
- attrs 25.4.0 - Class decorator support (dataclass compatibility)
- exceptiongroup 1.3.1 - Exception group handling (Python 3.9+)
- idna 3.11 - Internationalized domain name support
- platformdirs 4.5.1 - Platform-specific directory paths
- soupsieve 2.8 - CSS selector library for BeautifulSoup

## Configuration

**Environment:**
- Single env var supported: `SCI_FORCE_TIMEOUT` (boolean "1" to force query timeouts)
- Database timeout default: 5 seconds (configurable per `Database` class)

**Build:**
- No build config files present (Python, no compilation)
- Entry points are direct script execution: `pipenv run py script.py`

**Data Configuration:**
- Database paths hardcoded in `db/__init__.py`:
  - `CORE_DB_PATH`: `db/core.52.db` (7,659 talks metadata)
  - `CONTENT_DB_PATH`: `db/content.52.db` (talk HTML content)
- Cache location: `http_cache.sqlite` in project root (managed by requests-cache)

## Platform Requirements

**Development:**
- Python 3+ (no pinned version)
- pipenv for dependency management
- SQLite3 support (built-in to Python)
- Filesystem write access (for caching and logs)

**Production:**
- Python 3+ runtime
- SQLite3 databases accessible at `db/` paths
- ~530 MB storage for `content.52.db` (talk HTML)
- ~50 MB storage for `core.52.db` (metadata)
- ~160 MB for `http_cache.sqlite` (if using request caching)

---

*Stack analysis: 2026-03-18*
