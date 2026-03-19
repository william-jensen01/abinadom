#!/usr/bin/env python3
"""
Create talk_metadata table in core.52.db and provide shared UPSERT helper.

This module serves two purposes:
  1. DDL script: run directly to create the talk_metadata table and indexes.
  2. Shared helper: imported by all backfill scripts to write enrichment data
     via upsert_talk_metadata().

Usage:
    pipenv run py db/one-off-migration/create_talk_metadata_table.py [--db <path>]
"""

import argparse
import os
import sys

# Ensure Unicode output works on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add root to path for db module import
db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(db_dir)
sys.path.insert(0, root_dir)

from db import Database, CORE_DB_PATH


def create_table(db: Database) -> None:
    """Create talk_metadata table and indexes (idempotent)."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS talk_metadata (
            talk_id         INTEGER PRIMARY KEY REFERENCES talk(ID),
            speaker_role_id INTEGER REFERENCES speaker_role(id),
            uri_l           TEXT,
            uri_gc          TEXT,
            kicker          TEXT,
            talk_preview    TEXT,
            data_aid        TEXT
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_talk_metadata_data_aid ON talk_metadata(data_aid)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_talk_metadata_uri_gc ON talk_metadata(uri_gc)"
    )
    print("  ✓ talk_metadata table created/verified")


def upsert_talk_metadata(db: Database, talk_id: int, **fields) -> None:
    """
    Upsert a row in talk_metadata for talk_id.

    Accepts arbitrary keyword arguments matching talk_metadata column names
    (speaker_role_id, uri_l, uri_gc, kicker, talk_preview, data_aid).
    Existing columns NOT included in **fields are left unchanged.

    Args:
        db:      Writable Database instance (core.52.db).
        talk_id: Primary key — talk.ID.
        **fields: Column name → value pairs to upsert.
    """
    if not fields:
        return
    columns = list(fields.keys())
    placeholders = ", ".join(["?"] * (len(columns) + 1))
    col_names = ", ".join(["talk_id"] + columns)
    update_clause = ", ".join(f"{col} = excluded.{col}" for col in columns)
    values = [talk_id] + [fields[col] for col in columns]
    db.execute(
        f"""INSERT INTO talk_metadata ({col_names})
            VALUES ({placeholders})
            ON CONFLICT(talk_id) DO UPDATE SET {update_clause}""",
        values,
    )


def verify_table(db: Database) -> None:
    """Print column names from PRAGMA table_info to confirm table structure."""
    rows = db.select("PRAGMA table_info(talk_metadata)")
    col_names = [row["name"] for row in rows]
    print(f"  talk_metadata columns ({len(col_names)}): {', '.join(col_names)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create talk_metadata table and indexes in core.52.db"
    )
    parser.add_argument(
        "--db",
        default=CORE_DB_PATH,
        help="Path to core.52.db (default: CORE_DB_PATH from db module)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("Create talk_metadata Table")
    print("=" * 60)
    print(f"Database: {args.db}")
    print("=" * 60)

    db = Database(args.db, timeout=60, read_only=False)
    create_table(db)
    verify_table(db)

    print("=" * 60)
    print("✓ Done")
    print("=" * 60)


if __name__ == "__main__":
    main()
