# Phase 1: DB Enrichment - Research

**Researched:** 2026-03-19
**Domain:** SQLite schema migration, backfill scripts, Phase 1 extractor modification
**Confidence:** HIGH

## Summary

Phase 1 restructures metadata storage by creating a dedicated `talk_metadata` table (1:1 with `talks`, GC entries only) and migrating all existing backfill scripts to write there instead of directly to the `talks` table. The current state has enrichment data scattered across `talks` columns (`URI_L`, `URI_GC`, `data_aid`, `speaker_role_id`, `Kicker`) that were added via `ALTER TABLE` by individual backfill scripts. The new `talk_metadata` table centralizes these fields plus `talk_preview`.

The codebase has 6 backfill scripts in `db/one-off-migration/`, of which 4 write to the `talks` table directly (`backfill_talk_metadata.py`, `backfill_talk_kicker.py`, `backfill_talk_uri.py`, `backfill_talk_metadata_role_extraction.py`). One writes to `content.52.db` (`backfill_talk_texts.py`) and one writes to `conference_topic`/`talk_topic` tables (`backfill_topics.py`). The preview backfill currently writes to `content.52.db talkbody.TextPreview` and only has 34 entries -- the Church API fetcher needs to be completed to cover all ~7,659 GC talks. The existing `api/extract_conference_sections.py` fetches session data from the Church API and can serve as the pattern for the preview fetcher.

**Primary recommendation:** Create `talk_metadata` table with DDL, migrate the 4 talk-targeting backfill scripts to INSERT/UPDATE `talk_metadata` instead of `talks`, build the preview fetcher using the existing Church API pattern, then update Phase 1's SQL query to LEFT JOIN `talk_metadata`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ENRCH-01 | `talk_metadata` table created (1:1 with `talks`, GC entries only) with columns: `speaker_role`, `uri_l`, `uri_gc`, `kicker`, `talk_preview`, `data_aid` | DDL pattern documented below; current columns found on `talks` table confirm field names and types |
| ENRCH-02 | All existing backfill scripts in `db/one-off-migration/` updated to write to `talk_metadata` instead of `talks` columns | 4 scripts identified that write to `talks`: `backfill_talk_metadata.py`, `backfill_talk_kicker.py`, `backfill_talk_uri.py`, `backfill_talk_metadata_role_extraction.py` |
| ENRCH-03 | Talk preview collection script completed: fetches all GC previews from Church API, saves to `talk_previews.json` | Church API pattern exists in `api/extract_conference_sections.py`; current `talk_previews.json` has only 34 entries |
| ENRCH-04 | All backfill scripts re-run to populate `talk_metadata` with current data | Depends on ENRCH-01 and ENRCH-02 completion |
| ENRCH-05 | Phase 1 metadata extractor updated to JOIN `talks + talk_metadata` and expose enriched fields downstream | Current query in `extractors/phase1_talk_metadata.py` reads `URI_L`, `URI_GC`, `data_aid`, `speaker_role_id` directly from `talks`; needs LEFT JOIN to `talk_metadata` |
| ENRCH-06 | `talk_topic` and `conference_topic` tables remain unchanged | `backfill_topics.py` writes to these tables, not `talks` -- no changes needed |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlite3 | stdlib | Database operations | Already used throughout; `db/__init__.py` Database class wraps it |
| beautifulsoup4 | (existing) | HTML parsing for kicker/role extraction | Already a project dependency used by backfill scripts |
| requests | (existing) | HTTP calls to Church API | Already used by `api/extract_conference_sections.py` |
| requests_cache | (existing) | Cache HTTP responses | Already used by `api/extract_conference_sections.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json | stdlib | JSON file I/O for metadata/previews | Already used throughout |
| argparse | stdlib | CLI argument parsing | Already used by all backfill scripts |

No new dependencies are needed for this phase.

## Architecture Patterns

### Current Database Layout (Before)
```
core.52.db
  talk table:
    ID, Corpus, URL, Title, Date, SpeakerID,
    AudioUrl, VideoLowUrl, VideoMedUrl, VideoHighUrl,
    URI_L, URI_GC, data_aid, speaker_role_id, Kicker    <-- enrichment columns mixed in

  speaker_role table:
    id, role, slug                                       <-- already exists, 110 rows

  conference_topic table:                                <-- DO NOT TOUCH
  talk_topic table:                                      <-- DO NOT TOUCH

content.52.db
  talkbody table:
    TalkID, Text, TextRaw, TextSimple, TextMinimal,
    TextEnhanced, TextPreview                            <-- preview currently here
