#!/usr/bin/env python3
"""
Backfill script for populating talk previews.

This script migrates talk preview data from JSON file into the core.db database. It will:

- Find each record's SCI talk by Church URI (talk_metadata.uri_gc / uri_l,
  so backfill_talk_uri.py must run first)
- Populate talk_metadata.talk_preview, using UPSERT so re-runs are safe

Usage:
  pipenv run python db/one-off-migration/backfill_talk_preview.py [--core-db PATH] [--input PATH] [--dry-run]

Notes:
- Expects JSON format: [{"uri": "/general-conference/...", "preview": "text..."}, ...]
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
from create_talk_metadata_table import find_talk_by_uri, load_talk_uri_index, upsert_talk_metadata

PREVIEWS_PATH = os.path.join(migration_dir, "talk_previews.json")


def ensure_talk_metadata_table(db: Database) -> None:
    """Ensure talk_metadata table exists in core.52.db (idempotent)."""
    from create_talk_metadata_table import create_table
    create_table(db)


def load_json_data(file_path: str) -> List[Dict[str, str]]:
    """Load talk preview records ([{"uri": ..., "preview": ...}, ...])."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def populate_previews(
    db: Database, previews_data: List[Dict], dry_run: bool = False
) -> tuple[int, int, int]:
    """
    Write talk previews to talk_metadata.talk_preview.

    Args:
        db:            Database instance (writable unless dry_run).
        previews_data: List of preview dicts from JSON.
        dry_run:       If True, don't write changes.

    Returns:
        Tuple of (previews_inserted, previews_failed, uris_without_sci_talk)
    """
    uri_index = load_talk_uri_index(db)
    previews_inserted = 0
    previews_failed = 0
    no_talk = 0
    total = len(previews_data)

    print(f"\nProcessing {total} talk previews...")

    for i, preview_data in enumerate(previews_data, 1):
        uri = preview_data.get("uri")
        preview = preview_data.get("preview")

        if uri is None or preview is None:
            print(f"  ⚠️  [{i}/{total}] Missing uri or preview in entry")
            previews_failed += 1
            continue

        # Church URIs with no SCI talk (reports, sustainings, ...) are expected
        talk_id = find_talk_by_uri(uri_index, uri)
        if talk_id is None:
            no_talk += 1
            continue

        if dry_run:
            previews_inserted += 1
            continue

        try:
            upsert_talk_metadata(db, talk_id, talk_preview=preview)
            previews_inserted += 1
            if i % 500 == 0 or i == total:
                print(f"  Progress: {i}/{total} ({(i/total)*100:.1f}%)")
        except Exception as e:
            print(f"  ⚠️  Error upserting TalkID {talk_id}: {e}")
            previews_failed += 1

    return previews_inserted, previews_failed, no_talk


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
        description="Backfill talk previews into talk_metadata"
    )
    parser.add_argument(
        "--core-db",
        "--db",
        dest="core_db",
        default=CORE_DB_PATH,
        help="Path to core DB (default: CORE_DB_PATH from db module)",
    )
    parser.add_argument(
        "--input",
        "-i",
        default=PREVIEWS_PATH,
        help="Path to JSON file with talk previews (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write changes; only report what would be done",
    )
    return parser.parse_args()


def run(core_db_path: str, previews_path: str = PREVIEWS_PATH, dry_run: bool = False) -> dict:
    previews_data = load_json_data(previews_path)
    print(f"✓ Loaded {len(previews_data)} talk previews")

    db = Database(core_db_path, timeout=60, read_only=dry_run)
    if not dry_run:
        ensure_talk_metadata_table(db)

    inserted, failed, no_talk = populate_previews(db, previews_data, dry_run=dry_run)
    print(f"Previews inserted/updated: {inserted}")
    print(f"Previews failed: {failed}")
    print(f"URIs with no SCI talk: {no_talk}")
    if not dry_run:
        print_statistics(db)
    return {"inserted": inserted, "failed": failed, "no_talk": no_talk}


def main() -> None:
    """Main execution function."""
    args = parse_args()

    print("=" * 60)
    print("Talk Preview Backfill Migration")
    print("=" * 60)
    print(f"Database: {args.core_db}")
    print(f"Input: {args.input}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'WRITE'}")
    print("=" * 60)

    for path in (args.core_db, args.input):
        if not os.path.exists(path):
            print(f"\n❌ Error: not found: {path}")
            sys.exit(1)

    start_time = time.time()
    run(args.core_db, args.input, dry_run=args.dry_run)
    print(f"Elapsed time: {time.time() - start_time:.2f}s")


if __name__ == "__main__":
    main()
