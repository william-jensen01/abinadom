#!/usr/bin/env python3
"""
Backfill talk metadata from talk_metadata.json.

This script will:
1. Create a speaker_role table with id, role, and role_slug columns
2. Extract unique speaker roles from metadata and populate the speaker_role table
3. Add speaker_role_id and data_aid columns to the talk table
4. Update the talk table with title, speaker_role_id, and data_aid for each talk

Usage:
    python backfill_talk_metadata.py <db_path> <metadata_json_path>

Example:
    python backfill_talk_metadata.py ../test/test.core.52.db talk_metadata.json
"""

import argparse
import json
import sys
import os
import re
from typing import List, Dict, Any, Optional
import sqlite3

# Add parent directories to path for importing Database
db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(db_dir)
sys.path.insert(0, root_dir)

from db import Database, CORE_DB_PATH

migration_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, migration_dir)
from create_talk_metadata_table import upsert_talk_metadata


def title_case_role(text: str) -> str:
    """
    Convert role text to proper title case.

    Capitalizes all words except articles and prepositions (unless they're the first word).

    Args:
        text: Input text (e.g., "recently released as relief society general president")

    Returns:
        Title-cased text (e.g., "Recently Released as Relief Society General President")
    """
    if not text:
        return ""

    # Words that should remain lowercase (unless first word)
    lowercase_words = {
        # Articles
        "a",
        "an",
        "the",
        # Common prepositions
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "to",
        "with",
        "over",
        "under",
        "upon",
        "after",
        "before",
        # Common conjunctions that are typically lowercase in titles
        "and",
        "but",
        "or",
        "nor",
        "yet",
        "so",
    }

    words = text.split()
    result = []

    for i, word in enumerate(words):
        # Always capitalize the first word
        if i == 0:
            result.append(word.capitalize())
        # Keep lowercase words lowercase
        elif word.lower() in lowercase_words:
            result.append(word.lower())
        # Capitalize everything else
        else:
            result.append(word.capitalize())

    return " ".join(result)


def slugify(text: str) -> str:
    """
    Convert text to lowercase hyphenated slug.

    Args:
        text: Input text (e.g., "President of the Church")

    Returns:
        Slugified text (e.g., "president-of-the-church")
    """
    if not text:
        return ""

    # Convert to lowercase
    slug = text.lower()

    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)

    # Remove any characters that aren't alphanumeric or hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)

    # Remove duplicate hyphens
    slug = re.sub(r"-+", "-", slug)

    # Strip leading/trailing hyphens
    slug = slug.strip("-")

    return slug