```

### Target Database Layout (After)
```
core.52.db
  talk table:
    ID, Corpus, URL, Title, Date, SpeakerID,
    AudioUrl, VideoLowUrl, VideoMedUrl, VideoHighUrl,
    URI_L, URI_GC, data_aid, speaker_role_id, Kicker    <-- columns remain for now
                                                         (dropping them is out of scope
                                                          to avoid breaking other code)

  talk_metadata table (NEW):
    talk_id INTEGER PRIMARY KEY REFERENCES talk(ID),
    speaker_role_id INTEGER REFERENCES speaker_role(id),
    uri_l TEXT,
    uri_gc TEXT,
    kicker TEXT,
    talk_preview TEXT,
    data_aid TEXT

  speaker_role table:                                    <-- unchanged
  conference_topic table:                                <-- unchanged
  talk_topic table:                                      <-- unchanged
```

### Pattern 1: Backfill Script Migration
**What:** Each backfill script that currently writes to `talks` is updated to write to `talk_metadata` instead.
**When to use:** For `backfill_talk_metadata.py`, `backfill_talk_kicker.py`, `backfill_talk_uri.py`, `backfill_talk_metadata_role_extraction.py`.
**Key change:** Replace `UPDATE talk SET ... WHERE ID = ?` with `INSERT INTO talk_metadata (...) VALUES (...) ON CONFLICT(talk_id) DO UPDATE SET ...`.
**Example:**
```python
# Before (in backfill_talk_kicker.py):
core_db.execute(
    "UPDATE talk SET Kicker = ? WHERE ID = ?",
    (kicker_text, talk_id),
)

# After:
core_db.execute(
    """INSERT INTO talk_metadata (talk_id, kicker)
       VALUES (?, ?)
       ON CONFLICT(talk_id) DO UPDATE SET kicker = excluded.kicker""",
    (talk_id, kicker_text),
)
```

### Pattern 2: Phase 1 Query Update
**What:** Add LEFT JOIN to `talk_metadata` in the Phase 1 SQL query.
**When to use:** When updating `extractors/phase1_talk_metadata.py`.
**Example:**
```python
# Add to existing query after the INNER JOINs:
LEFT JOIN talk_metadata tm ON t.ID = tm.talk_id

