# Implementation Plan: UPDATE.py - Conference Database Synchronization Script

## Overview

Create a comprehensive script (`/UPDATE.py`) that synchronizes data from a conference-specific database (gc.db) to the main core database and JSON files. The script processes a single conference session, updating metadata, topics, speaker roles, and talk relationships.

## Critical Files

**Script Location:**

-   `/UPDATE.py` (new file)

**Database Files:**

-   `/db/core.52.db` (main database, updated)
-   `/db/*.db` (gc.db passed as command-line argument)

**JSON Files (all in root directory):**

-   `/api/sessions.json` (update/append)
-   `/db/one-off-migration/conference_topics.json` (update/append)
-   `/db/one-off-migration/talk_metadata.json` (update/append)
-   `/talk_previews.json` (create new, update/append)

**Reference Files:**

-   `/db/one-off-migration/backfill_topics.py` (pattern reference for topic handling)
-   `/db/one-off-migration/backfill_talk_metadata.py` (pattern reference for speaker role handling)
-   `/db/__init__.py` (Database class)

## Matching Strategy

**Talk Matching (gc.db → core.db):**

1. **Primary**: Match by URI (gc.subitem.uri = core.talk.URI_GC OR core.talk.URI_L)
2. **Fallback**: Match by data_aid (gc.subitem.id = core.talk.data_aid)
3. **Unmatched**: Log warning, skip processing, add to summary report

## Implementation Phases

### Phase 1: Setup and Initialization

**1.1 Command-Line Interface**

```python
import argparse
parser = argparse.ArgumentParser(description="Update core database from conference database")
parser.add_argument("gc_db_path", help="Path to conference-specific database (gc.db)")
parser.add_argument("--dry-run", action="store_true", help="Simulate without writing")
parser.add_argument("--verbose", action="store_true", help="Detailed logging")
```

**1.2 Validate Inputs**

-   Check gc_db_path exists and is readable
-   Verify gc.db has expected schema (Topic, TopicSubitem, nav_item, subitem, subitem_content, metadata tables)
-   Validate core.52.db exists at `/db/core.52.db`

**1.3 Initialize Database Connections**

```python
from db import Database, CORE_DB_PATH
gc_db = Database(gc_db_path, read_only=True)
core_db = Database(CORE_DB_PATH, read_only=False)
```

**1.4 Load Existing JSON Files**

-   Load `/api/sessions.json` (create empty `{}` if not exists)
-   Load `/db/one-off-migration/conference_topics.json` (create empty `[]` if not exists)
-   Load `/db/one-off-migration/talk_metadata.json` (create empty `[]` if not exists)
-   Load `/talk_previews.json` (create empty `[]` if not exists)

**1.5 Initialize Tracking Structures**

```python
stats = {
    "talks_matched": 0,
    "talks_unmatched": 0,
    "talks_updated": 0,
    "topics_added": 0,
    "talk_topics_added": 0,
    "speaker_roles_created": 0,
    "previews_added": 0
}
unmatched_talks = []  # For final report
```

---

### Phase 2: Extract Conference Metadata

**2.1 Query Conference Information from gc.metadata**

```sql
SELECT key, value FROM metadata
WHERE key IN ('uri', 'title')
```

**2.2 Parse Year-Month from URI**

-   Extract from `metadata.uri` (e.g., "/general-conference/2025/04")
-   Pattern: `/general-conference/{year}/{month}`
-   Store as: `conference_key = "2025-04"`

**2.3 Format Conference Title**

-   Extract from `metadata.title` (e.g., "April 2025 general conference")
-   Parse to: "Apr 2025" (abbreviated month, year only)
-   Abbreviations: {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}

---

### Phase 3: Process Sessions (sessions.json)

**3.1 Query Session Entries from gc.db**

```sql
SELECT
    s.uri,
    s.title,
    n.subtitle
FROM subitem s
JOIN nav_item n ON s.id = n.subitem_id
WHERE s.type = 'conferenceSession'
ORDER BY s.position
```

**3.2 Build Session Objects**

```python
session_entry = {
    "content": {
        "uri": row["uri"],
        "title": row["title"],
        "subtitle": row["subtitle"] or ""
    }
}
```

**3.3 Update sessions.json**

-   Load existing `/api/sessions.json`
-   Create or replace entry at `sessions[conference_key]`
-   Write back to file with `indent=2`

---

