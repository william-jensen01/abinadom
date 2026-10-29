"""
Topic data fetcher.

Fetches the topics index (/general-conference/topics) into topics.json, then
fetches each topic page and extracts its talk entries into
conference_topics.json. Topic pages are always fetched fresh.

Usage:
    pipenv run python scripts/process_topics.py
"""

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from utils.church_api import fresh_session, get_json
from utils.json_io import read_json, write_json

TOPICS_INDEX_URI = "/general-conference/topics"
TOPICS_FILE = os.path.join(ROOT_DIR, "topics.json")
OUTPUT_FILE = os.path.join(ROOT_DIR, "db", "one-off-migration", "conference_topics.json")


def fetch_topics_index(session: requests.Session) -> List[Dict]:
    """Fetch every topic ({type, title, uri}) from the topics index page.

    Reads the page's "Find by topic" filter, which lists every topic once.
    """
    data = get_json(session, TOPICS_INDEX_URI)
    for section in data.get("collection", {}).get("sections", []):
        for entry in section.get("entries", []):
            if entry.get("type") == "search" and entry.get("items"):
                return entry["items"]
    raise ValueError(f"No topic list found on {TOPICS_INDEX_URI}")


def extract_entries(api_data: Dict[str, Any]) -> List[Dict]:
    """Extract all entries from collection.sections in API response."""
    entries = []
    for section in api_data.get("collection", {}).get("sections", []):
        entries.extend(section.get("entries", []))
    return entries


def process_topics(
    topics: List[Dict], session: requests.Session, previous: Optional[Dict[str, List[Dict]]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict]]:
    """
    Fetch every topic page and return its talk entries.

    A topic the index lists but whose page is 404 (e.g. "values", 2026-10)
    keeps its entries from `previous` (topic title → entries) and is returned
    in the second list. Any other failure raises (after get_json's retry), so
    a partial result is never written: an empty topic would delete its talks
    from the saved file.

    Returns:
        (results, missing_pages). results: [{'topic': title, 'entries': [... uri descending]}]
    """
    previous = previous or {}
    results = []
    missing_pages = []
    for topic in topics:
        try:
            entries = extract_entries(get_json(session, topic["uri"]))
        except requests.exceptions.HTTPError as e:
            if e.response is None or e.response.status_code != 404:
                raise
            missing_pages.append(topic)
            entries = previous.get(topic["title"], [])
            print(f"  {topic['title']}: page 404, kept {len(entries)} old entries")
        else:
            print(f"  {topic['title']}: {len(entries)} entries")
        results.append(
            {
                "topic": topic["title"],
                "entries": sorted(entries, key=lambda e: e["uri"], reverse=True),
            }
        )
    return results, missing_pages


def load_previous(path: str = OUTPUT_FILE) -> Dict[str, List[Dict]]:
    """Saved topic entries, by topic title."""
    return {t["topic"]: t["entries"] for t in read_json(path)}


def save_topics_index(topics: List[Dict], path: str = TOPICS_FILE) -> None:
    write_json(path, topics, key="uri")


def save_results(results: List[Dict], path: str = OUTPUT_FILE) -> None:
    write_json(path, results, key="topic")


def main():
    parser = argparse.ArgumentParser(description="Fetch conference topics from the Church API.")
    parser.add_argument("--topics", default=TOPICS_FILE, help="topics index output (default: %(default)s)")
    parser.add_argument("--output", default=OUTPUT_FILE, help="topic entries output (default: %(default)s)")
    args = parser.parse_args()

    session = fresh_session()

    print("Fetching topics index...")
    topics = fetch_topics_index(session)
    print(f"Found {len(topics)} topics\n")

    results, missing_pages = process_topics(topics, session, load_previous(args.output))

    # Write only after every topic succeeded.
    save_topics_index(topics, args.topics)
    save_results(results, args.output)
    print(f"\nSaved {args.topics} and {args.output}")
    for t in missing_pages:
        print(f"Topic page 404, old entries kept: {t['title']} ({t['uri']})")


if __name__ == "__main__":
    main()
