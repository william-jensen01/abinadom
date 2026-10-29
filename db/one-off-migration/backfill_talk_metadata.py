#!/usr/bin/env python3
"""
Backfill talk metadata from talk_metadata.json.

This script will:
1. Create a speaker_role table with id, role, and slug columns
2. Find each record's SCI talk by Church URI (talk_metadata.uri_gc / uri_l,
   so backfill_talk_uri.py must run first)
3. Update talk.Title and talk_metadata speaker_role_id / data_aid

Usage:
    pipenv run python db/one-off-migration/backfill_talk_metadata.py [--core-db PATH] [--metadata PATH]
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
from create_talk_metadata_table import find_talk_by_uri, load_talk_uri_index, upsert_talk_metadata

METADATA_PATH = os.path.join(migration_dir, "talk_metadata.json")


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

    print(f"\nStep 2: Loading metadata from {metadata_path}...")

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
    print("\nStep 3: Applying metadata to talk table...")
    print("-" * 80)

    uri_index = load_talk_uri_index(db)
    role_map: Dict[str, int] = {}  # normalized_role → speaker_role.id cache
    updated_count = 0
    title_updates = 0
    speaker_role_updates = 0
    data_aid_updates = 0
    not_found = []
    errors = []

    for idx, record in enumerate(metadata, start=1):
        uri = record.get("uri")
        title = record.get("title")
        speaker_role = record.get("speaker_role")
        data_aid = record.get("data_aid")

        if not uri:
            errors.append(f"Record {idx}: missing uri")
            continue

        # Church URIs with no SCI talk (reports, sustainings, ...) are expected
        talk_id = find_talk_by_uri(uri_index, uri)
        if talk_id is None:
            not_found.append(uri)
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
    print(f"  URIs with no SCI talk: {len(not_found)}")
    print(f"  Errors: {len(errors)}")

    if not_found:
        print(f"\nℹ First 10 URIs with no SCI talk (see build's match report):")
        for uri in not_found[:10]:
            print(f"    {uri}")
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
    print("\nStep 4: Verifying updates (sample)...")
    print("-" * 80)

    query = """
        SELECT
            t.ID,
            t.Title,
            sr.role as speaker_role,
            sr.slug as Speaker_Role_Slug,
            tm.data_aid
        FROM talk t
        JOIN talk_metadata tm ON tm.talk_id = t.ID
        LEFT JOIN speaker_role sr ON tm.speaker_role_id = sr.id
        WHERE {where}
        ORDER BY t.ID
        LIMIT 10
    """
    if sample_ids:
        placeholders = ",".join(["?"] * len(sample_ids))
        sample = db.select(query.format(where=f"t.ID IN ({placeholders})"), sample_ids)
    else:
        sample = db.select(
            query.format(where="tm.speaker_role_id IS NOT NULL OR tm.data_aid IS NOT NULL")
        )

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
    parser = argparse.ArgumentParser(description="Backfill Church talk metadata into the core DB")
    parser.add_argument(
        "--core-db",
        "--db",
        dest="core_db",
        default=CORE_DB_PATH,
        help="Path to core DB (default: uses CORE_DB_PATH from db module)",
    )
    parser.add_argument(
        "--metadata",
        default=METADATA_PATH,
        help="Path to talk_metadata.json (default: %(default)s)",
    )
    return parser.parse_args()


def run(core_db_path: str, metadata_path: str = METADATA_PATH) -> Dict[str, Any]:
    db = Database(core_db_path, read_only=False)
    create_speaker_role_table(db)
    stats = apply_metadata(db, load_metadata(metadata_path))
    verify_sample(db)
    return stats


def main():
    args = parse_args()

    print("=" * 80)
    print("Backfill Talk Metadata")
    print("=" * 80)
    print(f"Database: {args.core_db}")
    print(f"Metadata: {args.metadata}")
    print("=" * 80)

    stats = run(args.core_db, args.metadata)

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"  Total metadata records: {stats['total']}")
    print(f"  Talks updated: {stats['updated']}")
    print(f"    - Title updates: {stats['title_updates']}")
    print(f"    - Speaker role updates: {stats['speaker_role_updates']}")
    print(f"    - Data aid updates: {stats['data_aid_updates']}")
    print(f"  URIs with no SCI talk: {stats['not_found']}")
    print(f"  Errors: {stats['errors']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
