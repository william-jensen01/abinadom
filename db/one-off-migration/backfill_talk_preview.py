#!/usr/bin/env python3
"""
Backfill script for populating talk previews.

This script migrates talk preview data from JSON file into the content.db database. It will:

- Add TextPreview column to talkbody table if it doesn't exist
- Populate column from JSON data containing TalkID and preview text
- Use UPDATE statements to safely handle re-runs

Usage:
  python backfill_talk_preview.py [--db ./content.db] [--input talk_previews.json] [--dry-run]

Notes:
- This script is idempotent and safe to re-run
- Updates existing talkbody rows with TextPreview column
- Will add column if it doesn't exist
- Expects JSON format: [{"TalkID": 123, "preview": "text..."}, ...]
  or {"123": "preview text...", "456": "preview text..."}
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from typing import Dict, List, Union

# Add parent directory to path for importing Database
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(parent_dir)
sys.path.insert(0, root_dir)

from db import CONTENT_DB_PATH


def ensure_column_exists(conn: sqlite3.Connection) -> None:
    """
    Add TextPreview column to talkbody table if it doesn't exist.

    Args:
        conn: SQLite connection to content.db
    """
    print("Ensuring TextPreview column exists in talkbody table...")

    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(talkbody)")
    columns = {row[1] for row in cursor.fetchall()}

    # Add TextPreview column if it doesn't exist
    if "TextPreview" not in columns:
        print("  Adding TextPreview column to talkbody table...")
        try:
            conn.execute("ALTER TABLE talkbody ADD COLUMN TextPreview TEXT")
            conn.commit()
            print("  ✓ TextPreview column added")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ✓ TextPreview column already exists")
            else:
                raise
    else:
        print("  ✓ TextPreview column already exists")

    # Create index for better query performance
    print("  Creating indexes...")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_talkbody_textpreview
        ON talkbody(TextPreview)
        """
    )

    conn.commit()
    print("  ✓ Indexes created/verified")


