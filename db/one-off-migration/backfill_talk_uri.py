"""
Generate the uri variants and backfill the talk table. Correct the invalid uris with backfill_uri_corrections.json while removing non-GC URIs
"""

import argparse
import json
import sys
import os
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(db_dir)
sys.path.insert(0, root_dir)

from db import Database, CORE_DB_PATH

migration_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, migration_dir)
from create_talk_metadata_table import create_table, upsert_talk_metadata

CORRECTIONS_PATH = os.path.join(migration_dir, "talk_corrections.json")


def normalize_month_for_gc(month, year):
    """
    Normalize month to nearest General Conference (04 or 10).

    Args:
        month: Month as integer (1-12)
        year: Year as integer

    Returns:
        Tuple of (normalized_year, normalized_month)
    """
    month = int(month)
    year = int(year)
    if month == 1:
        # January goes to previous October
        return year - 1, "10"
    elif 2 <= month <= 7:
        # Feb-Jul goes to April
        return (year, "04")
    else:
        # Aug-Dec goes to October
        return (year, "10")


def extract_uri_l(url):
    """
    Extract literal URI from URL with minimal processing.
    Keeps session paths intact.

    Args:
        url: Full URL from database

    Returns:
        URI_L string or None
    """
    if not url:
        return None

    try:
        # Parse URL
        parsed = urlparse(url)
        path = parsed.path

        # Remove /study prefix if present
        if path.startswith("/study"):
            path = path[6:]  # Remove '/study'

        # Remove leading slash for consistency, then re-add
        path = path.strip("/")

        if path:
            return "/" + path

        return None

    except Exception as e:
        print(f"Error parsing URL '{url}': {e}")
        return None


def extract_uri_gc(url):
    """
    Extract General Conference URI variant with normalized dates.
    Extracts identifier from session paths.

    Args:
        url: Full URL from database

    Returns:
        URI_GC string or None
    """
    if not url:
        return None

    try:
        # Parse URL
        parsed = urlparse(url)
        path = parsed.path

        # Remove /study prefix if present
        if path.startswith("/study"):
            path = path[6:]

        # Split path into components
        parts = [p for p in path.split("/") if p]

        if len(parts) < 3:
            return None

        # Extract components: topic, year, month, identifier
        topic = parts[0]
        year = parts[1]
        month = parts[2]

        # Extract identifier (last part, after any session paths)
        identifier = parts[-1]

        # Normalize month
        try:
            normalized_year, normalized_month = normalize_month_for_gc(month, year)
        except (ValueError, TypeError):
            return None

        # Build GC URI
        uri_gc = (
            f"/general-conference/{normalized_year}/{normalized_month}/{identifier}"
        )

        return uri_gc

    except Exception as e:
        print(f"Error processing URL '{url}': {e}")
        return None


def generate_uris(db: Database):
    """
    Generate URI_L and URI_GC variants for all talks with URLs.

    Args:
        db: Database instance (must be writable)

    Returns:
        Dict with generation statistics
    """
    print("\nStep 1: Generating URI variants from talk URLs...")
    print("-" * 80)

    # Get all talks with URLs
    talks = db.select("SELECT ID, URL FROM talk WHERE URL IS NOT NULL")
    print(f"Found {len(talks)} talks with URLs")

    updated_count = 0
    uri_l_count = 0
    uri_gc_count = 0
    failed_count = 0

    for talk in talks:
        talk_id = talk["ID"]
        url = talk["URL"]

        uri_l = extract_uri_l(url)
        uri_gc = extract_uri_gc(url)

        # Write to talk_metadata (authoritative source for uri_l and uri_gc)
        upsert_talk_metadata(db, talk_id, uri_l=uri_l, uri_gc=uri_gc)

        updated_count += 1

        if uri_l:
            uri_l_count += 1
        if uri_gc:
            uri_gc_count += 1
        if not uri_l and not uri_gc:
            failed_count += 1
            print(f"⚠️  TalkID {talk_id}: Failed to generate URIs from URL: {url}")

        if updated_count % 500 == 0:
            print(f"Progress: {updated_count}/{len(talks)} talks processed")

    print("-" * 80)
    print(f"URI Generation Summary:")
    print(f"  Total talks processed: {updated_count}")
    print(f"  URI_L generated: {uri_l_count}")
    print(f"  URI_GC generated: {uri_gc_count}")
    print(f"  Failed to generate: {failed_count}")
    if updated_count > 0:
        success_rate = (updated_count - failed_count) / updated_count * 100
        print(f"  Success rate: {success_rate:.1f}%")

    return {
        "total": updated_count,
        "uri_l": uri_l_count,
        "uri_gc": uri_gc_count,
        "failed": failed_count,
    }