def create_speaker_role_table(db: Database):
    """
    Create the speaker_role table if it doesn't exist.

    Args:
        db: Database instance (must be writable)
    """
    print("\nStep 1: Creating speaker_role table...")

    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS speaker_role (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL UNIQUE,
                slug TEXT NOT NULL UNIQUE
            )
        """
        )
        print("  ✓ speaker_role table created/verified")
    except Exception as e:
        print(f"  ⚠️  Error creating speaker_role table: {e}")
        raise


def add_talk_columns(db: Database):
    """
    Add speaker_role_id and data_aid columns to talk table if they don't exist.

    Args:
        db: Database instance (must be writable)
    """
    print("\nStep 2: Adding metadata columns to talk table...")

    columns_to_add = [("speaker_role_id", "INTEGER"), ("data_aid", "TEXT")]

    for col_name, col_type in columns_to_add:
        try:
            db.execute(f"ALTER TABLE talk ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ Added column: {col_name}")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print(f"  ℹ Column {col_name} already exists")
            else:
                raise

    # Add foreign key constraint note (SQLite doesn't enforce FK on ALTER TABLE)
    print("  ℹ Note: speaker_role_id references speaker_role(id)")


def load_metadata(metadata_path: str) -> List[Dict[str, Any]]:
    """
    Load metadata from JSON file.

    Args:
        metadata_path: Path to talk_metadata.json

    Returns:
        List of metadata dictionaries
    """
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

    print(f"\nStep 3: Loading metadata from {metadata_path}...")

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    print(f"  ✓ Loaded {len(metadata)} talk metadata records")
    return metadata


def _valid_role(text: str) -> Optional[str]:
    """
    Return text if it is a usable role string, otherwise None.

    Discards values that are entirely wrapped in parentheses, e.g. "(Bishop)".
    """
    if not text:
        return None
    if re.fullmatch(r"\(.*\)", text):
        return None
    return text


def get_or_create_role(
    db: Database, role_map: Dict[str, int], raw_role: str
) -> Optional[int]:
    """
    Return the speaker_role.id for *raw_role*, inserting a new row if needed.
    Updates role_map in-place as a cache.
    """
    normalized = title_case_role(raw_role)
    if not normalized:
        return None

    if normalized in role_map:
        return role_map[normalized]

    # Check DB
    existing = db.select_one(
        "SELECT id FROM speaker_role WHERE role = ?", (normalized,)
    )
    if existing:
        role_map[normalized] = existing["id"]
        return existing["id"]

    # Insert — handle slug collisions
    slug = slugify(normalized)
    candidate_slug = slug
    counter = 2
    while db.select_one(
        "SELECT id FROM speaker_role WHERE slug = ?", (candidate_slug,)
    ):
        candidate_slug = f"{slug}-{counter}"
        counter += 1

    try:
        db.execute(
            "INSERT INTO speaker_role (role, slug) VALUES (?, ?)",
            (normalized, candidate_slug),
        )
        result = db.select_one(
            "SELECT id FROM speaker_role WHERE role = ?", (normalized,)
        )
        if result:
            role_map[normalized] = result["id"]
            print(
                f"  ✓ New role: '{normalized}' → '{candidate_slug}' (id: {result['id']})"
            )
            return result["id"]
    except sqlite3.IntegrityError:
        # Race / duplicate — try to fetch
        existing = db.select_one(
            "SELECT id FROM speaker_role WHERE role = ?", (normalized,)
        )
        if existing:
            role_map[normalized] = existing["id"]
            return existing["id"]

    return None


def apply_metadata(db: Database, metadata: List[Dict[str, Any]]):
    """
    Apply metadata updates to the talk table.

    Args:
        db: Database instance (must be writable)
        metadata: List of metadata dictionaries

    Returns:
        Dict with update statistics
    """
    print("\nStep 4: Applying metadata to talk table...")
    print("-" * 80)

    role_map: Dict[str, int] = {}  # normalized_role → speaker_role.id cache
    updated_count = 0
    title_updates = 0
    speaker_role_updates = 0
    data_aid_updates = 0
    not_found = []
    errors = []

    for idx, record in enumerate(metadata, start=1):
        talk_id = record.get("talkID")
        title = record.get("title")
        speaker_role = record.get("speaker_role")
        data_aid = record.get("data_aid")

        if not talk_id:
            errors.append(f"Record {idx}: missing talkID")
            continue

        # Check if talk exists
        existing = db.select_one("SELECT ID FROM talk WHERE ID = ?", (talk_id,))

        if not existing:
            not_found.append(talk_id)
            continue

        # Title stays on talks table; enrichment fields go to talk_metadata
        title_update = None
        if title is not None:
            title_update = title
            title_updates += 1

        enrichment_kwargs = {}
        if speaker_role is not None and _valid_role(speaker_role):
            role_id = get_or_create_role(db, role_map, speaker_role)
            if role_id:
                enrichment_kwargs["speaker_role_id"] = role_id
                speaker_role_updates += 1
            else:
                errors.append(
                    f"TalkID {talk_id}: failed to get/create role '{speaker_role}'"
                )

        if data_aid is not None:
            enrichment_kwargs["data_aid"] = data_aid
            data_aid_updates += 1

        if title_update is not None or enrichment_kwargs:
            try:
                if title_update is not None:
                    db.execute(
                        "UPDATE talk SET Title = ? WHERE ID = ?",
                        (title_update, talk_id),
                    )
                if enrichment_kwargs:
                    upsert_talk_metadata(db, talk_id, **enrichment_kwargs)
                updated_count += 1

                if updated_count % 100 == 0:
                    print(f"Progress: {updated_count}/{len(metadata)} talks updated")
            except sqlite3.IntegrityError as e:
                error_detail = f"IntegrityError - {str(e)}"
                if "data_aid" in str(e).lower():
                    error_detail = f"Duplicate data_aid: {data_aid}"
                errors.append(f"TalkID {talk_id}: {error_detail}")
            except Exception as e:
                errors.append(f"TalkID {talk_id}: {str(e)}")

    print("-" * 80)
    print(f"\nMetadata Application Summary:")
    print(f"  Total records in JSON: {len(metadata)}")
    print(f"  Talks updated: {updated_count}")
    print(f"  Title updates: {title_updates}")
    print(f"  Speaker role updates: {speaker_role_updates}")
    print(f"  Data aid updates: {data_aid_updates}")
    print(f"  Talks not found: {len(not_found)}")
    print(f"  Errors: {len(errors)}")

    if not_found:
        print(f"\n⚠️  First 10 talk IDs not found in database:")
        for talk_id in not_found[:10]:
            print(f"    TalkID {talk_id}")
        if len(not_found) > 10:
            print(f"    ... and {len(not_found) - 10} more")

    if errors:
        print(f"\n⚠️  Errors encountered:")
        for error in errors[:10]:
            print(f"    {error}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")

    return {
        "total": len(metadata),
        "updated": updated_count,
        "title_updates": title_updates,
        "speaker_role_updates": speaker_role_updates,
        "data_aid_updates": data_aid_updates,
        "not_found": len(not_found),
        "errors": len(errors),
    }


def verify_sample(db: Database, sample_ids: List[int] = None):
    """
    Verify updates by showing a sample of updated records.

    Args:
        db: Database instance
        sample_ids: Optional list of specific talk IDs to verify
    """
    print("\nStep 5: Verifying updates (sample)...")
    print("-" * 80)

    if sample_ids:
        placeholders = ",".join(["?"] * len(sample_ids))
        query = f"""
            SELECT
                t.ID,
                t.Title,
                sr.role as speaker_role,
                sr.slug as Speaker_Role_Slug, 
                t.data_aid
            FROM talk t
            LEFT JOIN speaker_role sr ON t.speaker_role_id = sr.id
            WHERE t.ID IN ({placeholders})
            ORDER BY t.ID
            LIMIT 10
        """
        sample = db.select(query, sample_ids)
    else:
        query = """
            SELECT
                t.ID,
                t.Title,
                sr.role as speaker_role,
                sr.slug as Speaker_Role_Slug, 
                t.data_aid
            FROM talk t
            LEFT JOIN speaker_role sr ON t.speaker_role_id = sr.id
            WHERE t.speaker_role_id IS NOT NULL OR t.data_aid IS NOT NULL
            ORDER BY t.ID
            LIMIT 10
        """
        sample = db.select(query)

    if sample:
        print(f"\nSample of {len(sample)} updated talks:")
        for talk in sample:
            print(f"\n  TalkID: {talk['ID']}")
            title = talk["Title"]
            print(
                f"  Title: {title[:60]}..."
                if title and len(title) > 60
                else f"  Title: {title}"
            )
            print(f"  Speaker role: {talk['speaker_role']}")
            print(f"  Speaker role Slug: {talk['Speaker_Role_Slug']}")
            print(f"  Data AID: {talk['data_aid']}")
    else:
        print("  No updated records found")

    print("-" * 80)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill conference topics and references into core.db"
    )
    parser.add_argument(
        "--db",
        default=f"{CORE_DB_PATH}",
        help="Path to core.db (default: uses CORE_DB_PATH from db module)",
    )
    parser.add_argument(
        "--metadata",
        default="./db/one-off-migration/talk_metadata.json",
        help="Path to talk_metadata.json (default: ./talk_metadata.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write changes; only report what would be done",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    db_path = args.db
    metadata_path = args.metadata

    print("=" * 80)
    print("Backfill Talk Metadata")
    print("=" * 80)
    print(f"Database: {db_path}")
    print(f"Metadata: {metadata_path}")
    print("=" * 80)

    # Create writable database instance
    db = Database(db_path, read_only=False)

    # Step 1: Create speaker_role table
    create_speaker_role_table(db)

    # Step 2: Add columns to talk table
    add_talk_columns(db)

    # Step 3: Load metadata
    metadata = load_metadata(metadata_path)

    # Step 4: Apply metadata to talk table (roles inserted on demand)
    stats = apply_metadata(db, metadata)

    # Step 5: Verify with sample
    # Get first few talkIDs from metadata for verification
    sample_ids = [m.get("talkID") for m in metadata[:5] if m.get("talkID")]
    verify_sample(db, sample_ids)

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"Database Schema:")
    print(f"  speaker_role table: id, role, role_slug")
    print(f"  talk table additions: speaker_role_id (FK), data_aid")
    print(f"\nData Updates:")
    print(f"  Total metadata records: {stats['total']}")
    print(f"  Talks updated: {stats['updated']}")
    print(f"    - Title updates: {stats['title_updates']}")
    print(f"    - Speaker role updates: {stats['speaker_role_updates']}")
    print(f"    - Data aid updates: {stats['data_aid_updates']}")
    print(f"  Talks not found: {stats['not_found']}")
    print(f"  Errors: {stats['errors']}")

    if stats["updated"] > 0:
        success_rate = (stats["updated"] / stats["total"]) * 100
        print(f"\nSuccess rate: {success_rate:.1f}%")

    print("=" * 80)
    print("\n✓ Backfill completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
