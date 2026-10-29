#!/usr/bin/env python3
"""
Church API Talk Preview Fetcher

Two-level fetch pattern:
  Level 1: Conference endpoint -> talk URIs per session
  Level 2: Individual talk endpoint -> preview text

Output is keyed by Church URI and merged into the existing file.

Usage:
  pipenv run python api/fetch_talk_previews.py --conference 2025-10
  pipenv run python api/fetch_talk_previews.py --all
  pipenv run python api/fetch_talk_previews.py --conference 2025-10 --dry-run
"""

import argparse
import datetime
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

import requests

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from utils.church_api import cached_session, fresh_session, get_json
from utils.json_io import merge_by_key, read_json, write_json

OUTPUT_PATH = os.path.join(ROOT_DIR, "db", "one-off-migration", "talk_previews.json")
FIRST_CONFERENCE = (1971, "04")

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conference list
# ---------------------------------------------------------------------------
def parse_conference(value: str) -> Tuple[int, str]:
    """Parse 'YYYY-MM' (MM is 04 or 10) into (year, month)."""
    try:
        year_s, month = value.split("-")
        year = int(year_s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got {value!r}")
    if month not in ("04", "10"):
        raise argparse.ArgumentTypeError(f"month must be 04 or 10, got {month!r}")
    return year, month


def all_conferences(today: Optional[datetime.date] = None) -> List[Tuple[int, str]]:
    """Every conference from 1971-04 through the current month."""
    today = today or datetime.date.today()
    conferences = []
    for year in range(FIRST_CONFERENCE[0], today.year + 1):
        for month in ("04", "10"):
            if (year, int(month)) <= (today.year, today.month):
                conferences.append((year, month))
    return conferences


# ---------------------------------------------------------------------------
# API fetch functions
# ---------------------------------------------------------------------------
def fetch_conference_talk_uris(session: requests.Session, year: int, month: str) -> List[Dict]:
    """Fetch talk URI list from the conference contents page (Level 1).

    Raises on a failed request, so a missing conference is never mistaken
    for one with no talks.

    Returns:
        List of dicts: [{"uri": str, "title": str, "subtitle": str}, ...]
    """
    data = get_json(session, f"/general-conference/{year}/{month}")

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


def fetch_talk_list(session: requests.Session, conferences: List[Tuple[int, str]]) -> List[Dict]:
    """Level 1 for several conferences, in order.

    A 404 on the newest conference is skipped (not held yet); any other
    failure raises.
    """
    talks = []
    for year, month in conferences:
        try:
            conference_talks = fetch_conference_talk_uris(session, year, month)
        except requests.exceptions.HTTPError as e:
            is_newest = (year, month) == conferences[-1]
            if is_newest and e.response is not None and e.response.status_code == 404:
                log.warning("Conference %s/%s not published yet; skipped", year, month)
                continue
            raise
        log.info("  Conference %s/%s: %d talk URIs", year, month, len(conference_talks))
        talks.extend(conference_talks)
    return talks


def fetch_talk_preview(session: requests.Session, talk_uri: str) -> Optional[str]:
    """Fetch preview text for a single talk (Level 2).

    Navigates: data["content"]["content"]["head"]["page-meta-social"]["pageMeta"]["description"]

    Returns:
        Preview description string, or None if the page has none.
        Raises if the request fails.
    """
    data = get_json(session, talk_uri)
    try:
        return data["content"]["content"]["head"]["page-meta-social"]["pageMeta"]["description"]
    except (KeyError, TypeError):
        log.warning("No preview found for talk %s", talk_uri)
        return None


def fetch_previews(session: requests.Session, talks: List[Dict]) -> List[Dict]:
    """Fetch previews for Level 1 talk entries. Returns preview records.

    A talk whose request fails gets no record, so merging keeps its old entry.
    """
    results = []
    for i, talk in enumerate(talks, 1):
        try:
            preview = fetch_talk_preview(session, talk["uri"])
        except (requests.exceptions.RequestException, ValueError) as e:
            log.error("Failed to fetch talk %s: %s", talk["uri"], e)
            continue
        results.append({"uri": talk["uri"], "title": talk["title"], "preview": preview or ""})
        if i % 100 == 0:
            log.info("  Progress: %d/%d talks fetched", i, len(talks))
    return results


def save_previews(records: List[Dict], output_path: str = OUTPUT_PATH) -> None:
    """Merge records into the previews file by URI."""
    write_json(output_path, merge_by_key(read_json(output_path), records))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Fetch talk previews from Church API using two-level fetch pattern."
    )
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--conference", type=parse_conference, metavar="YYYY-MM")
    which.add_argument("--all", action="store_true", help="1971-04 through the latest conference")
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    conferences = all_conferences() if args.all else [args.conference]
    print("=" * 70)
    print("Church API Talk Preview Fetcher")
    print("=" * 70)
    print(f"Conferences: {len(conferences)}")
    print(f"Output:      {args.output}")
    print(f"Dry run:     {args.dry_run}")
    print("=" * 70)

    # Contents pages are always fresh; talk pages may come from the cache.
    toc_session = fresh_session()
    talk_session = cached_session()

    talks = fetch_talk_list(toc_session, conferences)
    log.info("Total talk URIs collected: %d", len(talks))

    if args.dry_run:
        print("\n--- DRY RUN COMPLETE ---")
        print("Skipping Level 2 fetches and file write.")
        return

    results = fetch_previews(talk_session, talks)
    save_previews(results, args.output)

    print("\n" + "=" * 70)
    print("Coverage Summary")
    print("=" * 70)
    print(f"Talk URIs collected: {len(talks)}")
    print(f"Fetch failures:      {len(talks) - len(results)}")
    print(f"Previews found:      {sum(1 for r in results if r['preview'])}")
    print(f"Saved to:            {args.output}")
    print("=" * 70)


if __name__ == "__main__":
    main()