### Phase 4: Build Talk Matching Map

**4.1 Query All Talks from gc.db**

```sql
SELECT DISTINCT
    s.id AS data_aid,
    s.uri,
    s.title,
    s.position,
    n.subtitle AS speaker_subtitle,
    n.image_renditions,
    n.preview
FROM subitem s
JOIN nav_item n ON s.id = n.subitem_id
WHERE s.type = 'default'
ORDER BY s.position
```

**4.2 Build Matching Map (gc_talk → core_talk_id)**

```python
talk_map = {}  # {gc_data_aid: {core_talk_id, gc_data, match_method}}

for gc_talk in gc_talks:
    # Try URI match first
    core_talk = core_db.select_one("""
        SELECT ID FROM talk
        WHERE URI_GC = ? OR URI_L = ?
    """, (gc_talk["uri"], gc_talk["uri"]))

    if not core_talk:
        # Fallback to data_aid match
        core_talk = core_db.select_one("""
            SELECT ID FROM talk WHERE data_aid = ?
        """, (gc_talk["data_aid"],))

    if core_talk:
        talk_map[gc_talk["data_aid"]] = {
            "core_talk_id": core_talk["ID"],
            "gc_data": gc_talk,
            "match_method": "uri" if core_talk else "data_aid"
        }
        stats["talks_matched"] += 1
    else:
        # No match found - log for report
        unmatched_talks.append({
            "data_aid": gc_talk["data_aid"],
            "uri": gc_talk["uri"],
            "title": gc_talk["title"],
            "speaker": gc_talk["speaker_subtitle"]
        })
        stats["talks_unmatched"] += 1
```

---

### Phase 5: Update core.talk Table

**5.1 Create Helper Functions**

**Parse Speaker Role from HTML:**

```python
from bs4 import BeautifulSoup

def extract_speaker_role(html_content: str) -> str | None:
    """Extract <p class="author-role"> from HTML content."""
    soup = BeautifulSoup(html_content, "html.parser")
    role_tag = soup.find("p", class_="author-role")
    if role_tag:
        return role_tag.get_text(strip=True)
    return None
```

**Lookup/Insert Speaker Role (from backfill_talk_metadata.py pattern):**

```python
def get_or_create_speaker_role_id(db: Database, role: str) -> int:
    """Get existing speaker_role_id or create new one."""
    from db.one-off-migration.backfill_talk_metadata import title_case_role, slugify

    # Normalize role
    normalized_role = title_case_role(role)

    # Check if exists
    existing = db.select_one(
        "SELECT id FROM speaker_role WHERE role = ?",
        (normalized_role,)
    )
    if existing:
        return existing["id"]

    # Create new role
    role_slug = slugify(normalized_role)

    # Handle slug collisions
    counter = 2
    while True:
        try:
            db.execute(
                "INSERT INTO speaker_role (role, slug) VALUES (?, ?)",
                (normalized_role, role_slug)
            )
            break
        except sqlite3.IntegrityError:
            role_slug = f"{slugify(normalized_role)}-{counter}"
            counter += 1

    # Query back the ID
    result = db.select_one(
        "SELECT id FROM speaker_role WHERE role = ?",
        (normalized_role,)
    )
    stats["speaker_roles_created"] += 1
    return result["id"]
```

**5.2 Process Each Matched Talk**

```python
for gc_data_aid, match_info in talk_map.items():
    core_talk_id = match_info["core_talk_id"]
    gc_talk = match_info["gc_data"]

    # Get HTML content for speaker role extraction
    html_row = gc_db.select_one(
        "SELECT content_html FROM subitem_content WHERE subitem_id = ?",
        (gc_data_aid,)
    )

    speaker_role_id = None
    if html_row:
        role_text = extract_speaker_role(html_row["content_html"])
        if role_text:
            speaker_role_id = get_or_create_speaker_role_id(core_db, role_text)

    # Update talk table
    core_db.execute("""
        UPDATE talk
        SET
            speaker_role_id = ?,
            URI_GC = ?,
            URI_L = ?,
            data_aid = ?
        WHERE ID = ?
    """, (
        speaker_role_id,
        gc_talk["uri"],  # Assuming URI_GC = URI_L for gc data
        gc_talk["uri"],
        gc_data_aid,
        core_talk_id
    ))

    stats["talks_updated"] += 1
```

---

### Phase 6: Create and Populate talk_preview Table