def load_corrections(corrections_path: str) -> List[Dict[str, Any]]:
    """
    Load corrections from JSON file.

    Args:
        corrections_path: Path to talk_corrections.json

    Returns:
        List of correction dictionaries
    """
    if not os.path.exists(corrections_path):
        print(f"⚠️  Corrections file not found: {corrections_path}")
        return []

    with open(corrections_path, "r", encoding="utf-8") as f:
        corrections = json.load(f)

    print(f"\nLoaded {len(corrections)} corrections from {corrections_path}")
    return corrections


def apply_corrections(db: Database, corrections: List[Dict[str, Any]]):
    """
    Apply corrections from JSON to the database.

    Args:
        db: Database instance (must be writable)
        corrections: List of correction dictionaries

    Returns:
        Dict with correction statistics
    """
    if not corrections:
        print("\nNo corrections to apply.")
        return {
            "total": 0,
            "gc_updates": 0,
            "l_updates": 0,
            "gc_nullified": 0,
        }

    print("\nStep 2: Applying corrections from JSON...")
    print("-" * 80)

    gc_updates = 0
    l_updates = 0
    gc_nullified = 0

    for correction in corrections:
        talk_id = correction.get("TalkID")
        correct_uri = correction.get("correct_uri")
        is_gc = correction.get("gc", False)

        if not talk_id:
            print(f"⚠️  Skipping correction: missing TalkID")
            continue

        # Apply correction to talk_metadata
        if is_gc:
            if correct_uri:
                upsert_talk_metadata(db, talk_id, uri_gc=correct_uri)
                gc_updates += 1
                print(f"✓ TalkID {talk_id}: uri_gc = {correct_uri}")
        else:
            upsert_kwargs = {}
            if correct_uri:
                upsert_kwargs["uri_l"] = correct_uri
                l_updates += 1
            upsert_kwargs["uri_gc"] = None
            gc_nullified += 1
            upsert_talk_metadata(db, talk_id, **upsert_kwargs)
            print(f"✓ TalkID {talk_id}: uri_l = {correct_uri}, uri_gc = NULL")

    print("-" * 80)
    print(f"Corrections Applied:")
    print(f"  URI_GC updates: {gc_updates}")
    print(f"  URI_L updates: {l_updates}")
    print(f"  URI_GC nullified: {gc_nullified}")

    return {
        "total": len(corrections),
        "gc_updates": gc_updates,
        "l_updates": l_updates,
        "gc_nullified": gc_nullified,
    }


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Backfill URI variants into talk_metadata")
    parser.add_argument(
        "--core-db",
        "--db",
        dest="core_db",
        default=CORE_DB_PATH,
        help="Path to core DB (default: CORE_DB_PATH from db module)",
    )
    parser.add_argument("--corrections", default=CORRECTIONS_PATH)
    return parser.parse_args()


def run(core_db_path: str, corrections_path: str = CORRECTIONS_PATH) -> Dict[str, Any]:
    """Generate uri_l/uri_gc for every talk with a URL, then apply corrections."""
    db = Database(core_db_path, read_only=False)
    create_table(db)
    gen_stats = generate_uris(db)
    corr_stats = apply_corrections(db, load_corrections(corrections_path))
    return {"generate": gen_stats, "corrections": corr_stats}


def main():
    args = parse_args()

    print("=" * 80)
    print("Backfill Talk URIs and Corrections")
    print("=" * 80)
    print(f"Database: {args.core_db}")
    print(f"Corrections: {args.corrections}")
    print("=" * 80)

    stats = run(args.core_db, args.corrections)
    gen_stats, corr_stats = stats["generate"], stats["corrections"]

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"URI Generation:")
    print(f"  Total talks: {gen_stats['total']}")
    print(f"  URI_L generated: {gen_stats['uri_l']}")
    print(f"  URI_GC generated: {gen_stats['uri_gc']}")
    print(f"  Failed: {gen_stats['failed']}")
    print(f"\nCorrections Applied:")
    print(f"  Total corrections: {corr_stats['total']}")
    print(f"  URI_GC updated: {corr_stats['gc_updates']}")
    print(f"  URI_L updated: {corr_stats['l_updates']}")
    print(f"  URI_GC nullified: {corr_stats['gc_nullified']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
