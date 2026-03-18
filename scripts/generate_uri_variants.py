#!/usr/bin/env python3
"""
Generate URI Variants from Talk URLs

Creates three new columns in the talk table:
- URI_L: Literal URI (minimal processing, keeps session paths)
- URI_GC: General Conference variant (normalized dates, extracted identifiers)
- URI_Success: Track which URI variant worked (populated later)
"""

import sqlite3
import sys
import re
from urllib.parse import urlparse


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
        return (year - 1, "10")
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


def add_uri_columns(db_path):
    """
    Add URI_L, URI_GC, and URI_Success columns to talk table.

    Args:
        db_path: Path to database
    """
    print("=" * 80)
    print("URI Variant Generator")
    print("=" * 80)
    print(f"Database: {db_path}")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add columns if they don't exist
    print("\nStep 1: Adding URI columns to talk table...")

    columns_to_add = [("URI_L", "TEXT"), ("URI_GC", "TEXT"), ("URI_Success", "TEXT")]

    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE talk ADD COLUMN {col_name} {col_type}")
            print(f"  Added column: {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"  Column {col_name} already exists, will update values")
            else:
                raise

    conn.commit()

    # Get all talks with URLs
    print("\nStep 2: Loading talks from database...")
    cursor.execute("SELECT ID, URL FROM talk WHERE URL IS NOT NULL")
    talks = cursor.fetchall()
    print(f"Found {len(talks)} talks with URLs")

    # Process each talk
    print("\nStep 3: Generating URI variants...")
    print("-" * 80)

    updated_count = 0
    uri_l_count = 0
    uri_gc_count = 0
    failed_count = 0

    for talk_id, url in talks:
        uri_l = extract_uri_l(url)
        uri_gc = extract_uri_gc(url)

        # Update database
        cursor.execute(
            "UPDATE talk SET URI_L = ?, URI_GC = ? WHERE ID = ?",
            (uri_l, uri_gc, talk_id),
        )

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

    # Commit changes
    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("Summary:")
    print(f"  Total talks processed: {updated_count}")
    print(f"  URI_L generated: {uri_l_count}")
    print(f"  URI_GC generated: {uri_gc_count}")
    print(f"  Failed to generate: {failed_count}")
    print(
        f"  Success rate: {((updated_count - failed_count) / updated_count * 100):.1f}%"
    )
    print("=" * 80)
    print("\n✓ URI columns created and populated successfully!")
    print(
        "\nNote: URI_Success column created but left empty (populate with validation script)"
    )
    print("=" * 80)


def main():
    if len(sys.argv) != 2:
        print("Usage: python generate_uri_variants.py <core_db_path>")
        sys.exit(1)

    db_path = sys.argv[1]

    add_uri_columns(db_path)


if __name__ == "__main__":
    main()
