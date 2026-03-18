#!/usr/bin/env python3
"""
UPDATE.py - Conference Database Synchronization Script

Synchronizes data from a conference-specific database (gc.db) to the main core database
and JSON files. Processes a single conference session, updating metadata, topics, speaker
roles, and talk relationships.

Usage:
    python UPDATE.py <gc_db_path> [--dry-run] [--verbose]

Example:
    python UPDATE.py db/2025-04.db
    python UPDATE.py db/2025-04.db --dry-run --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import Database, CORE_DB_PATH, CONTENT_DB_PATH

# Import speaker role utilities from backfill script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "db", "one-off-migration"))
from backfill_talk_metadata import title_case_role, slugify


# ============================================================================
# CONSTANTS
# ============================================================================

MONTH_ABBR = {
    "01": "Jan",
    "02": "Feb",
    "03": "Mar",
    "04": "Apr",
    "05": "May",
    "06": "Jun",
    "07": "Jul",
    "08": "Aug",
    "09": "Sep",
    "10": "Oct",
    "11": "Nov",
    "12": "Dec",
}


# ============================================================================
# UTILITY FUNCTIONS - JSON I/O
# ============================================================================


def load_json(filepath: str) -> Any:
    """
    Load JSON file, return empty structure if not exists.

    Args:
        filepath: Path to JSON file

    Returns:
        Parsed JSON data, or empty dict/list if file doesn't exist
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Return appropriate empty structure based on filename
        if any(x in filepath for x in ["topics", "metadata", "previews"]):
            return []
        return {}
    except json.JSONDecodeError as e:
        print(f"Warning: Malformed JSON in {filepath}: {e}")
        # Return empty structure
        if any(x in filepath for x in ["topics", "metadata", "previews"]):
            return []
        return {}


def save_json(filepath: str, data: Any) -> None:
    """
    Save JSON with consistent formatting.

    Args:
        filepath: Path to save JSON file
        data: Data to serialize
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================================
# UTILITY FUNCTIONS - Conference Metadata
# ============================================================================


def parse_conference_uri(uri: str) -> tuple[str, str, str]:
    """
    Parse conference URI to extract year and month.

    Args:
        uri: Conference URI (e.g., "/general-conference/2025/04")

    Returns:
        Tuple of (conference_key, year, month)
        e.g., ("2025-04", "2025", "04")

    Raises:
        ValueError: If URI format is invalid
    """
    pattern = r"/general-conference/(\d{4})/(\d{2})"
    match = re.search(pattern, uri)
    if not match:
        raise ValueError(f"Invalid conference URI format: {uri}")

    year, month = match.groups()
    conference_key = f"{year}-{month}"
    return conference_key, year, month


def format_conference_title(full_title: str, year: str, month: str) -> str:
    """
    Convert full conference title to abbreviated format.

    Args:
        full_title: Full title (e.g., "April 2025 general conference")
        year: Year string (e.g., "2025")
        month: Month string (e.g., "04")

    Returns:
        Abbreviated title (e.g., "Apr 2025")
    """
    abbr = MONTH_ABBR.get(month, month)
    return f"{abbr} {year}"


# ============================================================================
# UTILITY FUNCTIONS - HTML Parsing
# ============================================================================


def extract_speaker_role(html_content: str) -> Optional[str]:
    """
    Extract speaker role from HTML content.

    Searches for <p class="author-role"> tag and returns its text content.

    Args:
        html_content: HTML string from subitem_content.content_html

    Returns:
        Speaker role text, or None if not found
    """
    if not html_content:
        return None

    soup = BeautifulSoup(html_content, "html.parser")
    role_tag = soup.find("p", class_="author-role")

    if role_tag:
        return role_tag.get_text(strip=True)

    return None


def extract_image_url(image_renditions: str) -> Optional[str]:
    """
    Extract URL from image_renditions field.

    Format: "768x432,url\\n192x108,url"
    Returns the first URL found (768x432 preferred).

    Args:
        image_renditions: Image renditions string from nav_item

    Returns:
        Image URL, or None if not found
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


# ============================================================================
# DATABASE HELPER FUNCTIONS
# ============================================================================


