#!/usr/bin/env python3
"""
Backfill script for populating conference topics and their talk references.

This script migrates topic data from JSON files into the core.db database. It will:

- Create two tables if they don't exist:
  - conference_topic: stores topic names and slugs
  - talk_topic: links talks to topics (content_identifier = Church URI)

- Populate tables from conference_topics.json ([{"topic": ..., "entries": [{"uri": ...}]}])
- Find each entry's SCI talk by Church URI (talk_metadata.uri_gc / uri_l,
  so backfill_talk_uri.py must run first)
- Use idempotent inserts (ON CONFLICT DO NOTHING) to safely handle re-runs

Usage:
  pipenv run python db/one-off-migration/backfill_topics.py [--core-db PATH] [--input PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from typing import Dict, List, Optional, Set

# Add parent directory to path for importing Database
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(parent_dir)
sys.path.insert(0, root_dir)

from db import Database, CORE_DB_PATH

migration_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, migration_dir)
from create_talk_metadata_table import find_talk_by_uri, load_talk_uri_index

TOPICS_PATH = os.path.join(migration_dir, "conference_topics.json")


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
    conn: sqlite3.Connection,
    topics_data: List[Dict],
    uri_index: Dict[str, Set[int]],
    dry_run: bool = False,
) -> tuple[int, int, int, int]:
    """
    Populate conference_topic and talk_topic tables.

    Args:
        conn: SQLite connection
        topics_data: List of topic dictionaries from JSON
        uri_index: load_talk_uri_index() result
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
            talk_id = find_talk_by_uri(uri_index, uri)
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

        print(f"  {topic_name}: {local_success}/{len(entries)} entries linked to a talk")

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
        description="Backfill conference topics and references into the core DB"
    )
    parser.add_argument(
        "--core-db",
        "--db",
        dest="core_db",
        default=CORE_DB_PATH,
        help="Path to core DB (default: uses CORE_DB_PATH from db module)",
    )
    parser.add_argument(
        "--input",
        "-i",
        default=TOPICS_PATH,
        help="Path to JSON file with topics (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write changes; only report what would be done",
    )
    return parser.parse_args()


def run(core_db_path: str, topics_path: str = TOPICS_PATH, dry_run: bool = False) -> dict:
    topics_data = load_json_data(topics_path)
    print(f"✓ Loaded {len(topics_data)} topics")
    uri_index = load_talk_uri_index(Database(core_db_path))

    conn = sqlite3.connect(core_db_path)
    try:
        ensure_tables_exist(conn)
        topics, refs, refs_with_talk, refs_failed = populate_topics(
            conn, topics_data, uri_index, dry_run=dry_run
        )
        print(f"Topics processed: {topics}")
        print(f"References inserted: {refs}")
        print(f"References with no SCI talk/skipped: {refs_failed}")
        if not dry_run:
            print_statistics(conn)
    finally:
        conn.close()
    return {"topics": topics, "references": refs, "skipped": refs_failed}


def main() -> None:
    """Main execution function."""
    args = parse_args()

    print("=" * 60)
    print("Conference Topics Backfill Migration")
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
