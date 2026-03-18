#!/usr/bin/env python3
"""
General Conference Section Entries Extractor

Fetches conference data from API and extracts all section entries,
saving them in a flat structure keyed by conference ID.
"""

import sqlite3
import sys
import json
import requests
import requests_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import time

# sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
# from db import Database

# ============================================================================
# CONFIGURATION - Modify these values as needed
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


def get_conferences(db_path):
    """Get all conferences from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT ID, Year, Annual FROM conference ORDER BY ID")
    conferences = cursor.fetchall()

    conn.close()
    return conferences


def fetch_conference_sections(idx, year, annual):
    """
    Fetch conference data from API and extract all section entries.

    Args:
        conf_id: Conference ID
        year: Conference year
        annual: Annual code (A or S)

    Returns:
        Tuple of (conf_id, list of all section entries) or (conf_id, None) on error
    """
    try:
        # Map annual code to month
        month = "04" if annual == "A" else "10"

        # Build URL
        url = f"{API_BASE_URL}/general-conference/{year}/{month}".strip()
        conf_id = f"{year}-{month}"

        safe_print(f"→ Conference {idx}: Fetching {year}/{month}")

        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Navigate to toc.entries
        toc_entries = data.get("toc", {}).get("entries", [])
        if not toc_entries:
            safe_print(f"⚠️  Conference {idx} ({conf_id}): No TOC entries found")
            return (conf_id, [])

        # Extract all section entries into a flat list
        all_entries = []
        section_count = 0

        for entry in toc_entries:
            # Check if this entry has a section
            if "section" in entry and entry["section"]:
                section_entries = entry["section"].get("entries", [])
                all_entries.extend(section_entries)  # Flatten into single list
                section_count += 1

        safe_print(
            f"✓ Conference {idx} ({conf_id}): Found {len(all_entries)} entries across {section_count} sections"
        )
        return (conf_id, all_entries)

    except requests.exceptions.RequestException as e:
        safe_print(f"✗ Conference {idx} ({conf_id}): Request failed - {e}")
        return (conf_id, None)
    except json.JSONDecodeError as e:
        safe_print(f"✗ Conference {idx} ({conf_id}): Invalid JSON response - {e}")
        return (conf_id, None)
    except Exception as e:
        safe_print(f"✗ Conference {idx} ({conf_id}): Unexpected error - {e}")
        return (conf_id, None)


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python extract_conference_sections.py <core_db_path> <output_json_path>"
        )
        sys.exit(1)

    core_db_path = sys.argv[1]
    output_json_path = sys.argv[2]

    print("=" * 80)
    print("General Conference Section Entries Extractor")
    print("=" * 80)
    print(f"Core Database: {core_db_path}")
    print(f"Output JSON: {output_json_path}")
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Worker Threads: {WORKER_COUNT}")
    print("=" * 80)

    # Step 1: Get conferences from database
    print("\nStep 1: Loading conferences from database...")
    conferences = get_conferences(core_db_path)
    print(f"Found {len(conferences)} conferences")

    # Step 2: Fetch conference data (multithreaded)
    print(f"\nStep 2: Fetching conference data from API ({WORKER_COUNT} workers)...")
    print("-" * 80)

    results = {}
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
        # Submit all tasks
        future_to_conf = {
            executor.submit(fetch_conference_sections, idx, year, annual): idx
            for idx, year, annual in conferences
        }

        # Process completed tasks
        completed = 0
        for future in as_completed(future_to_conf):
            conf_id, entries = future.result()

            # Store results with conference ID as key
            if entries is not None:
                results[str(conf_id)] = entries
            else:
                results[str(conf_id)] = []

            completed += 1

            if completed % 20 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed
                remaining = len(conferences) - completed
                eta = remaining / rate if rate > 0 else 0
                safe_print(
                    f"Progress: {completed}/{len(conferences)} ({completed/len(conferences)*100:.1f}%) - ETA: {eta:.0f}s"
                )

    elapsed = time.time() - start_time
    print("-" * 80)
    print(
        f"Completed in {elapsed:.1f} seconds ({len(conferences)/elapsed:.1f} conferences/sec)"
    )

    # Step 3: Save to JSON
    print(f"\nStep 3: Saving results to {output_json_path}...")
    with open(output_json_path, "w") as f:
        json.dump(results, f, indent=2)

    # Calculate statistics
    total_entries = sum(len(entries) for entries in results.values())
    non_empty = sum(1 for entries in results.values() if len(entries) > 0)

    print(f"Saved {len(results)} conferences")
    print(f"  - {non_empty} conferences with entries")
    print(f"  - {len(results) - non_empty} conferences with no entries")
    print(f"  - {total_entries} total section entries extracted")

    print("\n" + "=" * 80)
    print("✓ All steps completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
