#!/usr/bin/env python3
"""
Create talk_metadata table in core DB and provide shared helpers.

This module serves two purposes:
  1. DDL script: run directly to create the talk_metadata table and indexes.
  2. Shared helpers, imported by the backfill scripts:
     - upsert_talk_metadata(): write enrichment data
     - load_talk_uri_index() / find_talk_by_uri(): find the SCI talk for a
       Church URI via talk_metadata.uri_gc or uri_l

Usage:
    pipenv run python db/one-off-migration/create_talk_metadata_table.py [--core-db <path>]
"""

import argparse
import os
import sys
from typing import Dict, Optional, Set

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


def load_talk_uri_index(db: Database) -> Dict[str, Set[int]]:
    """Map every talk_metadata.uri_gc and uri_l to the talk IDs that have it.

    Built once per backfill; look up with find_talk_by_uri(). A URI with more
    than one talk is ambiguous (see duplicate_uris()).
    """
    index: Dict[str, Set[int]] = {}
    rows = db.select("SELECT talk_id, uri_gc, uri_l FROM talk_metadata")
    for row in rows:
        for uri in (row["uri_gc"], row["uri_l"]):
            if uri:
                index.setdefault(uri, set()).add(row["talk_id"])
    return index


def find_talk_by_uri(index: Dict[str, Set[int]], uri: str) -> Optional[int]:
    """Talk ID for a Church URI, or None if no talk (or more than one) has it."""
    ids = index.get(uri)
    if ids and len(ids) == 1:
        return next(iter(ids))
    return None


def duplicate_uris(index: Dict[str, Set[int]]) -> Dict[str, Set[int]]:
    """URIs claimed by more than one talk."""
    return {uri: ids for uri, ids in index.items() if len(ids) > 1}


def verify_table(db: Database) -> None:
    """Print column names from PRAGMA table_info to confirm table structure."""
    rows = db.select("PRAGMA table_info(talk_metadata)")
    col_names = [row["name"] for row in rows]
    print(f"  talk_metadata columns ({len(col_names)}): {', '.join(col_names)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create talk_metadata table and indexes in the core DB"
    )
    parser.add_argument(
        "--core-db",
        "--db",
        dest="core_db",
        default=CORE_DB_PATH,
        help="Path to core DB (default: CORE_DB_PATH from db module)",
    )
    return parser.parse_args()


def run(core_db_path: str) -> None:
    db = Database(core_db_path, timeout=60, read_only=False)
    create_table(db)
    verify_table(db)


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("Create talk_metadata Table")
    print("=" * 60)
    print(f"Database: {args.core_db}")
    print("=" * 60)

    run(args.core_db)

    print("=" * 60)
    print("✓ Done")
    print("=" * 60)


if __name__ == "__main__":
    main()
