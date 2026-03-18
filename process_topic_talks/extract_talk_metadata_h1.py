#!/usr/bin/env python3
"""
Talk Metadata Extractor

Fetches talk data from API and extracts data-aid and title metadata,
comparing with database values.
"""

import sqlite3
import sys
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import defaultdict
import time

# ============================================================================
# CONFIGURATION - Modify these values as needed
# ============================================================================
API_BASE_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri="
WORKER_COUNT = 2
# ============================================================================

# Thread-safe print lock
print_lock = Lock()

# Thread-safe error tracking
errors_lock = Lock()
errors = defaultdict(list)


def safe_print(message):
    """Thread-safe print function."""
    with print_lock:
        print(message)


def get_talks_with_uris(db_path):
    """Get all talks with URIs from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT ID, Title, URI FROM talk WHERE URI IS NOT NULL ORDER BY ID")
    talks = cursor.fetchall()

    conn.close()
    return talks


def fetch_talk_metadata(talk_id, db_title, uri):
    """
    Fetch talk metadata from API.

    Args:
        talk_id: Talk ID from database
        db_title: Title from database
        uri: URI path for the talk

    Returns:
        Dictionary with talk metadata
    """
    try:
        url = f"{API_BASE_URL}{uri}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Extract API title from content.meta.title
        api_title = data.get("content", {}).get("meta", {}).get("title")

        # Extract data-aid from h1 in content.content.body
        html_content = data.get("content", {}).get("content", {}).get("body", "")
        data_aid = None

        if html_content:
            soup = BeautifulSoup(html_content, "html.parser")
            h1_element = soup.find("h1", {"data-aid": True})
            if h1_element and h1_element.get("data-aid"):
                data_aid = h1_element["data-aid"]
            else:
                with errors_lock:
                    errors["missing_data_aid"].append(
                        {
                            "talkID": talk_id,
                            "uri": uri,
                            "db_title": db_title,
                            "reason": "No h1 element with data-aid found in HTML",
                        }
                    )
        else:
            with errors_lock:
                errors["missing_html_content"].append(
                    {
                        "talkID": talk_id,
                        "uri": uri,
                        "db_title": db_title,
                        "reason": "No HTML content in response.content.content.body",
                    }
                )

        if not api_title:
            with errors_lock:
                errors["missing_api_title"].append(
                    {
                        "talkID": talk_id,
                        "uri": uri,
                        "db_title": db_title,
                        "reason": "No title in response.content.meta.title",
                    }
                )

        # Build result
        result = {
            "talkID": talk_id,
            "db_title": db_title,
            "api_title": api_title,
            "uri": uri,
            "data_aid": data_aid,
        }

        # Log status
        if data_aid and api_title:
            safe_print(f"✓ TalkID {talk_id}: Complete")
        elif not data_aid and not api_title:
            safe_print(f"⚠️  TalkID {talk_id}: Missing data-aid and API title")
        elif not data_aid:
            safe_print(f"⚠️  TalkID {talk_id}: Missing data-aid")
        elif not api_title:
            safe_print(f"⚠️  TalkID {talk_id}: Missing API title")

        return result

    except requests.exceptions.HTTPError as e:
        safe_print(f"✗ TalkID {talk_id}: HTTP error - {e}")
        with errors_lock:
            errors["http_error"].append(
                {
                    "talkID": talk_id,
                    "uri": uri,
                    "db_title": db_title,
                    "error": str(e),
                    "status_code": (
                        response.status_code if "response" in locals() else None
                    ),
                    "reason": "HTTP error during request",
                }
            )
        return {
            "talkID": talk_id,
            "db_title": db_title,
            "api_title": None,
            "uri": uri,
            "data_aid": None,
        }
    except requests.exceptions.RequestException as e:
        safe_print(f"✗ TalkID {talk_id}: Request failed - {e}")
        with errors_lock:
            errors["request_error"].append(
                {
                    "talkID": talk_id,
                    "uri": uri,
                    "db_title": db_title,
                    "error": str(e),
                    "reason": "Network or connection error",
                }
            )
        return {
            "talkID": talk_id,
            "db_title": db_title,
            "api_title": None,
            "uri": uri,
            "data_aid": None,
        }
    except json.JSONDecodeError as e:
        safe_print(f"✗ TalkID {talk_id}: Invalid JSON - {e}")
        with errors_lock:
            errors["json_decode_error"].append(
                {
                    "talkID": talk_id,
                    "uri": uri,
                    "db_title": db_title,
                    "error": str(e),
                    "reason": "Invalid JSON response from API",
                }
            )
        return {
            "talkID": talk_id,
            "db_title": db_title,
            "api_title": None,
            "uri": uri,
            "data_aid": None,
        }
    except Exception as e:
        safe_print(f"✗ TalkID {talk_id}: Unexpected error - {e}")
        with errors_lock:
            errors["unexpected_error"].append(
                {
                    "talkID": talk_id,
                    "uri": uri,
                    "db_title": db_title,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "reason": "Unexpected exception during processing",
                }
            )
        return {
            "talkID": talk_id,
            "db_title": db_title,
            "api_title": None,
            "uri": uri,
            "data_aid": None,
        }


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python extract_talk_metadata.py <core_db_path> <output_json_path> <errors_json_path>"
        )
        sys.exit(1)

    core_db_path = sys.argv[1]
    output_json_path = sys.argv[2]
    errors_json_path = sys.argv[3]

    print("=" * 80)
    print("Talk Metadata Extractor")
    print("=" * 80)
    print(f"Core Database: {core_db_path}")
    print(f"Output JSON: {output_json_path}")
    print(f"Errors JSON: {errors_json_path}")
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Worker Threads: {WORKER_COUNT}")
    print("=" * 80)

    # Step 1: Get talks from database
    print("\nStep 1: Loading talks from database...")
    talks = get_talks_with_uris(core_db_path)
    print(f"Found {len(talks)} talks with URIs")

    # Step 2: Fetch metadata from API (multithreaded)
    print(f"\nStep 2: Fetching talk metadata from API ({WORKER_COUNT} workers)...")
    print("-" * 80)

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
        # Submit all tasks
        future_to_talk = {
            executor.submit(fetch_talk_metadata, talk_id, title, uri): (
                talk_id,
                title,
                uri,
            )
            for talk_id, title, uri in talks
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
    import os

    output_dir = os.path.dirname(output_json_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    with open(output_json_path, "w") as f:
        json.dump(results, f, indent=2)

    # Calculate statistics
    complete = sum(1 for r in results if r["data_aid"] and r["api_title"])
    missing_data_aid = sum(1 for r in results if not r["data_aid"])
    missing_api_title = sum(1 for r in results if not r["api_title"])
    missing_both = sum(1 for r in results if not r["data_aid"] and not r["api_title"])

    print(f"Saved {len(results)} talk records")
    print(f"  - Complete (both data-aid and API title): {complete}")
    print(f"  - Missing data-aid: {missing_data_aid}")
    print(f"  - Missing API title: {missing_api_title}")
    print(f"  - Missing both: {missing_both}")

    if complete > 0:
        success_rate = (complete / len(results) * 100) if results else 0
        print(f"  - Success rate: {success_rate:.1f}%")

    # Step 4: Save errors to JSON
    print(f"\nStep 4: Saving errors to {errors_json_path}...")
    try:
        errors_dict = dict(errors)

        # Create directory if it doesn't exist
        errors_dir = os.path.dirname(errors_json_path)
        if errors_dir and not os.path.exists(errors_dir):
            os.makedirs(errors_dir)
            print(f"Created directory: {errors_dir}")

        with open(errors_json_path, "w") as f:
            json.dump(errors_dict, f, indent=2)

        total_errors = sum(len(v) for v in errors_dict.values())
        if total_errors > 0:
            print(f"Saved {total_errors} errors")
            print("\nError breakdown:")
            for error_type, error_list in errors_dict.items():
                print(f"  - {error_type}: {len(error_list)}")
        else:
            print("No errors to save")
    except Exception as e:
        print(f"Warning: Failed to save errors - {e}")

    print("\n" + "=" * 80)
    if sum(len(v) for v in errors.values()) > 0:
        print(
            f"⚠️  Completed with {sum(len(v) for v in errors.values())} errors. Check {errors_json_path} for details."
        )
    else:
        print("✓ All steps completed successfully with no errors!")
    print("=" * 80)


if __name__ == "__main__":
    main()
