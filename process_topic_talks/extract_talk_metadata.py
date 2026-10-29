#!/usr/bin/env python3
"""
Talk Metadata Fetcher

Fetches title, data-aid and speaker role for each talk page from the Church
API. Output is keyed by Church URI and merged into the existing file.

Usage:
    pipenv run python process_topic_talks/extract_talk_metadata.py --conference 2025-10
    pipenv run python process_topic_talks/extract_talk_metadata.py --all
"""

import argparse
import html
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from api.fetch_talk_previews import all_conferences, fetch_talk_list, parse_conference
from utils.church_api import cached_session, fresh_session, get_json
from utils.json_io import merge_by_key, read_json, write_json

# ============================================================================
# CONFIGURATION
# ============================================================================
OUTPUT_PATH = os.path.join(ROOT_DIR, "db", "one-off-migration", "talk_metadata.json")
WORKER_COUNT = 1
# ============================================================================

# Thread-safe print lock
print_lock = Lock()


def safe_print(message):
    """Thread-safe print function."""
    with print_lock:
        print(message)


def extract_speaker_role(html_content):
    """
    Extract speaker role from HTML content.

    Args:
        html_content: HTML string

    Returns:
        Speaker role text or None
    """
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        role_elem = soup.find("p", class_="author-role")
        if role_elem:
            return role_elem.get_text(strip=True)
        return None
    except Exception:
        return None


def fetch_talk_metadata(session: requests.Session, uri: str) -> Optional[Dict[str, Optional[str]]]:
    """
    Fetch talk metadata from the API.

    Args:
        session: requests session (may be cached)
        uri: Church URI of the talk

    Returns:
        Dictionary with talk metadata (missing fields are None), or None if
        the request failed
    """
    result = {
        "uri": uri,
        "title": None,
        "speaker_role": None,
        "data_aid": None,
    }

    try:
        api_data = get_json(session, uri)

        # Extract title and data-aid
        meta = api_data.get("content", {}).get("meta", {})
        title = meta.get("title")
        result["title"] = html.unescape(title) if title else None
        result["data_aid"] = meta.get("pageAttributes", {}).get("data-aid")

        talk_body = api_data.get("content", {}).get("content", {}).get("body")
        result["speaker_role"] = extract_speaker_role(talk_body) if talk_body else None

        missing = [k for k in ("title", "data_aid", "speaker_role") if not result[k]]
        if missing:
            safe_print(f"⚠️  {uri}: Missing {', '.join(missing)}")

    except (requests.exceptions.RequestException, ValueError) as e:
        safe_print(f"✗ {uri}: Request failed - {e}")
        return None

    return result


def fetch_all_metadata(session: requests.Session, uris: List[str]) -> List[Dict]:
    """Fetch metadata for each URI, in input order.

    A talk whose request fails gets no record, so merging keeps its old entry.
    """
    with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
        results = executor.map(lambda uri: fetch_talk_metadata(session, uri), uris)
        return [r for r in results if r is not None]


def save_metadata(records: List[Dict], output_path: str = OUTPUT_PATH) -> None:
    """Merge records into the metadata file by URI."""
    write_json(output_path, merge_by_key(read_json(output_path), records))


def main():
    parser = argparse.ArgumentParser(description="Fetch talk metadata from the Church API.")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--conference", type=parse_conference, metavar="YYYY-MM")
    which.add_argument("--all", action="store_true", help="1971-04 through the latest conference")
    parser.add_argument("--output", default=OUTPUT_PATH, help="Output JSON path (default: %(default)s)")
    args = parser.parse_args()

    conferences = all_conferences() if args.all else [args.conference]

    print("=" * 80)
    print("Talk Metadata Fetch")
    print("=" * 80)
    print(f"Conferences: {len(conferences)}")
    print(f"Output JSON: {args.output}")
    print(f"Worker Threads: {WORKER_COUNT}")
    print("=" * 80)

    uris = [t["uri"] for t in fetch_talk_list(fresh_session(), conferences)]
    print(f"Found {len(uris)} talk URIs")

    start_time = time.time()
    results = fetch_all_metadata(cached_session(), uris)
    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.1f} seconds")

    save_metadata(results, args.output)

    complete = sum(1 for r in results if r["title"] and r["data_aid"] and r["speaker_role"])
    print(f"Saved {len(results)} talk records ({len(uris) - len(results)} fetch failures)")
    print(f"  - Complete (all fields): {complete}")
    print(f"  - Missing title: {sum(1 for r in results if not r['title'])}")
    print(f"  - Missing data-aid: {sum(1 for r in results if not r['data_aid'])}")
    print(f"  - Missing speaker_role: {sum(1 for r in results if not r['speaker_role'])}")


if __name__ == "__main__":
    main()