def get_or_create_speaker_role_id(
    db: Database, role: str, stats: Dict[str, int], verbose: bool = False
) -> Optional[int]:
    """
    Get existing speaker_role_id or create new one.

    Args:
        db: Database connection (write mode)
        role: Speaker role text
        stats: Statistics dictionary to update
        verbose: Print detailed logging

    Returns:
        speaker_role.id, or None if role is empty
    """
    if not role:
        return None

    # Normalize role
    normalized_role = title_case_role(role)

    # Check if exists
    existing = db.select_one(
        "SELECT id FROM speaker_role WHERE role = ?", (normalized_role,)
    )
    if existing:
        if verbose:
            print(f"  Found existing role: {normalized_role} (ID: {existing['id']})")
        return existing["id"]

    # Create new role
    role_slug = slugify(normalized_role)

    # Handle slug collisions
    counter = 2
    while True:
        try:
            db.execute(
                "INSERT INTO speaker_role (role, slug) VALUES (?, ?)",
                (normalized_role, role_slug),
            )
            if verbose:
                print(f"  Created new role: {normalized_role} (slug: {role_slug})")
            break
        except sqlite3.IntegrityError:
            role_slug = f"{slugify(normalized_role)}-{counter}"
            counter += 1

    # Query back the ID
    result = db.select_one(
        "SELECT id FROM speaker_role WHERE role = ?", (normalized_role,)
    )

    stats["speaker_roles_created"] += 1
    return result["id"]


def validate_gc_schema(db: Database) -> bool:
    """
    Validate that gc.db has expected schema.

    Args:
        db: Database connection to gc.db

    Returns:
        True if schema is valid

    Raises:
        ValueError: If required tables are missing
    """
    required_tables = [
        "Topic",
        "TopicSubitem",
        "nav_item",
        "subitem",
        "subitem_content",
        "metadata",
    ]

    existing_tables = db.select("SELECT name FROM sqlite_master WHERE type='table'")
    existing_names = {row["name"] for row in existing_tables}

    missing = set(required_tables) - existing_names
    if missing:
        raise ValueError(f"gc.db missing required tables: {missing}")

    return True


# ============================================================================
# PHASE 1: SETUP AND INITIALIZATION
# ============================================================================


def initialize(
    gc_db_path: str, verbose: bool = False
) -> tuple[Database, Database, Database, Dict]:
    """
    Initialize database connections and load existing JSON files.

    Args:
        gc_db_path: Path to conference-specific database
        verbose: Print detailed logging

    Returns:
        Tuple of (gc_db, core_db, content_db, json_files)
    """
    if verbose:
        print("=" * 60)
        print("PHASE 1: Setup and Initialization")
        print("=" * 60)

    # Validate inputs
    if not os.path.exists(gc_db_path):
        raise FileNotFoundError(f"gc.db not found: {gc_db_path}")

    if not os.path.exists(CORE_DB_PATH):
        raise FileNotFoundError(f"core.db not found: {CORE_DB_PATH}")

    if not os.path.exists(CONTENT_DB_PATH):
        raise FileNotFoundError(f"content.db not found: {CONTENT_DB_PATH}")

    # Initialize database connections
    if verbose:
        print(f"Connecting to gc.db: {gc_db_path}")
    gc_db = Database(gc_db_path, read_only=True)

    if verbose:
        print(f"Connecting to core.db: {CORE_DB_PATH}")
    core_db = Database(CORE_DB_PATH, read_only=False)

    if verbose:
        print(f"Connecting to content.db: {CONTENT_DB_PATH}")
    content_db = Database(CONTENT_DB_PATH, read_only=False)

    # Validate gc.db schema
    if verbose:
        print("Validating gc.db schema...")
    validate_gc_schema(gc_db)

    # Load existing JSON files
    if verbose:
        print("Loading existing JSON files...")

    json_files = {
        "sessions": load_json("api/sessions.json"),
        "conference_topics": load_json("db/one-off-migration/conference_topics.json"),
        "talk_metadata": load_json("db/one-off-migration/talk_metadata.json"),
        "talk_previews": load_json("db/one-off-migration/talk_previews.json"),
    }

    if verbose:
        print(f"  - sessions.json: {len(json_files['sessions'])} conferences")
        print(
            f"  - conference_topics.json: {len(json_files['conference_topics'])} topics"
        )
        print(f"  - talk_metadata.json: {len(json_files['talk_metadata'])} talks")
        print(f"  - talk_previews.json: {len(json_files['talk_previews'])} previews")
        print()

    return gc_db, core_db, content_db, json_files


# ============================================================================
# PHASE 2: EXTRACT CONFERENCE METADATA
# ============================================================================