# Add to SELECT list:
tm.speaker_role_id AS enriched_speaker_role_id,
tm.uri_l AS enriched_uri_l,
tm.uri_gc AS enriched_uri_gc,
tm.kicker AS enriched_kicker,
tm.talk_preview AS enriched_talk_preview,
tm.data_aid AS enriched_data_aid
```

### Pattern 3: Church API Preview Fetcher
**What:** Script that fetches talk previews from the Church API for all conferences.
**When to use:** For ENRCH-03.
**Key insight:** The existing `api/extract_conference_sections.py` already fetches conference data from the API endpoint `https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri=`. The response JSON contains `toc.entries[].section.entries[]` where each entry has a `preview` field. The fetcher needs to:
1. Iterate all conferences from `core.52.db`
2. Fetch each conference's API data
3. Extract `preview` from each talk entry
4. Match to `talk_id` using URI or `data_aid`
5. Save to `talk_previews.json`

### Anti-Patterns to Avoid
- **Dropping columns from `talks` table:** Do NOT remove `URI_L`, `URI_GC`, `data_aid`, `speaker_role_id`, `Kicker` from `talks`. SQLite doesn't support `DROP COLUMN` cleanly on older versions, and other code may reference these columns. Leave them as-is; the authoritative source becomes `talk_metadata`.
- **Modifying `backfill_topics.py` or `backfill_talk_texts.py`:** These don't write to `talks` and are explicitly out of scope (ENRCH-06).
- **Writing previews to `content.52.db`:** The current `backfill_talk_preview.py` writes to `content.52.db talkbody.TextPreview`. The new approach stores previews in `talk_metadata.talk_preview` in `core.52.db`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP caching for Church API | Custom caching logic | `requests_cache` (already used) | Already configured in `api/extract_conference_sections.py` with SQLite backend |
| Talk ID matching (URI to talk_id) | Manual string matching | Existing DB lookups by `URI_GC` or `data_aid` | Pattern already established in `backfill_topics.py` and `Update_GC_PLAN.md` |
| Speaker role normalization | Custom title casing | `title_case_role()` and `slugify()` from `backfill_talk_metadata.py` | Already handles edge cases like articles/prepositions |
| Kicker extraction from HTML | New HTML parsing | `extract_kicker()` from `backfill_talk_kicker.py` | Already handles 4 era-specific patterns |

## Common Pitfalls

### Pitfall 1: UPSERT Syntax in SQLite
**What goes wrong:** Using `INSERT OR REPLACE` destroys existing columns not in the INSERT.
**Why it happens:** `INSERT OR REPLACE` deletes the existing row then inserts a new one, which NULLs out any columns not specified.
**How to avoid:** Use `INSERT INTO ... ON CONFLICT(talk_id) DO UPDATE SET col = excluded.col` for each column being set. This preserves other columns.
**Warning signs:** After running one backfill script, other columns in `talk_metadata` become NULL.

### Pitfall 2: Foreign Key Enforcement
**What goes wrong:** SQLite has foreign keys OFF by default.
**Why it happens:** Foreign key constraints must be explicitly enabled with `PRAGMA foreign_keys = ON`.
**How to avoid:** The `Database` class in `db/__init__.py` does not enable foreign keys. Add `PRAGMA foreign_keys = ON` to the DDL script or the connection setup if FK enforcement is desired. For this phase, the FK on `talk_id` is mostly documentation since all `talk_id` values come from existing `talks.ID`.
**Warning signs:** Rows in `talk_metadata` with `talk_id` values that don't exist in `talks`.

### Pitfall 3: Preview Coverage Gap
**What goes wrong:** The Church API may not have preview data for older conferences (pre-1971 or early era talks).
**Why it happens:** The API endpoint `/general-conference/{year}/{month}` may return empty results for very old conferences, or entries may lack the `preview` field.
**How to avoid:** Handle NULL/missing previews gracefully. Log coverage statistics. Accept that `talk_preview` will be NULL for many older talks.
**Warning signs:** Only a fraction of 7,659 talks end up with previews.

### Pitfall 4: Backfill Script Ordering
**What goes wrong:** Running backfill scripts before creating the `talk_metadata` table causes errors.
**Why it happens:** Scripts are independent and don't create the table themselves.
**How to avoid:** DDL for `talk_metadata` must run first. Each backfill script should use `CREATE TABLE IF NOT EXISTS` or assume the table exists.
**Warning signs:** `sqlite3.OperationalError: no such table: talk_metadata`.

### Pitfall 5: Windows Encoding Issues
**What goes wrong:** JSON files with non-ASCII characters fail to load on Windows.
**Why it happens:** Python on Windows defaults to cp1252 encoding, not UTF-8.
**How to avoid:** Always specify `encoding='utf-8'` when opening JSON files. The existing `backfill_talk_kicker.py` already handles this with `sys.stdout.reconfigure(encoding="utf-8")`.
**Warning signs:** `UnicodeDecodeError: 'charmap' codec can't decode byte`.

### Pitfall 6: Database Timeout
**What goes wrong:** Long-running backfill queries get interrupted.
**Why it happens:** `db/__init__.py` installs a 5-second timeout progress handler on all connections.
**How to avoid:** When running backfill scripts, use a larger timeout: `Database(path, timeout=60, read_only=False)`. The batch processing pattern in existing scripts (e.g., `backfill_talk_kicker.py` with batch_size=500) helps keep individual operations short.
**Warning signs:** `sqlite3.OperationalError: interrupted`.

## Code Examples

### DDL for talk_metadata Table
```sql
-- Source: Derived from current talks table columns and ENRCH-01 requirements
CREATE TABLE IF NOT EXISTS talk_metadata (
    talk_id INTEGER PRIMARY KEY REFERENCES talk(ID),
    speaker_role_id INTEGER REFERENCES speaker_role(id),
    uri_l TEXT,
    uri_gc TEXT,
    kicker TEXT,
    talk_preview TEXT,
    data_aid TEXT
);

-- Index for lookups by data_aid (used in UPDATE.py matching)
CREATE INDEX IF NOT EXISTS idx_talk_metadata_data_aid ON talk_metadata(data_aid);

-- Index for lookups by uri_gc (used in topic backfill matching)
CREATE INDEX IF NOT EXISTS idx_talk_metadata_uri_gc ON talk_metadata(uri_gc);
```

### UPSERT Pattern for Backfill Scripts
```python
# Source: SQLite documentation for ON CONFLICT clause
def upsert_talk_metadata(db, talk_id, **fields):
    """Insert or update a talk_metadata row, preserving unset columns."""
    columns = list(fields.keys())
    placeholders = ", ".join(["?"] * (len(columns) + 1))
    col_names = ", ".join(["talk_id"] + columns)
    update_clause = ", ".join(f"{col} = excluded.{col}" for col in columns)

    values = [talk_id] + [fields[col] for col in columns]

    db.execute(
        f"""INSERT INTO talk_metadata ({col_names})
            VALUES ({placeholders})
            ON CONFLICT(talk_id) DO UPDATE SET {update_clause}""",
        values,
    )
```

