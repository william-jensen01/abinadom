#!/usr/bin/env python3
"""
Backfill talk kicker text from talkbody HTML.

Extracts the "kicker" teaser subtitle from conference talk HTML and stores it
in the Kicker column of the talk table in core.52.db.

Targets all talks with Corpus IN ('E', 'G') (~5,838 talks).

Usage:
    pipenv run py db/one-off-migration/backfill_talk_kicker.py [options]

Examples:
    pipenv run py db/one-off-migration/backfill_talk_kicker.py --talk-ids 2000 2001 2002
    pipenv run py db/one-off-migration/backfill_talk_kicker.py --dry-run
    pipenv run py db/one-off-migration/backfill_talk_kicker.py
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Optional

from bs4 import BeautifulSoup

# Ensure Unicode output works on Windows (cp1252 can't encode ✓, ⚠️, etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add parent directories to path for importing Database
db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(db_dir)
sys.path.insert(0, root_dir)

from db import Database, CONTENT_DB_PATH, CORE_DB_PATH

migration_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, migration_dir)
from create_talk_metadata_table import upsert_talk_metadata


def ensure_kicker_column_exists(core_db: Database) -> None:
    """Add Kicker column to talk table in core.52.db if not present. Idempotent."""
    try:
        core_db.execute("ALTER TABLE talk ADD COLUMN Kicker TEXT")
        print("  ✓ Kicker column added to talk table in core.52.db")
    except Exception as e:
        if "duplicate column name" in str(e).lower():
            print("  ✓ Kicker column already exists in talk table")
        else:
            raise


def fetch_eligible_talk_ids(
    core_db: Database, talk_ids: list[int] | None = None
) -> list[int]:
    """Return list of eligible talk IDs.

    If talk_ids is provided, returns those IDs (no corpus filter).
    Otherwise returns all IDs with Corpus IN ('E', 'G').
    """
    if talk_ids:
        placeholders = ",".join(["?"] * len(talk_ids))
        rows = core_db.select(
            f"SELECT ID FROM talk WHERE ID IN ({placeholders}) ORDER BY ID",
            talk_ids,
        )
    else:
        rows = core_db.select(
            "SELECT ID FROM talk WHERE Corpus IN ('E', 'G') ORDER BY ID"
        )
    return [row["ID"] for row in rows]


def extract_kicker(html: str) -> tuple[str | None, str]:
    """Parse TextRaw HTML and return (kicker_text, pattern_name).

    Tries 4 patterns in order:
        1. kicker_p_header    — header > p.kicker            (2020+)
        2. blockquote_intro_p — blockquote.intro > p.intro   (2018)
        3. blockquote_intro_div — blockquote.intro > div.kicker (2015)
        4. div_kicker_body    — div.kicker (not inside blockquote.intro) (1971-2015)

    Returns (None, 'not_found') if no pattern matched.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Pattern 1: header > p.kicker
    header = soup.find("header")
    if header:
        p = header.find("p", class_="kicker")
        if p:
            text = p.get_text(strip=True)
            if text:
                return text, "kicker_p_header"

    # Pattern 2: blockquote.intro > p.intro
    blockquote_intro = soup.find("blockquote", class_="intro")
    if blockquote_intro:
        p = blockquote_intro.find("p", class_="intro")
        if p:
            text = p.get_text(strip=True)
            if text:
                return text, "blockquote_intro_p"

    # Pattern 3: blockquote.intro > div.kicker
    if blockquote_intro:
        div = blockquote_intro.find("div", class_="kicker")
        if div:
            text = div.get_text(strip=True)
            if text:
                return text, "blockquote_intro_div"

    # Pattern 4: div.kicker not inside blockquote.intro
    for div in soup.find_all("div", class_="kicker"):
        if div.find_parent("blockquote", class_="intro"):
            continue
        text = div.get_text(strip=True)
        if text:
            return text, "div_kicker_body"

    return None, "not_found"


def process_talks(
    core_db: Database,
    content_conn: sqlite3.Connection,
    ids: list[int],
    batch_size: int,
    dry_run: bool,
    force: bool,
    stats: dict,
) -> None:
    """Batch-process talks: read TextRaw, extract kicker, write to core.52.db."""
    total = len(ids)

    for batch_start in range(0, total, batch_size):
        batch_ids = ids[batch_start : batch_start + batch_size]
        placeholders = ",".join(["?"] * len(batch_ids))

        # Read TextRaw from content.52.db
        cursor = content_conn.execute(
            f"SELECT TalkID, TextRaw FROM talkbody WHERE TalkID IN ({placeholders})",
            batch_ids,
        )
        content_rows = {row[0]: row[1] for row in cursor.fetchall()}

        # Read existing kicker values from talk_metadata (authoritative source)
        existing_rows = core_db.select(
            f"SELECT talk_id, kicker FROM talk_metadata WHERE talk_id IN ({placeholders})",
            batch_ids,
        )
        existing_kickers = {row["talk_id"]: row["kicker"] for row in existing_rows}

        batch_updates = []

        for talk_id in batch_ids:
            stats["total"] += 1

            if talk_id not in content_rows:
                print(f"  ⚠️  TalkID {talk_id}: not found in talkbody (no TextRaw)")
                stats["not_found"] += 1
                stats["pattern_counts"]["not_found"] += 1
                continue

            # Skip if already populated and not forcing
            if existing_kickers.get(talk_id) is not None and not force:
                stats["skipped"] += 1
                continue

            html = content_rows[talk_id]
            if not html:
                stats["not_found"] += 1
                stats["pattern_counts"]["not_found"] += 1
                continue

            try:
                kicker_text, pattern = extract_kicker(html)
            except Exception as e:
                print(f"  ⚠️  TalkID {talk_id}: extraction error — {e}")
                stats["errors"] += 1
                continue

            stats["pattern_counts"][pattern] += 1

            if kicker_text:
                stats["found"] += 1
                batch_updates.append((kicker_text, talk_id))
            else:
                stats["not_found"] += 1

        # Write batch to both talk.Kicker and talk_metadata.kicker
        if batch_updates and not dry_run:
            try:
                for kicker_text, talk_id in batch_updates:
                    core_db.execute(
                        "UPDATE talk SET Kicker = ? WHERE ID = ?",
                        [kicker_text, talk_id],
                    )
                    upsert_talk_metadata(core_db, talk_id, kicker=kicker_text)
                stats["written"] += len(batch_updates)
                print(f"  ✓ Committed batch of {len(batch_updates)} updates")
            except Exception as e:
                print(f"  ❌ Batch write failed: {e}")
                raise

        processed = min(batch_start + batch_size, total)
        pct = (processed / total) * 100
        print(
            f"  Progress: {processed}/{total} ({pct:.1f}%)"
            f"  found={stats['found']} not_found={stats['not_found']}"
            f" skipped={stats['skipped']} errors={stats['errors']}"
        )