def extract_conference_metadata(
    gc_db: Database, verbose: bool = False
) -> tuple[str, str, str]:
    """
    Extract conference metadata from gc.db.

    Args:
        gc_db: Database connection to gc.db
        verbose: Print detailed logging

    Returns:
        Tuple of (conference_key, conference_title, year-month)
        e.g., ("2025-04", "Apr 2025", "2025-04")
    """
    if verbose:
        print("=" * 60)
        print("PHASE 2: Extract Conference Metadata")
        print("=" * 60)

    # Query metadata
    metadata_rows = gc_db.select(
        "SELECT key, value FROM metadata WHERE key IN ('uri', 'title')"
    )

    metadata = {row["key"]: row["value"] for row in metadata_rows}

    if "uri" not in metadata:
        raise ValueError("Missing 'uri' in gc.metadata")
    if "title" not in metadata:
        raise ValueError("Missing 'title' in gc.metadata")

    # Parse URI
    conference_key, year, month = parse_conference_uri(metadata["uri"])

    # Format title
    conference_title = format_conference_title(metadata["title"], year, month)

    if verbose:
        print(f"Conference URI: {metadata['uri']}")
        print(f"Conference Key: {conference_key}")
        print(f"Conference Title: {conference_title}")
        print(f"Full Title: {metadata['title']}")
        print()

    return conference_key, conference_title, conference_key


# ============================================================================
# PHASE 3: PROCESS SESSIONS
# ============================================================================


