#!/usr/bin/env python3
"""
Church API Talk Preview Fetcher

Two-level fetch pattern:
  Level 1: Conference endpoint -> talk URIs per session
  Level 2: Individual talk endpoint -> preview text and data_aid

Usage:
  pipenv run py api/fetch_talk_previews.py --dry-run
  pipenv run py api/fetch_talk_previews.py --db db/core.52.db --output db/one-off-migration/talk_previews.json
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from urllib.parse import urlparse

import requests
import requests_cache

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri="
REQUEST_TIMEOUT = 30
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "db",
    "one-off-migration",
    "talk_previews.json",
)

# Default DB path – import from db package if available, else construct manually
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from db import CORE_DB_PATH

    DEFAULT_DB_PATH = CORE_DB_PATH
except ImportError:
    DEFAULT_DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "db", "core.52.db"
    )

# ---------------------------------------------------------------------------
# Cache setup (matches extract_conference_sections.py pattern)
# ---------------------------------------------------------------------------
requests_cache.install_cache(
    "http_cache", backend="sqlite", expire_after=requests_cache.NEVER_EXPIRE
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_conferences(db_path):
    """Get all conferences from the database.

    Returns list of (id, year, annual) tuples.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT ID, Year, Annual FROM conference ORDER BY Year, ID")
    conferences = cursor.fetchall()
    conn.close()
    return conferences


