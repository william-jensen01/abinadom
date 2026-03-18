#!/usr/bin/env python3
"""
Talk Metadata Backfill Script

Fetches talk metadata including title, data-aid, and speaker role.
Uses existing database infrastructure for cleaner, more maintainable code.
"""

import sys
import json
import requests
import requests_cache
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import time
import os
import html
from datetime import timedelta

# Add parent directory to path to import db module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import Database

# ============================================================================
# CONFIGURATION
# ============================================================================
API_BASE_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri="
WORKER_COUNT = 1
REQUEST_TIMEOUT = 30
# ============================================================================

# Thread-safe print lock
print_lock = Lock()

requests_cache.install_cache(
    "http_cache", backend="sqlite", expire_after=requests_cache.NEVER_EXPIRE
)


def safe_print(message):
    """Thread-safe print function."""
    with print_lock:
        print(message)


def get_talks_with_uris(db: Database):
    """Get all talks with URIs from the database."""
    query = "SELECT ID, URI_GC FROM talk WHERE URI_GC IS NOT NULL ORDER BY ID"
    rows = db.select(query)
    return [(row["ID"], row["URI_GC"]) for row in rows]


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
    except Exception as e:
        return None


def fetch_talk_metadata(talk_id, uri):
    """
    Fetch talk metadata from API and HTML.

    Args:
        talk_id: Talk ID from database
        uri: URI path for the talk

    Returns:
        Dictionary with talk metadata
    """
    result = {
        "talkID": talk_id,
        "title": None,
        "uri": uri,
        "speaker_role": None,
        "data_aid": None,
    }

    try:
        # Fetch from API for title and data-aid
        api_url = f"{API_BASE_URL}{uri}"
        api_response = requests.get(api_url, timeout=REQUEST_TIMEOUT)
        print(api_response.from_cache)
        if not api_response.from_cache:
            return None
        api_response.raise_for_status()
        api_data = api_response.json()

        # Extract title and data-aid
        title = api_data.get("content", {}).get("meta", {}).get("title")
        result["title"] = html.unescape(title) if title else None
        result["data_aid"] = (
            api_data.get("content", {})
            .get("meta", {})
            .get("pageAttributes", {})
            .get("data-aid")
        )

        talk_body = api_data.get("content", {}).get("content", {}).get("body")
        result["speaker_role"] = extract_speaker_role(talk_body) if talk_body else None

        # # Fetch HTML for speaker role
        # html_url = f"{HTML_BASE_URL}{uri}"
        # html_response = requests.get(html_url, timeout=REQUEST_TIMEOUT)
        # html_response.raise_for_status()
        # result["speaker_role"] = extract_speaker_role(html_response.text)

        # Log status
        missing = []
        if not result["title"]:
            missing.append("title")
        if not result["data_aid"]:
            missing.append("data-aid")
        if not result["speaker_role"]:
            missing.append("speaker_role")

        if missing:
            safe_print(f"⚠️  TalkID {talk_id}: Missing {', '.join(missing)}")
        else:
            safe_print(f"✓ TalkID {talk_id}: Complete")

    except requests.exceptions.RequestException as e:
        safe_print(f"✗ TalkID {talk_id}: Request failed - {e}")
    except json.JSONDecodeError as e:
        safe_print(f"✗ TalkID {talk_id}: Invalid JSON - {e}")
    except Exception as e:
        safe_print(f"✗ TalkID {talk_id}: Unexpected error - {e}")

    return result


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python backfill_talk_metadata.py <core_db_path> <output_json_path>"
        )
        sys.exit(1)

    core_db_path = sys.argv[1]
    output_json_path = sys.argv[2]

    print("=" * 80)
    print("Talk Metadata Backfill")
    print("=" * 80)
    print(f"Core Database: {core_db_path}")
    print(f"Output JSON: {output_json_path}")
    print(f"Worker Threads: {WORKER_COUNT}")
    print("=" * 80)

    # Initialize database
    core_db = Database(core_db_path, read_only=True)

    # Step 1: Get talks from database
    print("\nStep 1: Loading talks from database...")
    talks = get_talks_with_uris(core_db)
    print(f"Found {len(talks)} talks with URIs")

    # Step 2: Fetch metadata (multithreaded)
    print(f"\nStep 2: Fetching talk metadata ({WORKER_COUNT} workers)...")
    print("-" * 80)

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
        # Submit all tasks
        future_to_talk = {
            executor.submit(fetch_talk_metadata, talk_id, uri): (talk_id, uri)
            for talk_id, uri in talks
        }

        # Process completed tasks
        completed = 0
        for future in as_completed(future_to_talk):
            result = future.result()
            results.append(result)
            completed += 1

            if completed % 100 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed
                remaining = len(talks) - completed
                eta = remaining / rate if rate > 0 else 0
                safe_print(
                    f"Progress: {completed}/{len(talks)} ({completed/len(talks)*100:.1f}%) - ETA: {eta:.0f}s"
                )

    elapsed = time.time() - start_time
    print("-" * 80)
    print(f"Completed in {elapsed:.1f} seconds ({len(talks)/elapsed:.1f} talks/sec)")

    # Step 3: Save to JSON
    print(f"\nStep 3: Saving results to {output_json_path}...")

    # Create directory if it doesn't exist
    output_dir = os.path.dirname(output_json_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    with open(output_json_path, "w") as f:
        json.dump(results, f, indent=2)

    # Calculate statistics
    complete = sum(
        1 for r in results if r["title"] and r["data_aid"] and r["speaker_role"]
    )
    missing_title = sum(1 for r in results if not r["title"])
    missing_data_aid = sum(1 for r in results if not r["data_aid"])
    missing_speaker_role = sum(1 for r in results if not r["speaker_role"])

    print(f"Saved {len(results)} talk records")
    print(f"  - Complete (all fields): {complete}")
    print(f"  - Missing title: {missing_title}")
    print(f"  - Missing data-aid: {missing_data_aid}")
    print(f"  - Missing speaker_role: {missing_speaker_role}")

    if complete > 0:
        success_rate = (complete / len(results) * 100) if results else 0
        print(f"  - Success rate: {success_rate:.1f}%")

    print("\n" + "=" * 80)
    if complete == len(results):
        print("✓ All talks processed successfully!")
    else:
        print(f"⚠️  Completed with {len(results) - complete} incomplete records")
    print("=" * 80)


if __name__ == "__main__":
    main()