def process_sessions(
    gc_db: Database,
    json_files: Dict,
    conference_key: str,
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Process session entries and update sessions.json.

    Args:
        gc_db: Database connection to gc.db
        json_files: Dictionary of loaded JSON files
        conference_key: Conference key (e.g., "2025-04")
        verbose: Print detailed logging
        dry_run: Don't write files
    """
    if verbose:
        print("=" * 60)
        print("PHASE 3: Process Sessions (sessions.json)")
        print("=" * 60)

    # Query session entries
    sessions_query = """
        SELECT
            s.uri,
            s.title,
            n.subtitle
        FROM subitem s
        JOIN nav_item n ON s.id = n.subitem_id
        WHERE s.type = 'conferenceSession'
        ORDER BY s.position
    """

    session_rows = gc_db.select(sessions_query)

    if verbose:
        print(f"Found {len(session_rows)} session entries")

    # Build session objects
    session_entries = []
    for row in session_rows:
        entry = {
            "content": {
                "uri": row["uri"],
                "title": row["title"],
                "subtitle": row["subtitle"] if row["subtitle"] else "",
            }
        }
        session_entries.append(entry)

        if verbose:
            print(f"  - {row['title']}")

    # Update sessions.json
    json_files["sessions"][conference_key] = session_entries

    if not dry_run:
        save_json("api/sessions.json", json_files["sessions"])
        if verbose:
            print(f"\nUpdated api/sessions.json with {len(session_entries)} sessions")
    else:
        print(
            f"\n[DRY RUN] Would update api/sessions.json with {len(session_entries)} sessions"
        )

    print()


# ============================================================================
# PHASE 4: BUILD TALK MATCHING MAP
# ============================================================================


def build_talk_matching_map(
    gc_db: Database,
    core_db: Database,
    stats: Dict[str, int],
    unmatched_talks: List[Dict],
    verbose: bool = False,
) -> Dict[str, Dict]:
    """
    Build mapping from gc.db talks to core.db talk IDs.

    Args:
        gc_db: Database connection to gc.db
        core_db: Database connection to core.db
        stats: Statistics dictionary to update
        unmatched_talks: List to append unmatched talks
        verbose: Print detailed logging

    Returns:
        Dictionary mapping gc_data_aid to {core_talk_id, gc_data, match_method}
    """
    if verbose:
        print("=" * 60)
        print("PHASE 4: Build Talk Matching Map")
        print("=" * 60)

    # Query all talks from gc.db
    talks_query = """
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
    """

    gc_talks = gc_db.select(talks_query)

    if verbose:
        print(f"Found {len(gc_talks)} talks in gc.db")
        print("\nMatching talks...")

    talk_map = {}

    for gc_talk in gc_talks:
        # Try URI match first
        core_talk = core_db.select_one(
            "SELECT ID FROM talk WHERE URI_GC = ? OR URI_L = ?",
            (gc_talk["uri"], gc_talk["uri"]),
        )

        match_method = None
        if core_talk:
            match_method = "uri"
        else:
            # Fallback to data_aid match
            core_talk = core_db.select_one(
                "SELECT ID FROM talk WHERE data_aid = ?", (gc_talk["data_aid"],)
            )
            if core_talk:
                match_method = "data_aid"

        if core_talk:
            talk_map[gc_talk["data_aid"]] = {
                "core_talk_id": core_talk["ID"],
                "gc_data": gc_talk,
                "match_method": match_method,
            }
            stats["talks_matched"] += 1

            if verbose:
                print(
                    f"  ✓ {gc_talk['title']} (ID: {core_talk['ID']}, method: {match_method})"
                )
        else:
            # No match found
            unmatched_talks.append(
                {
                    "data_aid": gc_talk["data_aid"],
                    "uri": gc_talk["uri"],
                    "title": gc_talk["title"],
                    "speaker": (
                        gc_talk["speaker_subtitle"]
                        if gc_talk["speaker_subtitle"]
                        else "Unknown"
                    ),
                }
            )
            stats["talks_unmatched"] += 1

            if verbose:
                print(f"  ✗ {gc_talk['title']} (no match in core.db)")

    if verbose:
        print(f"\nMatching complete:")
        print(f"  - Matched: {stats['talks_matched']}")
        print(f"  - Unmatched: {stats['talks_unmatched']}")
        print()

    return talk_map


# ============================================================================
# PHASE 5: UPDATE CORE.TALK TABLE
# ============================================================================


def update_core_talk_table(
    gc_db: Database,
    core_db: Database,
    talk_map: Dict[str, Dict],
    stats: Dict[str, int],
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Update core.talk table with speaker_role_id, URIs, and data_aid.

    Args:
        gc_db: Database connection to gc.db
        core_db: Database connection to core.db
        talk_map: Talk matching map from build_talk_matching_map
        stats: Statistics dictionary to update
        verbose: Print detailed logging
        dry_run: Don't execute updates
    """
    if verbose:
        print("=" * 60)
        print("PHASE 5: Update core.talk Table")
        print("=" * 60)

    for gc_data_aid, match_info in talk_map.items():
        core_talk_id = match_info["core_talk_id"]
        gc_talk = match_info["gc_data"]

        # Get HTML content for speaker role extraction
        html_row = gc_db.select_one(
            "SELECT content_html FROM subitem_content WHERE subitem_id = ?",
            (gc_data_aid,),
        )

        speaker_role_id = None
        role_text = None
        if html_row:
            role_text = extract_speaker_role(html_row["content_html"])
            if role_text:
                speaker_role_id = get_or_create_speaker_role_id(
                    core_db, role_text, stats, verbose
                )

        # Update talk table
        update_sql = """
            UPDATE talk
            SET
                speaker_role_id = ?,
                URI_GC = ?,
                URI_L = ?,
                data_aid = ?
            WHERE ID = ?
        """

        if dry_run:
            if verbose:
                print(f"  [DRY RUN] Would update talk ID {core_talk_id}:")
                print(f"    Title: {gc_talk['title']}")
                print(f"    Speaker Role: {role_text}")
                print(f"    URI: {gc_talk['uri']}")
                print(f"    Data-Aid: {gc_data_aid}")
        else:
            core_db.execute(
                update_sql,
                (
                    speaker_role_id,
                    gc_talk["uri"],
                    gc_talk["uri"],
                    gc_data_aid,
                    core_talk_id,
                ),
            )

            if verbose:
                print(f"  ✓ Updated talk ID {core_talk_id}: {gc_talk['title']}")

        stats["talks_updated"] += 1

    if verbose:
        print(f"\nUpdated {stats['talks_updated']} talks in core.talk")
        print()


# ============================================================================
# PHASE 6: ADD TEXTPREVIEW COLUMN TO TALKBODY TABLE
# ============================================================================


def create_and_populate_talk_preview(
    content_db: Database,
    talk_map: Dict[str, Dict],
    json_files: Dict,
    stats: Dict[str, int],
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Add TextPreview column to talkbody table and populate with preview data.

    Args:
        content_db: Database connection to content.db
        talk_map: Talk matching map
        json_files: Dictionary of loaded JSON files
        stats: Statistics dictionary to update
        verbose: Print detailed logging
        dry_run: Don't execute updates
    """
    if verbose:
        print("=" * 60)
        print("PHASE 6: Add TextPreview Column to talkbody Table")
        print("=" * 60)

    # Add TextPreview column if it doesn't exist (idempotent)
    if not dry_run:
        try:
            content_db.execute("ALTER TABLE talkbody ADD COLUMN TextPreview TEXT")
            if verbose:
                print("✓ Added TextPreview column to talkbody table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                if verbose:
                    print("✓ TextPreview column already exists")
            else:
                raise
    else:
        if verbose:
            print("[DRY RUN] Would add TextPreview column to talkbody table")

    # Update preview data
    preview_entries = []
    for gc_data_aid, match_info in talk_map.items():
        core_talk_id = match_info["core_talk_id"]
        gc_talk = match_info["gc_data"]

        if gc_talk.get("preview"):
            if dry_run:
                if verbose:
                    print(
                        f"  [DRY RUN] Would update preview for talk ID {core_talk_id}"
                    )
            else:
                content_db.execute(
                    "UPDATE talkbody SET TextPreview = ? WHERE TalkID = ?",
                    (gc_talk["preview"], core_talk_id),
                )

            stats["previews_added"] += 1

            # Build entry for JSON
            preview_entries.append(
                {
                    "talkID": core_talk_id,
                    "title": gc_talk["title"],
                    "uri": gc_talk["uri"],
                    "preview": gc_talk["preview"],
                }
            )

    # Update talk_previews.json
    preview_map = {p["talkID"]: p for p in json_files["talk_previews"]}
    for entry in preview_entries:
        preview_map[entry["talkID"]] = entry

    updated_previews = list(preview_map.values())
    updated_previews.sort(key=lambda x: x["talkID"])

    if not dry_run:
        save_json("db/one-off-migration/talk_previews.json", updated_previews)
        if verbose:
            print(f"✓ Added {stats['previews_added']} previews to database")
            print(
                f"✓ Updated talk_previews.json ({len(updated_previews)} total entries)"
            )
    else:
        print(f"[DRY RUN] Would add {stats['previews_added']} previews")

    print()


# ============================================================================
# PHASE 7: UPDATE TALK_TOPIC AND CONFERENCE_TOPIC TABLES
# ============================================================================


def update_talk_topics(
    gc_db: Database,
    core_db: Database,
    talk_map: Dict[str, Dict],
    stats: Dict[str, int],
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Update talk_topic and conference_topic tables.

    Args:
        gc_db: Database connection to gc.db
        core_db: Database connection to core.db
        talk_map: Talk matching map
        stats: Statistics dictionary to update
        verbose: Print detailed logging
        dry_run: Don't execute updates
    """
    if verbose:
        print("=" * 60)
        print("PHASE 7: Update talk_topic and conference_topic Tables")
        print("=" * 60)

    # Query topics and relationships
    topics_query = """
        SELECT
            t.topicId AS topic_slug,
            t.name AS topic_name,
            ts.subitemId AS data_aid
        FROM Topic t
        JOIN TopicSubitem ts ON t.id = ts.topicId
        ORDER BY t.name, ts.subitemId
    """

    gc_topic_relationships = gc_db.select(topics_query)

    if verbose:
        print(f"Found {len(gc_topic_relationships)} topic-talk relationships in gc.db")

    topic_id_cache = {}

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
                "SELECT id FROM conference_topic WHERE name = ?", (topic_name,)
            )

            if existing_topic:
                topic_id_cache[topic_name] = existing_topic["id"]
                if verbose:
                    print(
                        f"  Found existing topic: {topic_name} (ID: {existing_topic['id']})"
                    )
            else:
                # Insert new topic
                if dry_run:
                    # For dry run, use placeholder ID
                    topic_id_cache[topic_name] = -1
                    if verbose:
                        print(f"  [DRY RUN] Would create topic: {topic_name}")
                else:
                    core_db.execute(
                        "INSERT INTO conference_topic (name, slug) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
                        (topic_name, topic_slug),
                    )
                    result = core_db.select_one(
                        "SELECT id FROM conference_topic WHERE name = ?", (topic_name,)
                    )
                    topic_id_cache[topic_name] = result["id"]
                    stats["topics_added"] += 1
                    if verbose:
                        print(f"  ✓ Created topic: {topic_name} (ID: {result['id']})")

        topic_id = topic_id_cache[topic_name]
        content_identifier = talk_map[gc_data_aid]["gc_data"]["uri"]

        # Insert talk_topic relationship
        if dry_run:
            if verbose:
                print(
                    f"    [DRY RUN] Would link talk {core_talk_id} to topic {topic_name}"
                )
        else:
            core_db.execute(
                """
                INSERT INTO talk_topic (topic_id, talk_id, content_identifier)
                VALUES (?, ?, ?)
                ON CONFLICT(topic_id, content_identifier) DO NOTHING
                """,
                (topic_id, core_talk_id, content_identifier),
            )

        stats["talk_topics_added"] += 1

    if verbose:
        print(f"\n✓ Added {stats['topics_added']} new topics")
        print(f"✓ Added {stats['talk_topics_added']} talk-topic relationships")
        print()


# ============================================================================
# PHASE 8: UPDATE CONFERENCE_TOPICS.JSON
# ============================================================================


def update_conference_topics_json(
    gc_db: Database,
    talk_map: Dict[str, Dict],
    json_files: Dict,
    conference_title: str,
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Update conference_topics.json with new entries.

    Args:
        gc_db: Database connection to gc.db
        talk_map: Talk matching map
        json_files: Dictionary of loaded JSON files
        conference_title: Conference title (e.g., "Apr 2025")
        verbose: Print detailed logging
        dry_run: Don't write files
    """
    if verbose:
        print("=" * 60)
        print("PHASE 8: Update conference_topics.json")
        print("=" * 60)

    # Query topics and relationships
    topics_query = """
        SELECT
            t.topicId AS topic_slug,
            t.name AS topic_name,
            ts.subitemId AS data_aid
        FROM Topic t
        JOIN TopicSubitem ts ON t.id = ts.topicId
        ORDER BY t.name, ts.subitemId
    """

    gc_topic_relationships = gc_db.select(topics_query)

    # Create topic lookup
    topics_map = {t["topic"]: t for t in json_files["conference_topics"]}

    entries_added = 0

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
            "meta": conference_title,
            "secondaryMeta": gc_talk["speaker_subtitle"],
            "uri": gc_talk["uri"],
            "subtype": "secondary",
        }

        # Add to topic
        if topic_name not in topics_map:
            topics_map[topic_name] = {"topic": topic_name, "entries": []}

        # Check if entry already exists (by uri)
        existing_uris = {e["uri"] for e in topics_map[topic_name]["entries"]}
        if entry["uri"] not in existing_uris:
            topics_map[topic_name]["entries"].append(entry)
            entries_added += 1

    # Convert back to list and sort
    updated_topics = list(topics_map.values())
    updated_topics.sort(key=lambda x: x["topic"])

    if not dry_run:
        save_json("db/one-off-migration/conference_topics.json", updated_topics)
        if verbose:
            print(f"✓ Added {entries_added} new entries to conference_topics.json")
            print(f"  Total topics: {len(updated_topics)}")
    else:
        print(f"[DRY RUN] Would add {entries_added} entries to conference_topics.json")

    print()


# ============================================================================
# PHASE 9: UPDATE TALK_METADATA.JSON
# ============================================================================


def update_talk_metadata_json(
    gc_db: Database,
    talk_map: Dict[str, Dict],
    json_files: Dict,
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Update talk_metadata.json with new entries.

    Args:
        gc_db: Database connection to gc.db
        talk_map: Talk matching map
        json_files: Dictionary of loaded JSON files
        verbose: Print detailed logging
        dry_run: Don't write files
    """
    if verbose:
        print("=" * 60)
        print("PHASE 9: Update talk_metadata.json")
        print("=" * 60)

    # Create lookup by talkID
    metadata_map = {m["talkID"]: m for m in json_files["talk_metadata"]}

    entries_added = 0

    for gc_data_aid, match_info in talk_map.items():
        core_talk_id = match_info["core_talk_id"]
        gc_talk = match_info["gc_data"]

        # Get speaker role text
        html_row = gc_db.select_one(
            "SELECT content_html FROM subitem_content WHERE subitem_id = ?",
            (gc_data_aid,),
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
            "data_aid": gc_data_aid,
        }
        entries_added += 1

    # Convert to list and sort
    updated_metadata = list(metadata_map.values())
    updated_metadata.sort(key=lambda x: x["talkID"])

    if not dry_run:
        save_json("db/one-off-migration/talk_metadata.json", updated_metadata)
        if verbose:
            print(f"✓ Updated talk_metadata.json with {entries_added} entries")
            print(f"  Total entries: {len(updated_metadata)}")
    else:
        print(f"[DRY RUN] Would update talk_metadata.json with {entries_added} entries")

    print()


# ============================================================================
# PHASE 10: GENERATE REPORTS
# ============================================================================


def generate_reports(
    stats: Dict[str, int],
    unmatched_talks: List[Dict],
    conference_key: str,
    conference_title: str,
    dry_run: bool = False,
) -> None:
    """
    Generate summary statistics and inconsistency reports.

    Args:
        stats: Statistics dictionary
        unmatched_talks: List of unmatched talks
        conference_key: Conference key (e.g., "2025-04")
        conference_title: Conference title (e.g., "Apr 2025")
        dry_run: Dry run mode
    """
    print("\n" + "=" * 60)
    print("UPDATE COMPLETE - Summary Statistics")
    print("=" * 60)
    print(f"Conference: {conference_key} ({conference_title})")
    if dry_run:
        print("\n*** DRY RUN MODE - No changes were written ***")
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
    print(f"  - api/sessions.json")
    print(f"  - db/one-off-migration/conference_topics.json")
    print(f"  - db/one-off-migration/talk_metadata.json")
    print(f"  - db/one-off-migration/talk_previews.json")
    print("=" * 60)

    # Unmatched talks report
    if unmatched_talks:
        print("\n" + "=" * 60)
        print("INCONSISTENCY REPORT - Unmatched Talks")
        print("=" * 60)
        print(f"Found {len(unmatched_talks)} talks in gc.db with no match in core.db\n")

        for i, talk in enumerate(unmatched_talks, 1):
            print(f"{i}. {talk['title']}")
            print(f"   Speaker: {talk['speaker']}")
            print(f"   URI: {talk['uri']}")
            print(f"   Data-Aid: {talk['data_aid']}")
            print()

        # Save to file
        if not dry_run:
            report_file = f"./unmatched_talks_{conference_key}.json"
            save_json(report_file, unmatched_talks)
            print(f"Full report saved to: {report_file}")
        else:
            print(
                f"[DRY RUN] Would save report to: unmatched_talks_{conference_key}.json"
            )

        print("=" * 60)


# ============================================================================
# MAIN FUNCTION
# ============================================================================


def main():
    """Main entry point for UPDATE.py script."""
    # Force UTF-8 encoding for stdout (fixes Windows file redirection)
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    # Argument parsing
    parser = argparse.ArgumentParser(
        description="Update core database from conference database"
    )
    parser.add_argument(
        "gc_db_path", help="Path to conference-specific database (gc.db)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate without writing"
    )
    parser.add_argument("--verbose", action="store_true", help="Detailed logging")

    args = parser.parse_args()

    # Initialize statistics
    stats = {
        "talks_matched": 0,
        "talks_unmatched": 0,
        "talks_updated": 0,
        "topics_added": 0,
        "talk_topics_added": 0,
        "speaker_roles_created": 0,
        "previews_added": 0,
    }

    unmatched_talks = []

    try:
        # Phase 1: Initialize
        gc_db, core_db, content_db, json_files = initialize(args.gc_db_path, args.verbose)

        # Phase 2: Extract conference metadata
        conference_key, conference_title, _ = extract_conference_metadata(
            gc_db, args.verbose
        )

        # Phase 3: Process sessions
        process_sessions(gc_db, json_files, conference_key, args.verbose, args.dry_run)

        # Phase 4: Build talk matching map
        talk_map = build_talk_matching_map(
            gc_db, core_db, stats, unmatched_talks, args.verbose
        )

        # Phase 5: Update core.talk table
        update_core_talk_table(
            gc_db, core_db, talk_map, stats, args.verbose, args.dry_run
        )

        # Phase 6: Add TextPreview column to talkbody table
        create_and_populate_talk_preview(
            content_db, talk_map, json_files, stats, args.verbose, args.dry_run
        )

        # Phase 7: Update talk_topic and conference_topic tables
        update_talk_topics(gc_db, core_db, talk_map, stats, args.verbose, args.dry_run)

        # Phase 8: Update conference_topics.json
        update_conference_topics_json(
            gc_db, talk_map, json_files, conference_title, args.verbose, args.dry_run
        )

        # Phase 9: Update talk_metadata.json
        update_talk_metadata_json(
            gc_db, talk_map, json_files, args.verbose, args.dry_run
        )

        # Phase 10: Generate reports
        generate_reports(
            stats, unmatched_talks, conference_key, conference_title, args.dry_run
        )

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