def get_uri_gc_lookup(db_path):
    """Build a mapping from uri_gc path to talk ID.

    Queries talk table for rows with URI_GC set and Corpus in ('E', 'G').
    Normalizes URIs to path-only form for matching.

    Returns dict: {uri_gc_path: talk_id}
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ID, URI_GC FROM talk WHERE URI_GC IS NOT NULL AND Corpus IN ('E', 'G')"
    )
    rows = cursor.fetchall()
    conn.close()

    lookup = {}
    for talk_id, uri_gc in rows:
        # Normalize to path portion only
        if uri_gc.startswith("http"):
            path = urlparse(uri_gc).path
        else:
            path = uri_gc
        # Strip leading /study if present (API URIs don't include it)
        if path.startswith("/study"):
            path = path[len("/study") :]
        lookup[path] = talk_id

    return lookup


# ---------------------------------------------------------------------------
# API fetch functions
# ---------------------------------------------------------------------------
def fetch_conference_talk_uris(year, annual):
    """Fetch talk URI list from the conference endpoint (Level 1).

    Args:
        year: Conference year (e.g. 2024)
        annual: 'A' for April, 'S' for October (semi-annual)

    Returns:
        List of dicts: [{"uri": str, "title": str, "subtitle": str}, ...]
    """
    month = "04" if annual == "A" else "10"
    url = f"{API_BASE_URL}/general-conference/{year}/{month}"

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        log.error("Failed to fetch conference %s/%s: %s", year, month, e)
        return []
    except json.JSONDecodeError as e:
        log.error("Invalid JSON for conference %s/%s: %s", year, month, e)
        return []

    # Navigate to toc.entries, skip index 0 (not a session)
    toc_entries = data.get("toc", {}).get("entries", [])
    if not toc_entries:
        log.warning("No TOC entries for conference %s/%s", year, month)
        return []

    talks = []
    for session_entry in toc_entries[1:]:
        section = session_entry.get("section")
        if not section:
            continue
        for entry in section.get("entries", []):
            content = entry.get("content", {})
            uri = content.get("uri")
            if not uri:
                continue
            talks.append(
                {
                    "uri": uri,
                    "title": content.get("title", ""),
                    "subtitle": content.get("subtitle", ""),
                }
            )

    return talks


def fetch_talk_preview(talk_uri):
    """Fetch preview text for a single talk (Level 2).

    Navigates: data["content"]["content"]["head"]["page-meta-social"]["pageMeta"]["description"]

    Args:
        talk_uri: Talk URI path (e.g. /general-conference/2024/04/12nelson)

    Returns:
        Preview description string, or None if not found.
    """
    url = f"{API_BASE_URL}{talk_uri}"

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        log.error("Failed to fetch talk %s: %s", talk_uri, e)
        return None
    except json.JSONDecodeError as e:
        log.error("Invalid JSON for talk %s: %s", talk_uri, e)
        return None

    try:
        description = (
            data["content"]["content"]["head"]["page-meta-social"]["pageMeta"][
                "description"
            ]
        )
        return description
    except (KeyError, TypeError):
        log.warning("No preview found for talk %s", talk_uri)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Fetch talk previews from Church API using two-level fetch pattern."
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help="Path to core.52.db (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_PATH,
        help="Output JSON path (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch Level 1 URIs only, print counts, do not make Level 2 calls or write file.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Church API Talk Preview Fetcher")
    print("=" * 70)
    print(f"Database:  {args.db}")
    print(f"Output:    {args.output}")
    print(f"Dry run:   {args.dry_run}")
    print("=" * 70)

    # Step 1: Load conferences from DB
    log.info("Loading conferences from database...")
    conferences = get_conferences(args.db)
    log.info("Found %d conferences", len(conferences))

    # Step 2: Fetch Level 1 — conference talk URIs
    log.info("Fetching Level 1: conference talk URIs...")
    all_talk_entries = []  # list of (year, annual, talk_dict)
    for conf_id, year, annual in conferences:
        talks = fetch_conference_talk_uris(year, annual)
        for t in talks:
            all_talk_entries.append((year, annual, t))
        month = "04" if annual == "A" else "10"
        log.info(
            "  Conference %s/%s: %d talk URIs", year, month, len(talks)
        )

    log.info("Total talk URIs collected: %d", len(all_talk_entries))

    if args.dry_run:
        print("\n--- DRY RUN COMPLETE ---")
        print(f"Total conferences queried: {len(conferences)}")
        print(f"Total talk URIs collected: {len(all_talk_entries)}")
        print("Skipping Level 2 fetches and file write.")
        return

    # Step 3: Build uri_gc lookup
    log.info("Building URI_GC lookup from database...")
    uri_lookup = get_uri_gc_lookup(args.db)
    log.info("URI_GC lookup contains %d entries", len(uri_lookup))

    # Step 4: Fetch Level 2 — individual talk previews
    log.info("Fetching Level 2: individual talk previews...")
    results = []
    previews_found = 0
    matched = 0
    unmatched_talks = []

    for i, (year, annual, talk) in enumerate(all_talk_entries, 1):
        uri = talk["uri"]
        preview = fetch_talk_preview(uri)

        if preview:
            previews_found += 1

        # Match to talk_id via uri_gc lookup
        talk_id = uri_lookup.get(uri)
        if talk_id is not None:
            matched += 1
            results.append(
                {
                    "talkID": talk_id,
                    "title": talk["title"],
                    "uri": uri,
                    "preview": preview or "",
                }
            )
        else:
            month = "04" if annual == "A" else "10"
            unmatched_talks.append(
                {
                    "year": year,
                    "month": month,
                    "uri": uri,
                    "title": talk["title"],
                    "had_preview": preview is not None,
                }
            )
            log.debug("No talk_id match for URI: %s", uri)

        if i % 100 == 0:
            log.info("  Progress: %d/%d talks fetched", i, len(all_talk_entries))

    # Step 5: Save results
    log.info("Saving %d results to %s", len(results), args.output)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Coverage summary
    print("\n" + "=" * 70)
    print("Coverage Summary")
    print("=" * 70)
    print(f"Total talk URIs collected:   {len(all_talk_entries)}")
    print(f"Previews found (Level 2):    {previews_found}")
    print(f"Matched to talk_id:          {matched}")
    print(f"Unmatched (no talk_id):      {len(unmatched_talks)}")
    print(f"Results saved:               {len(results)}")

    if unmatched_talks:
        print("\n" + "-" * 70)
        print(f"Unmatched Talks ({len(unmatched_talks)} total)")
        print("-" * 70)
        # Group by conference for readability
        from itertools import groupby
        key = lambda t: (t["year"], t["month"])
        for (year, month), group in groupby(sorted(unmatched_talks, key=key), key=key):
            group_list = list(group)
            print(f"\n  {year}/{month} ({len(group_list)} unmatched):")
            for t in group_list:
                preview_flag = " [has preview]" if t["had_preview"] else ""
                title = t["title"] or "(no title)"
                print(f"    {t['uri']}")
                print(f"      Title: {title}{preview_flag}")

    print("=" * 70)


if __name__ == "__main__":
    main()
