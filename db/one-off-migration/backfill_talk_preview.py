#!/usr/bin/env python3
"""
Backfill script for populating talk previews.

This script migrates talk preview data from JSON file into the core.db database. It will:

- Populate talk_metadata.talk_preview in core.52.db from JSON data
- Use UPSERT statements to safely handle re-runs

Usage:
  pipenv run py db/one-off-migration/backfill_talk_preview.py [--db ./db/core.52.db] [--input talk_previews.json] [--dry-run]

Notes:
- This script is idempotent and safe to re-run
- Writes to core.52.db talk_metadata.talk_preview (NOT content.52.db talkbody.TextPreview)
- Expects JSON format: [{"TalkID": 123, "preview": "text..."}, ...]
  or {"123": "preview text...", "456": "preview text..."}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Union

# Ensure Unicode output works on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add parent directory to path for importing Database
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(parent_dir)
sys.path.insert(0, root_dir)

migration_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, migration_dir)

from db import Database, CORE_DB_PATH
from create_talk_metadata_table import upsert_talk_metadata


def ensure_talk_metadata_table(db: Database) -> None:
    """Ensure talk_metadata table exists in core.52.db (idempotent)."""
    from create_talk_metadata_table import create_table
    create_table(db)


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


def populate_previews(
    db: Database, previews_data: List[Dict], dry_run: bool = False
) -> tuple[int, int]:
    """
    Write talk previews to core.52.db talk_metadata.talk_preview.

    Args:
        db:            Writable Database instance (core.52.db).
        previews_data: List of preview dicts from JSON.
        dry_run:       If True, don't write changes.

    Returns:
        Tuple of (previews_inserted, previews_failed)
    """
    previews_inserted = 0
    previews_failed = 0
    total = len(previews_data)

    print(f"\nProcessing {total} talk previews...")

    for i, preview_data in enumerate(previews_data, 1):
        talk_id = preview_data.get("TalkID") or preview_data.get("talkID")
        preview = preview_data.get("preview")

        if talk_id is None or preview is None:
            print(f"  ⚠️  [{i}/{total}] Missing TalkID or preview in entry")
            previews_failed += 1
            continue

        if dry_run:
            print(f"  [{i}/{total}] [DRY-RUN] Would upsert talk_preview for TalkID {talk_id}")
            previews_inserted += 1
            continue

        try:
            upsert_talk_metadata(db, talk_id, talk_preview=preview)
            previews_inserted += 1
            if i % 100 == 0 or i == total:
                print(f"  Progress: {i}/{total} ({(i/total)*100:.1f}%)")
        except Exception as e:
            print(f"  ⚠️  Error upserting TalkID {talk_id}: {e}")
            previews_failed += 1

    return previews_inserted, previews_failed


def print_statistics(db: Database) -> None:
    """Print coverage statistics from core.52.db talk_metadata."""
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    rows = db.select("SELECT COUNT(*) as cnt FROM talk_metadata WHERE talk_preview IS NOT NULL")
    total_previews = rows[0]["cnt"] if rows else 0
    print(f"\nTotal talk previews in talk_metadata: {total_previews}")

    rows = db.select("SELECT COUNT(*) as cnt FROM talk_metadata")
    total_rows = rows[0]["cnt"] if rows else 0
    percentage = (total_previews / max(total_rows, 1)) * 100
    print(f"Total rows in talk_metadata: {total_rows}")
    print(f"Coverage: {percentage:.1f}%")

    rows = db.select("SELECT AVG(LENGTH(talk_preview)) as avg FROM talk_metadata WHERE talk_preview IS NOT NULL")
    avg_length = rows[0]["avg"] if rows else None
    if avg_length:
        print(f"Average preview length: {avg_length:.0f} characters")

    sample = db.select(
        "SELECT talk_id, SUBSTR(talk_preview, 1, 100) as snippet FROM talk_metadata WHERE talk_preview IS NOT NULL LIMIT 5"
    )
    if sample:
        print("\nSample previews (first 5):")
        for row in sample:
            print(f"  TalkID {row['talk_id']}")
            print(f"    \"{row['snippet']}...\"")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill talk previews into core.52.db talk_metadata table"
    )
    parser.add_argument(
        "--db",
        default=CORE_DB_PATH,
        help="Path to core.52.db (default: CORE_DB_PATH from db module)",
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

    db_path = args.db

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

    if not os.path.exists(db_path):
        print(f"\n❌ Error: Database not found at {db_path}")
        sys.exit(1)

    if not os.path.exists(input_path):
        print(f"\n❌ Error: Input file not found at {input_path}")
        sys.exit(1)

    start_time = time.time()

    try:
        print(f"\nLoading data from {input_path}...")
        previews_data = load_json_data(input_path)
        print(f"✓ Loaded {len(previews_data)} talk previews")

        db = Database(db_path, timeout=60, read_only=args.dry_run)

        if not args.dry_run:
            ensure_talk_metadata_table(db)

        if args.dry_run:
            print("\n[DRY-RUN MODE] No changes will be written")

        print("\n" + "=" * 60)
        print("Writing talk_preview to talk_metadata...")
        print("=" * 60)

        inserted, failed = populate_previews(db, previews_data, dry_run=args.dry_run)

        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)
        print(f"Previews inserted/updated: {inserted}")
        print(f"Previews failed/skipped: {failed}")
        print(f"Elapsed time: {elapsed:.2f}s")

        if not args.dry_run:
            print_statistics(db)
            print("\n✓ Migration complete!")
        else:
            print("\n[DRY-RUN] No changes were written to database")

    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n❌ Error: Invalid JSON in input file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