**6.1 Create Table (Idempotent)**

```python
core_db.execute("""
    CREATE TABLE IF NOT EXISTS talk_preview (
        TalkID INTEGER PRIMARY KEY,
        preview TEXT,
        FOREIGN KEY (TalkID) REFERENCES talk(ID)
    )
""")
```

**6.2 Insert Preview Data**

```python
for gc_data_aid, match_info in talk_map.items():
    core_talk_id = match_info["core_talk_id"]
    gc_talk = match_info["gc_data"]

    if gc_talk.get("preview"):
        core_db.execute("""
            INSERT OR REPLACE INTO talk_preview (TalkID, preview)
            VALUES (?, ?)
        """, (core_talk_id, gc_talk["preview"]))

        stats["previews_added"] += 1
```

**6.3 Build talk_previews.json**

```python
# Build entries for all talks with previews
preview_entries = []
for gc_data_aid, match_info in talk_map.items():
    gc_talk = match_info["gc_data"]
    if gc_talk.get("preview"):
        preview_entries.append({
            "talkID": match_info["core_talk_id"],
            "title": gc_talk["title"],
            "uri": gc_talk["uri"],
            "preview": gc_talk["preview"]
        })

# Merge with existing talk_previews.json
existing_previews = load_json("talk_previews.json")
# Create lookup by talkID
preview_map = {p["talkID"]: p for p in existing_previews}
# Update with new entries
for entry in preview_entries:
    preview_map[entry["talkID"]] = entry
# Convert back to list
updated_previews = list(preview_map.values())
# Sort by talkID
updated_previews.sort(key=lambda x: x["talkID"])
# Write to file
save_json("talk_previews.json", updated_previews)
```

---

### Phase 7: Update talk_topic and conference_topic Tables

**7.1 Query Topics and Relationships from gc.db**

```sql
SELECT
    t.topicId AS topic_slug,
    t.name AS topic_name,
    ts.subitemId AS data_aid
FROM Topic t
JOIN TopicSubitem ts ON t.id = ts.topicId
ORDER BY t.name, ts.subitemId
```

**7.2 Process Topic-Talk Relationships**

```python
topic_id_cache = {}  # {topic_name: topic_id}

for row in gc_topic_relationships:
    topic_name = row["topic_name"]
    topic_slug = row["topic_slug"]
    gc_data_aid = row["data_aid"]

    # Skip if talk not matched
    if gc_data_aid not in talk_map:
        continue

    core_talk_id = talk_map[gc_data_aid]["core_talk_id"]

    # Get or create conference_topic
    if topic_name not in topic_id_cache:
        existing_topic = core_db.select_one(
            "SELECT id FROM conference_topic WHERE name = ?",
            (topic_name,)
        )

        if existing_topic:
            topic_id_cache[topic_name] = existing_topic["id"]
        else:
            # Insert new topic (ON CONFLICT DO NOTHING pattern)
            core_db.execute("""
                INSERT INTO conference_topic (name, slug)
                VALUES (?, ?)
                ON CONFLICT(name) DO NOTHING
            """, (topic_name, topic_slug))

            # Query back the ID
            result = core_db.select_one(
                "SELECT id FROM conference_topic WHERE name = ?",
                (topic_name,)
            )
            topic_id_cache[topic_name] = result["id"]
            stats["topics_added"] += 1

    topic_id = topic_id_cache[topic_name]

    # Insert talk_topic relationship (ON CONFLICT DO NOTHING)
    content_identifier = talk_map[gc_data_aid]["gc_data"]["uri"]

    core_db.execute("""
        INSERT INTO talk_topic (topic_id, talk_id, content_identifier)
        VALUES (?, ?, ?)
        ON CONFLICT(topic_id, content_identifier) DO NOTHING
    """, (topic_id, core_talk_id, content_identifier))

    stats["talk_topics_added"] += 1
```

---

### Phase 8: Update conference_topics.json

**8.1 Helper: Parse Image Renditions**

```python
def extract_image_url(image_renditions: str) -> str | None:
    """
    Extract URL from image_renditions field.

    Format: "768x432,url\n192x108,url"
    Returns the first URL found (768x432 preferred).
    """
    if not image_renditions:
        return None

    lines = image_renditions.split("\n")
    for line in lines:
        if "," in line:
            parts = line.split(",", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None
```

**8.2 Build Topic Entries Map**