def load_json_data(file_path: str) -> List[Dict[str, Union[int, str]]]:
    """
    Load talk preview data from JSON file.

    Supports two formats:
    1. Array of objects: [{"TalkID": 123, "preview": "text..."}, ...]
    2. Object with TalkID keys: {"123": "preview text...", "456": "preview text..."}

    Args:
        file_path: Path to JSON file

    Returns:
        List of dictionaries with TalkID and preview keys
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle different JSON formats
    if isinstance(data, list):
        # Already in correct format
        return data
    elif isinstance(data, dict):
        # Convert object format to list format
        return [{"TalkID": int(talk_id), "preview": preview}
                for talk_id, preview in data.items()]
    else:
        raise ValueError(f"Unexpected JSON format: {type(data)}")


def update_preview(
    conn: sqlite3.Connection, talk_id: int, preview: str
) -> bool:
    """
    Update a talk preview in talkbody table (idempotent).

    Args:
        conn: SQLite connection
        talk_id: ID of the talk
        preview: Preview text

    Returns:
        True if updated successfully
    """
    try:
        cursor = conn.execute(
            """
            UPDATE talkbody
            SET TextPreview = ?
            WHERE TalkID = ?
            """,
            (preview, talk_id),
        )
        if cursor.rowcount == 0:
            print(f"  ⚠️  No talkbody row found for TalkID {talk_id}")
            return False
        return True
    except sqlite3.Error as e:
        print(f"  ⚠️  Error updating TalkID {talk_id}: {e}")
        return False


def populate_previews(
    conn: sqlite3.Connection, previews_data: List[Dict], dry_run: bool = False
) -> tuple[int, int]:
    """
    Populate talk_preview table.

    Args:
        conn: SQLite connection
        previews_data: List of preview dictionaries from JSON
        dry_run: If True, don't write changes

    Returns:
        Tuple of (previews_inserted, previews_failed)
    """
    previews_inserted = 0
    previews_failed = 0
    total = len(previews_data)

    print(f"\nProcessing {total} talk previews...")

    for i, preview_data in enumerate(previews_data, 1):
        talk_id = preview_data.get("TalkID")
        preview = preview_data.get("preview")

        if talk_id is None or preview is None:
            print(f"  ⚠️  [{i}/{total}] Missing TalkID or preview in entry")
            previews_failed += 1
            continue

        if dry_run:
            print(f"  [{i}/{total}] [DRY-RUN] Would update preview for TalkID {talk_id}")
            previews_inserted += 1
            continue

        # Update preview
        if update_preview(conn, talk_id, preview):
            previews_inserted += 1
            if i % 100 == 0 or i == total:
                print(f"  Progress: {i}/{total} ({(i/total)*100:.1f}%)")
        else:
            previews_failed += 1

    if not dry_run:
        conn.commit()

    return previews_inserted, previews_failed


def print_statistics(conn: sqlite3.Connection) -> None:
    """
    Print database statistics.

    Args:
        conn: SQLite connection
    """
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    # Total previews
    cursor = conn.execute("SELECT COUNT(*) FROM talkbody WHERE TextPreview IS NOT NULL")
    total_previews = cursor.fetchone()[0]
    print(f"\nTotal talk previews: {total_previews}")

    # Total talks in talkbody
    cursor = conn.execute("SELECT COUNT(*) FROM talkbody")
    total_talks = cursor.fetchone()[0]
    percentage = (total_previews / max(total_talks, 1)) * 100
    print(f"Total talks in talkbody: {total_talks}")
    print(f"Coverage: {percentage:.1f}%")

    # Average preview length
    cursor = conn.execute("SELECT AVG(LENGTH(TextPreview)) FROM talkbody WHERE TextPreview IS NOT NULL")
    avg_length = cursor.fetchone()[0]
    if avg_length:
        print(f"Average preview length: {avg_length:.0f} characters")

    # Sample previews
    print("\nSample previews (first 5):")
    cursor = conn.execute(
        """
        SELECT TalkID, SUBSTR(TextPreview, 1, 100) as preview_snippet
        FROM talkbody
        WHERE TextPreview IS NOT NULL
        LIMIT 5
        """
    )

    for talk_id, snippet in cursor.fetchall():
        print(f"  TalkID {talk_id}")
        print(f"    \"{snippet}...\"")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill talk previews into content.db talkbody table"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to content.db (default: uses CONTENT_DB_PATH from db module)",
    )
    parser.add_argument(
        "--input",
        "-i",
        default="talk_previews.json",
        help="Path to JSON file with talk previews (default: ./talk_previews.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write changes; only report what would be done",
    )
    return parser.parse_args()


def main() -> None:
    """Main execution function."""
    args = parse_args()

    # Use CONTENT_DB_PATH from db module or custom path if provided
    db_path = args.db if args.db else CONTENT_DB_PATH

    # Resolve input path relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, args.input)

    print("=" * 60)
    print("Talk Preview Backfill Migration")
    print("=" * 60)
    print(f"Database: {db_path}")
    print(f"Input: {input_path}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'WRITE'}")
    print("=" * 60)

    # Check if database exists
    if not os.path.exists(db_path):
        print(f"\n❌ Error: Database not found at {db_path}")
        sys.exit(1)

    # Check if input file exists
    if not os.path.exists(input_path):
        print(f"\n❌ Error: Input file not found at {input_path}")
        sys.exit(1)

    start_time = time.time()

    try:
        # Load JSON data
        print(f"\nLoading data from {input_path}...")
        previews_data = load_json_data(input_path)
        print(f"✓ Loaded {len(previews_data)} talk previews")

        # Create writable connection
        with sqlite3.connect(db_path) as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

            # Ensure column exists
            ensure_column_exists(conn)

            if args.dry_run:
                print("\n[DRY-RUN MODE] No changes will be written")

            # Populate table
            print("\n" + "=" * 60)
            print("Updating talkbody table with TextPreview...")
            print("=" * 60)

            inserted, failed = populate_previews(
                conn, previews_data, dry_run=args.dry_run
            )

            # Print results
            elapsed = time.time() - start_time
            print("\n" + "=" * 60)
            print("MIGRATION COMPLETE")
            print("=" * 60)
            print(f"Previews inserted/updated: {inserted}")
            print(f"Previews failed/skipped: {failed}")
            print(f"Elapsed time: {elapsed:.2f}s")

            if not args.dry_run:
                # Print statistics
                print_statistics(conn)
                print("\n✓ Migration complete!")
            else:
                print("\n[DRY-RUN] No changes were written to database")

    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n❌ Error: Invalid JSON in input file: {e}")
        sys.exit(1)
    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