### Phase 1 Query with LEFT JOIN
```python
# Source: Current extractors/phase1_talk_metadata.py build_talk_metadata_query()
query = """
    SELECT
        t.ID as talk_id,
        t.Title as title,
        t.Date as talk_date,
        t.Corpus as corpus,
        t.URL as url,
        -- Enriched fields from talk_metadata (preferred) with fallback to talks
        COALESCE(tm.uri_l, t.URI_L) as uri_l,
        COALESCE(tm.uri_gc, t.URI_GC) as uri_gc,
        COALESCE(tm.data_aid, t.data_aid) as data_aid,
        t.SpeakerID as speaker_id,
        COALESCE(tm.speaker_role_id, t.speaker_role_id) as speaker_role_id,
        tm.kicker,
        tm.talk_preview,
        -- ... rest of existing fields ...
        s.GivenNames as speaker_given_names,
        s.LastNames as speaker_last_names,
        -- etc.
    FROM talk t
    INNER JOIN speaker s ON t.SpeakerID = s.ID
    INNER JOIN conference_talk ct ON t.ID = ct.TalkID
    INNER JOIN conf_session cs ON ct.SessionID = cs.ID
    INNER JOIN conference c ON cs.ConferenceID = c.ID
    LEFT JOIN talk_metadata tm ON t.ID = tm.talk_id
    WHERE 1=1
"""
```

### Church API Preview Response Structure
```python
# Source: api/extract_conference_sections.py and api/sessions.json
# API endpoint: https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri=/general-conference/{year}/{month}
# Response structure:
# {
#   "toc": {
#     "entries": [
#       {
#         "section": {
#           "entries": [
#             {
#               "uri": "/general-conference/2025/10/12stevenson",
#               "title": "Blessed Are the Peacemakers",
#               "preview": "Elder Stevenson teaches us to follow...",
#               "id": "12stevenson",   <-- this is the data_aid
#               ...
#             }
#           ]
#         }
#       }
#     ]
#   }
# }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Enrichment columns on `talks` table | Dedicated `talk_metadata` table | This phase | Clean separation; Phase 1 reads from single JOIN |
| Preview in `content.52.db talkbody.TextPreview` | Preview in `core.52.db talk_metadata.talk_preview` | This phase | All enrichment data in one table in one database |
| 34 previews in `talk_previews.json` | Full coverage via Church API fetch | This phase | Complete preview data for all available GC talks |

## Existing Backfill Script Inventory

| Script | Current Target | New Target | Fields Written |
|--------|---------------|------------|----------------|
| `backfill_talk_metadata.py` | `talks.Title`, `talks.speaker_role_id`, `talks.data_aid` | `talk_metadata.speaker_role_id`, `talk_metadata.data_aid` | speaker_role_id, data_aid (Title stays on talks) |
| `backfill_talk_kicker.py` | `talks.Kicker` | `talk_metadata.kicker` | kicker |
| `backfill_talk_uri.py` | `talks.URI_L`, `talks.URI_GC` | `talk_metadata.uri_l`, `talk_metadata.uri_gc` | uri_l, uri_gc |
| `backfill_talk_metadata_role_extraction.py` | `talks.speaker_role_id` | `talk_metadata.speaker_role_id` | speaker_role_id |
| `backfill_talk_texts.py` | `content.52.db talkbody` | NO CHANGE | TextRaw, TextSimple, etc. |
| `backfill_topics.py` | `conference_topic`, `talk_topic` | NO CHANGE | topic data |
| `backfill_talk_preview.py` | `content.52.db talkbody.TextPreview` | `talk_metadata.talk_preview` | talk_preview |

**Important note about `backfill_talk_metadata.py`:** This script also writes `Title` to the `talks` table. Title updates should remain on `talks` since Title is a core field, not an enrichment field. Only `speaker_role_id` and `data_aid` should move to `talk_metadata`.

## Open Questions

1. **Should enrichment columns be dropped from `talks`?**
   - What we know: The columns (`URI_L`, `URI_GC`, `data_aid`, `speaker_role_id`, `Kicker`) exist on `talks` and will be duplicated in `talk_metadata`.
   - What's unclear: Whether any code outside the pipeline reads these columns directly.
   - Recommendation: Leave columns on `talks` for now. Use COALESCE in Phase 1 query to prefer `talk_metadata` values. Dropping can happen in a future cleanup phase.

2. **How complete will Church API preview coverage be?**
   - What we know: Only 34 previews exist currently. The API has data for conferences from ~1971 onward (based on URL patterns in talk_metadata.json starting at talkID 2000).
   - What's unclear: Exact coverage -- older conferences may not have preview data in the API.
   - Recommendation: Build the fetcher, run it, log coverage statistics. Accept partial coverage as expected behavior.

3. **Should `backfill_talk_preview.py` continue to write to `content.52.db`?**
   - What we know: Currently writes `TextPreview` to `content.52.db talkbody` table. The new plan puts preview in `talk_metadata.talk_preview` in `core.52.db`.
   - What's unclear: Whether anything reads `talkbody.TextPreview`.
   - Recommendation: Update the script to write to `talk_metadata.talk_preview` instead. Leave the old `TextPreview` column in `content.52.db` as-is.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via pipenv) |
| Config file | None detected -- uses default pytest discovery |
| Quick run command | `pipenv run py -m pytest tests/test_phase1.py -x` |
| Full suite command | `pipenv run py -m pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENRCH-01 | `talk_metadata` table exists with correct schema | integration | `pipenv run py -m pytest tests/test_phase1.py -x -k "talk_metadata_table"` | No -- Wave 0 |
| ENRCH-02 | Backfill scripts write to `talk_metadata` not `talks` | integration | `pipenv run py -m pytest tests/test_phase1.py -x -k "backfill_target"` | No -- Wave 0 |
| ENRCH-03 | Preview fetcher produces complete `talk_previews.json` | manual-only | Run fetcher and check output count | N/A (manual) |
| ENRCH-04 | `talk_metadata` populated after backfill | integration | `pipenv run py -m pytest tests/test_phase1.py -x -k "metadata_populated"` | No -- Wave 0 |
| ENRCH-05 | Phase 1 output includes enriched fields | unit | `pipenv run py -m pytest tests/test_phase1.py -x -k "enriched"` | No -- Wave 0 |
| ENRCH-06 | `talk_topic`/`conference_topic` unchanged | smoke | `pipenv run py -m pytest tests/test_phase1.py -x -k "topic_tables"` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/test_phase1.py -x`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x`
- **Phase gate:** Full suite green before verification