```python
# Load existing conference_topics.json
existing_topics = load_json("db/one-off-migration/conference_topics.json")

# Create topic lookup: {topic_name: topic_object}
topics_map = {t["topic"]: t for t in existing_topics}

# For each topic in gc.db
for row in gc_topic_relationships:
    topic_name = row["topic_name"]
    gc_data_aid = row["data_aid"]

    # Skip unmatched talks
    if gc_data_aid not in talk_map:
        continue

    gc_talk = talk_map[gc_data_aid]["gc_data"]

    # Create entry object
    entry = {
        "type": "item",
        "src": extract_image_url(gc_talk.get("image_renditions")),
        "title": gc_talk["title"],
        "meta": conference_title,  # e.g., "Apr 2025"
        "secondaryMeta": gc_talk["speaker_subtitle"],
        "uri": gc_talk["uri"],
        "subtype": "secondary"
    }

    # Add to topic
    if topic_name not in topics_map:
        topics_map[topic_name] = {
            "topic": topic_name,
            "entries": []
        }

    # Check if entry already exists (by uri)
    existing_uris = {e["uri"] for e in topics_map[topic_name]["entries"]}
    if entry["uri"] not in existing_uris:
        topics_map[topic_name]["entries"].append(entry)

# Convert back to list and sort by topic name
updated_topics = list(topics_map.values())
updated_topics.sort(key=lambda x: x["topic"])

# Write to file
save_json("db/one-off-migration/conference_topics.json", updated_topics)
```

---

### Phase 9: Update talk_metadata.json

**9.1 Build Talk Metadata Entries**

```python
# Load existing talk_metadata.json
existing_metadata = load_json("db/one-off-migration/talk_metadata.json")

# Create lookup by talkID
metadata_map = {m["talkID"]: m for m in existing_metadata}

# For each matched talk
for gc_data_aid, match_info in talk_map.items():
    core_talk_id = match_info["core_talk_id"]
    gc_talk = match_info["gc_data"]

    # Get speaker role text
    html_row = gc_db.select_one(
        "SELECT content_html FROM subitem_content WHERE subitem_id = ?",
        (gc_data_aid,)
    )
    speaker_role = None
    if html_row:
        speaker_role = extract_speaker_role(html_row["content_html"])

    # Create/update entry
    metadata_map[core_talk_id] = {
        "talkID": core_talk_id,
        "title": gc_talk["title"],
        "uri": gc_talk["uri"],
        "speaker_role": speaker_role,
        "data_aid": gc_data_aid
    }

# Convert to list and sort by talkID
updated_metadata = list(metadata_map.values())
updated_metadata.sort(key=lambda x: x["talkID"])

# Write to file
save_json("db/one-off-migration/talk_metadata.json", updated_metadata)
```

---

### Phase 10: Generate Reports

**10.1 Summary Statistics**

```python
print("\n" + "="*60)
print("UPDATE COMPLETE - Summary Statistics")
print("="*60)
print(f"Conference: {conference_key} ({conference_title})")
print(f"\nTalk Matching:")
print(f"  - Matched: {stats['talks_matched']}")
print(f"  - Unmatched: {stats['talks_unmatched']}")
print(f"\nDatabase Updates:")
print(f"  - Talks updated: {stats['talks_updated']}")
print(f"  - Speaker roles created: {stats['speaker_roles_created']}")
print(f"  - Topics added: {stats['topics_added']}")
print(f"  - Talk-topic relationships added: {stats['talk_topics_added']}")
print(f"  - Previews added: {stats['previews_added']}")
print(f"\nJSON Files Updated:")
print(f"  - sessions.json")
print(f"  - conference_topics.json")
print(f"  - talk_metadata.json")
print(f"  - talk_previews.json")
print("="*60)
```

**10.2 Unmatched Talks Report**

```python
if unmatched_talks:
    print("\n" + "="*60)
    print("INCONSISTENCY REPORT - Unmatched Talks")
    print("="*60)
    print(f"Found {len(unmatched_talks)} talks in gc.db with no match in core.db\n")

    for i, talk in enumerate(unmatched_talks, 1):
        print(f"{i}. {talk['title']}")
        print(f"   Speaker: {talk['speaker']}")
        print(f"   URI: {talk['uri']}")
        print(f"   Data-Aid: {talk['data_aid']}")
        print()

    # Save to file
    report_file = f"unmatched_talks_{conference_key}.json"
    save_json(report_file, unmatched_talks)
    print(f"Full report saved to: {report_file}")
    print("="*60)
```