def print_pattern_distribution(stats: dict) -> None:
    """Print per-pattern hit-count table."""
    print("\nPattern Distribution:")
    patterns = [
        "kicker_p_header",
        "blockquote_intro_p",
        "blockquote_intro_div",
        "div_kicker_body",
        "not_found",
    ]
    for p in patterns:
        count = stats["pattern_counts"].get(p, 0)
        print(f"  {p:<28} {count}")


def print_statistics(core_db: Database) -> None:
    """Print post-run coverage and sample kickers from talk table."""
    rows = core_db.select("SELECT COUNT(*) as cnt FROM talk WHERE Corpus IN ('E', 'G')")
    total_eligible = rows[0]["cnt"] if rows else 0

    rows = core_db.select(
        "SELECT COUNT(*) as cnt FROM talk_metadata tm"
        " JOIN talk t ON tm.talk_id = t.ID"
        " WHERE t.Corpus IN ('E', 'G') AND tm.kicker IS NOT NULL"
    )
    total_with_kicker = rows[0]["cnt"] if rows else 0

    pct = (total_with_kicker / max(total_eligible, 1)) * 100
    print(
        f"\nCoverage: {total_with_kicker}/{total_eligible} ({pct:.1f}%) talks have a Kicker"
    )

    sample = core_db.select(
        "SELECT talk_id, kicker FROM talk_metadata WHERE kicker IS NOT NULL ORDER BY talk_id LIMIT 5"
    )
    if sample:
        print("\nSample kickers (first 5):")
        for row in sample:
            snippet = row["kicker"][:80] if row["kicker"] else ""
            print(f"  TalkID {row['talk_id']}: \"{snippet}\"")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill kicker text into core.52.db talk table"
    )
    parser.add_argument(
        "--content-db",
        default=CONTENT_DB_PATH,
        help="Path to content.52.db (default: CONTENT_DB_PATH)",
    )
    parser.add_argument(
        "--core-db",
        default=CORE_DB_PATH,
        help="Path to core.52.db (default: CORE_DB_PATH)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=500,
        help="Batch size (default: 500)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts only, no writes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing non-NULL Kicker values",
    )
    parser.add_argument(
        "--talk-ids",
        type=int,
        nargs="+",
        metavar="INT",
        help="Target specific TalkIDs (overrides corpus filter)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 80)
    print("Backfill Talk Kicker")
    print("=" * 80)
    print(f"Content DB: {args.content_db}")
    print(f"Core DB:    {args.core_db}")
    print(f"Mode:       {'DRY-RUN' if args.dry_run else 'WRITE'}")
    print("=" * 80)

    if args.force:
        print("  ⚠️  --force mode: existing Kicker values will be overwritten")

    # Open core.52.db (writable)
    core_db = Database(args.core_db, read_only=False)

    # Ensure schema
    ensure_kicker_column_exists(core_db)

    # Fetch eligible IDs
    ids = fetch_eligible_talk_ids(core_db, args.talk_ids)
    print(
        f"  ✓ Fetched {len(ids)} eligible talk IDs"
        + (" (Corpus IN ('E','G'))" if not args.talk_ids else " (--talk-ids)")
    )

    stats: dict = {
        "total": 0,
        "found": 0,
        "not_found": 0,
        "skipped": 0,
        "errors": 0,
        "written": 0,
        "pattern_counts": {
            "kicker_p_header": 0,
            "blockquote_intro_p": 0,
            "blockquote_intro_div": 0,
            "div_kicker_body": 0,
            "not_found": 0,
        },
    }

    # Open content.52.db (read-only)
    content_conn = sqlite3.connect(f"file:{args.content_db}?mode=ro", uri=True)
    content_conn.execute("PRAGMA journal_mode=WAL;")

    print(f"\nProcessing {len(ids)} talks (batch size: {args.batch})...")

    try:
        process_talks(
            core_db=core_db,
            content_conn=content_conn,
            ids=ids,
            batch_size=args.batch,
            dry_run=args.dry_run,
            force=args.force,
            stats=stats,
        )
    finally:
        content_conn.close()

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"  Total eligible:  {len(ids)}")
    print(f"  Kickers found:   {stats['found']}")
    print(f"  Not found:       {stats['not_found']}")
    print(f"  Skipped:         {stats['skipped']}")
    print(f"  Errors:          {stats['errors']}")
    print(f"  Written:         {stats['written']}")

    print_pattern_distribution(stats)

    if not args.dry_run:
        print_statistics(core_db)

    print("\n" + "=" * 80)
    print("✓ Backfill completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
