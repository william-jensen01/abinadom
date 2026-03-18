#!/usr/bin/env python3
"""
Backfill script for populating conference topics and their talk references.

This script migrates topic data from JSON files into the core.db database. It will:

- Create two tables if they don't exist:
  - conference_topic: stores topic names and slugs
  - talk_topic: links talks to topic via data-aid identifiers

- Populate tables from JSON data containing topics and their associated data-aids
- Use idempotent inserts (ON CONFLICT DO NOTHING) to safely handle re-runs
- Support both data_aids format and entries/uri format

Usage:
  python backfill_topics.py [--db ./core.db] [--input ../process_topic_talks/ALL_data_aids.json] [--dry-run]

Notes:
- This script is idempotent and safe to re-run
- Uses ON CONFLICT DO NOTHING to avoid duplicate inserts
- Will create tables if they don't exist
- Supports looking up talk_id from talk table using data-aid identifiers
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from typing import Dict, List, Optional

# Add parent directory to path for importing Database
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(parent_dir)
sys.path.insert(0, root_dir)

from db import Database, CORE_DB_PATH


def generate_topic_slug(topic_name: str) -> str:
    """
    Generate a URL-friendly slug from topic name.

    Args:
        topic_name: Original topic name

    Returns:
        slug (e.g., "Book of Mormon" -> "book-of-mormon")
    """
    return topic_name.lower().replace(" ", "-")


def ensure_tables_exist(conn: sqlite3.Connection) -> None:
    """
    Create conference_topic and talk_topic tables if they don't exist.

    Args:
        conn: SQLite connection to core.db
    """
    print("Ensuring tables exist...")

    # Check if tables already exist
    cursor = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name IN ('conference_topic', 'talk_topic')
        """
    )
    existing_tables = {row[0] for row in cursor.fetchall()}

    # Create conference_topic table
    if "conference_topic" not in existing_tables:
        print("  Creating conference_topic table...")
        conn.execute(
            """
            CREATE TABLE conference_topic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                slug TEXT NOT NULL UNIQUE
            )
            """
        )
        print("  ✓ conference_topic table created")
    else:
        print("  ✓ conference_topic table exists")

    # Create talk_topic table
    if "talk_topic" not in existing_tables:
        print("  Creating talk_topic table...")
        conn.execute(
            """
            CREATE TABLE talk_topic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                talk_id INTEGER NOT NULL,
                content_identifier TEXT NOT NULL,
                FOREIGN KEY (topic_id) REFERENCES conference_topic(id),
                FOREIGN KEY (talk_id) REFERENCES talk(ID),
                UNIQUE(topic_id, content_identifier)
            )
            """
        )
        print("  ✓ talk_topic table created")
    else:
        print("  ✓ talk_topic table exists")

    # Create indexes for better query performance
    print("  Creating indexes...")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_talk_topic_topic
        ON talk_topic(topic_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_talk_topic_talk
        ON talk_topic(talk_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_talk_topic_content_identifier
        ON talk_topic(content_identifier)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conference_topic_slug
        ON conference_topic(slug)
        """
    )

    conn.commit()
    print("  ✓ Indexes created/verified")


def lookup_talk_id(conn: sqlite3.Connection, uri: str) -> Optional[int]:
    """
    Look up TalkID from talk table using URI_GC.

    Args:
        conn: SQLite connection
        uri: URI to look up

    Returns:
        TalkID if found, None otherwise
    """
    try:
        cursor = conn.execute(
            """
                SELECT ID FROM talk WHERE URI_GC = ?
            """,
            (uri,),
        )
        result = cursor.fetchone()
        if result:
            return result[0]
    except sqlite3.OperationalError:
        pass

    return None


def insert_topic(conn: sqlite3.Connection, topic_name: str) -> int:
    """
    Insert a topic or return existing ID (idempotent).

    Args:
        conn: SQLite connection
        topic_name: name of the topic

    Returns:
        ID of the inserted or existing topic
    """
    slug = generate_topic_slug(topic_name)

    # Try to insert, if exists, just ignore
    conn.execute(
        """
        INSERT INTO conference_topic (name, slug)
        VALUES (?, ?)
        ON CONFLICT(name) DO NOTHING
        """,
        (topic_name, slug),
    )

    # Get the ID
    cursor = conn.execute(
        "SELECT ID FROM conference_topic WHERE name = ?", (topic_name,)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def insert_talk_topic(
    conn: sqlite3.Connection,
    topic_id: int,
    talk_id: Optional[int],
    content_identifier: str,
) -> bool:
    """
    Insert a topic reference (idempotent).

    Args:
        conn: SQLite connection
        topic_id: ID of the topic
        talk_id: ID of the talk (can be None if lookup failed)
        content_identifier: Data-aid identifier

    Returns:
        True if inserted, False if skipped (duplicate or missing talk_id)
    """
    if talk_id is None:
        return False

    try:
        conn.execute(
            """
            INSERT INTO talk_topic (topic_id, talk_id, content_identifier)
            VALUES (?, ?, ?)
            ON CONFLICT(topic_id, content_identifier) DO NOTHING
            """,
            (topic_id, talk_id, content_identifier),
        )
        return True
    except sqlite3.IntegrityError:
        # Duplicate or foreign key violation
        return False


def load_json_data(file_path: str) -> List[Dict]:
    """
    Load topic data from JSON file.

    Args:
        file_path: Path to JSON file

    Returns:
        List of topic dictionaries
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def populate_topics(
    conn: sqlite3.Connection, topics_data: List[Dict], dry_run: bool = False
) -> tuple[int, int, int, int]:
    """
    Populate conference_topic and talk_topic tables.

    Args:
        conn: SQLite connection
        topics_data: List of topic dictionaries from JSON
        dry_run: If True, don't write changes

    Returns:
        Tuple of (topics_processed, references_inserted, references_with_talk_id, references_failed)
    """
    topics_processed = 0
    references_inserted = 0
    references_with_talk_id = 0
    references_failed = 0

    for topic_data in topics_data:
        topic_name = topic_data.get("topic", "Unknown")
        entries = topic_data.get("entries", [])

        print(f"\nProcessing: {topic_name}")
        print(f"  Entries: {len(entries)}")

        if dry_run:
            topics_processed += 1
            print(f"  [DRY-RUN] Would insert topic and {len(entries)} references")
            continue

        # Insert topic
        topic_id = insert_topic(conn, topic_name)
        if topic_id is None:
            print(f"  ⚠️  Failed to insert/retrieve topic")
            continue

        topics_processed += 1

        # Insert references
        local_success = 0
        local_with_talk = 0
        local_failed = 0

        for entry in entries:
            if not entry:
                local_failed += 1
                continue
            uri = entry.get("uri", "")

            # Look up talk ID
            talk_id = lookup_talk_id(conn, uri)
            if talk_id:
                local_with_talk += 1
                references_with_talk_id += 1

            # Insert reference (will be skipped if talk_id is None)
            if insert_talk_topic(conn, topic_id, talk_id, uri):
                local_success += 1
                references_inserted += 1
            else:
                local_failed += 1
                references_failed += 1

        print(f"  ✓ Inserted {local_success}/{len(entries)} references")
        print(f"  ✓ Found talk_id for {local_with_talk}/{len(entries)} entries")
        if local_failed > 0:
            print(f"  ⚠️  Failed/skipped {local_failed} references")

    if not dry_run:
        conn.commit()

    return (
        topics_processed,
        references_inserted,
        references_with_talk_id,
        references_failed,
    )


def print_statistics(conn: sqlite3.Connection) -> None:
    """
    Print database statistics.

    Args:
        conn: SQLite connection
    """
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    # Total topics
    cursor = conn.execute("SELECT COUNT(*) FROM conference_topic")
    total_topics = cursor.fetchone()[0]
    print(f"\nTotal topics: {total_topics}")

    # Total references
    cursor = conn.execute("SELECT COUNT(*) FROM talk_topic")
    total_refs = cursor.fetchone()[0]
    print(f"Total topic references: {total_refs}")

    # References with talk_id
    cursor = conn.execute("SELECT COUNT(*) FROM talk_topic WHERE talk_id IS NOT NULL")
    with_talk_id = cursor.fetchone()[0]
    percentage = (with_talk_id / max(total_refs, 1)) * 100
    print(f"References with talk_id: {with_talk_id} ({percentage:.1f}%)")

    # Top 10 topics by reference count
    print("\nTop 10 topics by reference count:")
    cursor = conn.execute(
        """
        SELECT ct.name, COUNT(tr.ID) as ref_count
        FROM conference_topic ct
        LEFT JOIN talk_topic tr ON ct.ID = tr.topic_id
        GROUP BY ct.ID, ct.name
        ORDER BY ref_count DESC
        LIMIT 10
        """
    )

    for topic_name, ref_count in cursor.fetchall():
        print(f"  {topic_name}: {ref_count} references")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill conference topics and references into core.db"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to core.db (default: uses CORE_DB_PATH from db module)",
    )
    parser.add_argument(
        "--input",
        "-i",
        default="conference_topics.json",
        help="Path to JSON file with topics (default: ./conference_topics.json)",
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

    # Use CORE_DB_PATH from db module or custom path if provided
    db_path = args.db if args.db else CORE_DB_PATH

    # Resolve input path relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, args.input)

    print("=" * 60)
    print("Conference Topics Backfill Migration")
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
        topics_data = load_json_data(input_path)
        print(f"✓ Loaded {len(topics_data)} topics")

        # Create writable Database instance (disable read-only mode for migration)
        # Note: We use raw sqlite3 connection for schema operations
        # since the Database class is optimized for queries, not schema changes
        with sqlite3.connect(db_path) as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

            # Ensure tables exist
            ensure_tables_exist(conn)

            if args.dry_run:
                print("\n[DRY-RUN MODE] No changes will be written")

            # Populate tables
            print("\n" + "=" * 60)
            print("Populating tables...")
            print("=" * 60)

            topics, refs, refs_with_talk, refs_failed = populate_topics(
                conn, topics_data, dry_run=args.dry_run
            )

            # Print results
            elapsed = time.time() - start_time
            print("\n" + "=" * 60)
            print("MIGRATION COMPLETE")
            print("=" * 60)
            print(f"Topics processed: {topics}")
            print(f"References inserted: {refs}")
            print(f"References with talk_id: {refs_with_talk}")
            print(f"References failed/skipped: {refs_failed}")
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