---

## Utility Functions

**JSON File I/O:**

```python
import json
from typing import Any

def load_json(filepath: str) -> Any:
    """Load JSON file, return empty structure if not exists."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Return appropriate empty structure based on file
        if "topics" in filepath or "metadata" in filepath or "previews" in filepath:
            return []
        return {}

def save_json(filepath: str, data: Any) -> None:
    """Save JSON with consistent formatting."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

**Month Abbreviation:**

```python
MONTH_ABBR = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
}

def format_conference_title(full_title: str, month: str, year: str) -> str:
    """Convert 'April 2025 general conference' to 'Apr 2025'."""
    abbr = MONTH_ABBR.get(month, month)
    return f"{abbr} {year}"
```

---

## Error Handling

**Database Errors:**

-   Wrap all database operations in try/except
-   Rollback on errors if within transaction
-   Log detailed error context (table, operation, values)

**JSON Errors:**

-   Validate JSON structure after loading
-   Handle malformed entries gracefully
-   Backup original file before writing

**Validation Errors:**

-   Check for NULL/missing required fields
-   Validate foreign key references exist
-   Report validation failures without stopping entire process

---

## Idempotency & Safety

**Idempotent Operations:**

-   `ON CONFLICT DO NOTHING` for conference_topic and talk_topic inserts
-   `INSERT OR REPLACE` for talk_preview (keyed by TalkID)
-   `UPDATE` statements for core.talk (safe to run multiple times)
-   JSON merging preserves existing data for other conferences

**Dry Run Mode:**

-   `--dry-run` flag simulates all operations without writing
-   Prints all SQL statements and JSON changes
-   Useful for validation before actual run

**Transaction Safety:**

-   Consider wrapping core.db updates in transaction
-   Commit only if all operations succeed
-   JSON files written only after successful DB commit

---

## Testing Strategy

**Unit Tests:**

1. Test talk matching logic (URI primary, data_aid fallback)
2. Test speaker role parsing from HTML
3. Test image URL extraction
4. Test month abbreviation formatting

**Integration Tests:**

1. Test with sample gc.db (2-3 talks, 2-3 topics)
2. Verify all JSON files updated correctly
3. Verify database tables updated correctly
4. Test idempotency (run twice, verify no duplicates)

**Edge Cases:**

1. gc.db with talks not in core.db
2. Missing speaker_role in HTML
3. Missing image_renditions
4. Empty topic lists
5. Malformed URIs

---

## Usage Examples

**Basic Usage:**

```bash
python UPDATE.py db/2025-04.db
```

**Dry Run (Preview Changes):**

```bash
python UPDATE.py db/2025-04.db --dry-run
```

**Verbose Output:**

```bash
python UPDATE.py db/2025-04.db --verbose
```

---

## Dependencies

**Standard Library:**

-   `argparse` - CLI argument parsing
-   `json` - JSON file I/O
-   `sqlite3` - Database operations
-   `sys`, `os` - Path and system operations
-   `re` - Regular expressions for parsing

**External Libraries:**

-   `beautifulsoup4` - HTML parsing for speaker role extraction

**Internal Modules:**

-   `db.Database` - Database abstraction layer
-   `db.one-off-migration.backfill_talk_metadata` - Speaker role utilities (title_case_role, slugify)

---

## File Structure Summary

```
/UPDATE.py (new)
/db/
  core.52.db (updated)
  one-off-migration/
    conference_topics.json (updated)
    talk_metadata.json (updated)
/api/
  sessions.json (updated)
/talk_previews.json (new/updated)
/unmatched_talks_{year-month}.json (generated report)
```

---

## Notes

1. **Speaker Role Normalization**: Uses title_case_role() from backfill_talk_metadata.py to ensure consistency
2. **Slug Collision Handling**: Appends counter suffix for duplicate slugs (e.g., "role-2", "role-3")
3. **URI Variants**: gc.db URIs are stored in both URI_GC and URI_L fields (no normalization needed for modern data)
4. **Transaction Scope**: Consider wrapping all core.db writes in a single transaction for atomicity
5. **Logging Level**: Use --verbose for detailed SQL logging, default for summary only
6. **Backup Recommendation**: Backup core.52.db before running (not automated in script)