### Wave 0 Gaps
- [ ] Tests for `talk_metadata` DDL (table creation, column types)
- [ ] Tests for UPSERT pattern (insert, update, conflict handling)
- [ ] Tests for Phase 1 query with LEFT JOIN (with and without `talk_metadata` rows)
- [ ] Tests for enriched fields in TalkMetadata dataclass (`kicker`, `talk_preview`)
- [ ] Smoke test that `talk_topic`/`conference_topic` row counts are unchanged

## Sources

### Primary (HIGH confidence)
- `db/__init__.py` -- Database class, connection patterns, path constants
- `extractors/phase1_talk_metadata.py` -- Current Phase 1 SQL query and extraction logic
- `models/talk_metadata.py` -- TalkMetadata dataclass fields
- `db/one-off-migration/backfill_talk_metadata.py` -- Speaker role and data_aid backfill pattern
- `db/one-off-migration/backfill_talk_kicker.py` -- Kicker extraction pattern
- `db/one-off-migration/backfill_talk_uri.py` -- URI generation and correction pattern
- `db/one-off-migration/backfill_talk_metadata_role_extraction.py` -- HTML-based role extraction
- `db/one-off-migration/backfill_talk_preview.py` -- Preview backfill pattern (currently targets content.52.db)
- `db/one-off-migration/backfill_topics.py` -- Topic backfill (DO NOT TOUCH)
- `api/extract_conference_sections.py` -- Church API fetch pattern
- `docs/update/Update_GC_PLAN.md` -- UPDATE.py plan showing talk matching and preview collection approach
- `scripts/db_schema_extractor.py` output -- Current `talks` table schema (15 columns, 7659 rows)

### Secondary (MEDIUM confidence)
- SQLite `ON CONFLICT` documentation -- UPSERT syntax
- `talk_previews.json` -- 34 entries, confirming format `{talkID, title, uri, preview}`
- `talk_metadata.json` -- ~28K lines, confirming format `{talkID, title, uri, speaker_role, data_aid}`

### Tertiary (LOW confidence)
- Church API preview coverage for pre-1971 conferences -- unknown, needs empirical testing

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies
- Architecture: HIGH -- straightforward DDL + script migration with well-understood patterns
- Pitfalls: HIGH -- based on direct code reading and SQLite documentation
- Church API coverage: MEDIUM -- API pattern known, but coverage extent for older conferences untested

**Research date:** 2026-03-19
**Valid until:** 2026-04-19 (stable domain, no external dependency changes expected)
