#!/usr/bin/env python3
"""
General Conference Talk Topic Extractor

Fetches talk data from API, extracts data-aid from HTML, maps to topics,
and populates talk_topic table in the database.
"""

import sqlite3
import sys
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import time
import argparse

# ============================================================================
# CONFIGURATION - Modify these values as needed
# ============================================================================
API_BASE_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri="
RETRY_API_BASE_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/content?lang=eng&uri="
WORKER_COUNT = 2
# ============================================================================

# Thread-safe print lock
print_lock = Lock()


def safe_print(message):
    """Thread-safe print function."""
    with print_lock:
        print(message)


def get_talk_title(db_path, talk_id):
    """Get the full title for a talk from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT Title FROM talk WHERE ID = ?", (talk_id,))
    result = cursor.fetchone()

    conn.close()
    return result[0] if result else None


def fetch_talk_data(talk_id, uri):
    """
    Fetch talk data from API and extract data-aid from h1 element.

    Args:
        talk_id: The talk ID from database
        uri: The URI path for the talk

    Returns:
        Tuple of (talk_id, data_aid) or (talk_id, None) on error
    """
    try:
        url = f"{API_BASE_URL}{uri}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Parse JSON response
        data = response.json()

        # Extract aid from page attributes
        data_aid = (
            data.get("content", {})
            .get("meta", {})
            .get("pageAttributes", {})
            .get("data-aid")
        )

        if data_aid:
            safe_print(f"✓ TalkID {talk_id}: Found data-aid = {data_aid}")
            return (talk_id, data_aid)
        else:
            safe_print(f"⚠️  TalkID {talk_id}: No data-aid found in pageAttributes")
            return (talk_id, None)

    except requests.exceptions.RequestException as e:
        safe_print(f"✗ TalkID {talk_id}: Request failed - {e}")
        return (talk_id, None)
    except json.JSONDecodeError as e:
        safe_print(f"✗ TalkID {talk_id}: Invalid JSON response - {e}")
        return (talk_id, None)
    except Exception as e:
        safe_print(f"✗ TalkID {talk_id}: Unexpected error - {e}")
        return (talk_id, None)


def get_talks_from_db(db_path):
    """Get all talks with URIs from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT ID, URI FROM talk WHERE URI IS NOT NULL ORDER BY ID")
    talks = cursor.fetchall()

    conn.close()
    return talks


def save_to_json(data, output_path):
    """Save talk data to JSON file."""
    with open(output_path, "w") as f:
        json.dump(data, indent=2, fp=f)


def get_topic_ids(topic_db_path, content_identifier):
    """
    Get all topic_ids for a given content_identifier from topic database.

    Args:
        topic_db_path: Path to topic.content.db
        content_identifier: The data-aid value to look up

    Returns:
        List of topic_ids
    """
    conn = sqlite3.connect(topic_db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT topic_id FROM content_reference WHERE content_identifier = ?",
        (content_identifier,),
    )

    topic_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    return topic_ids


def create_talk_topic_table(db_path):
    """Create talk_topic table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS talk_topic (
            TalkID INTEGER NOT NULL,
            TopicID TEXT NOT NULL,
            PRIMARY KEY (TalkID, TopicID)
        )
    """
    )

    conn.commit()
    conn.close()


def populate_talk_topic_table(core_db_path, topic_db_path, json_path):
    """
    Populate talk_topic table with mappings from JSON data.

    Args:
        core_db_path: Path to core database
        topic_db_path: Path to topic database
        json_path: Path to JSON file with talk data
    """
    # Load JSON data
    with open(json_path, "r") as f:
        talk_data = json.load(f)

    # Create table if needed
    create_talk_topic_table(core_db_path)

    # Connect to databases
    core_conn = sqlite3.connect(core_db_path)
    core_cursor = core_conn.cursor()

    total_mappings = 0
    talks_with_topics = 0
    talks_without_topics = 0

    print("\n" + "=" * 80)
    print("Populating talk_topic table...")
    print("=" * 80)

    for entry in talk_data:
        talk_id = entry["talkID"]
        data_aid = entry["dataAid"]

        if not data_aid:
            talks_without_topics += 1
            continue

        # Get all topic_ids for this data_aid
        topic_ids = get_topic_ids(topic_db_path, data_aid)

        if topic_ids:
            talks_with_topics += 1
            for topic_id in topic_ids:
                try:
                    core_cursor.execute(
                        "INSERT OR IGNORE INTO talk_topic (TalkID, TopicID) VALUES (?, ?)",
                        (talk_id, topic_id),
                    )
                    total_mappings += 1
                except sqlite3.Error as e:
                    print(f"Error inserting TalkID {talk_id}, TopicID {topic_id}: {e}")

            print(f"✓ TalkID {talk_id}: Added {len(topic_ids)} topic mapping(s)")
        else:
            talks_without_topics += 1
            print(f"⚠️  TalkID {talk_id}: No topics found for data-aid {data_aid}")

    core_conn.commit()
    core_conn.close()

    print("\n" + "=" * 80)
    print("Summary:")
    print(f"  Talks with topics: {talks_with_topics}")
    print(f"  Talks without topics: {talks_without_topics}")
    print(f"  Total topic mappings inserted: {total_mappings}")
    print("=" * 80)


def retry_failed_talk(talk_id, uri, original_title):
    """
    Retry fetching data-aid for a failed talk by searching TOC entries.

    Args:
        talk_id: The talk ID
        uri: The original URI
        original_title: The full title from the database

    Returns:
        data_aid string or None
    """
    try:
        url = f"{API_BASE_URL}{uri}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # First, try the normal way one more time
        data_aid = (
            data.get("content", {})
            .get("meta", {})
            .get("pageAttributes", {})
            .get("data-aid")
        )
        if data_aid:
            safe_print(f"✓ RETRY TalkID {talk_id}: Found data-aid on second attempt")
            return data_aid

        # If still no data-aid, search through TOC entries
        toc_entries = data.get("toc", {}).get("entries", [])

        if not toc_entries:
            safe_print(f"⚠️  RETRY TalkID {talk_id}: No TOC entries found")
            return None

        matched_uri = None

        print("TOC For:", data.get("toc", {}).get("title", ""))

        for entry in toc_entries:
            # Check if this entry is a section
            if "section" in entry and entry["section"]:
                section_entries = entry["section"].get("entries", [])

                for section_entry in section_entries:
                    entry_title = section_entry.get("content", {}).get("title", "")

                    if entry_title == original_title:
                        print("MATCH", entry_title)
                        matched_uri = section_entry.get("content", {}).get("uri", "")

        print("MATCHED URI", matched_uri)
        if matched_uri:
            # Fetch from the matched URI
            matched_url = f"{API_BASE_URL}{matched_uri}"
            matched_response = requests.get(matched_url, timeout=30)
            matched_response.raise_for_status()

            matched_data = matched_response.json()

            matched_data_aid = (
                matched_data.get("content", {})
                .get("meta", {})
                .get("pageAttributes", {})
                .get("data-aid")
            )
            if matched_data_aid:
                safe_print(f"✓ RETRY TalkID {talk_id}: Found data-aid via TOC match")
                return matched_data_aid

        safe_print(f"✗ RETRY TalkID {talk_id}: Could not find data-aid after retry")
        return None

    except Exception as e:
        safe_print(f"✗ RETRY TalkID {talk_id}: Error during retry - {e}")
        return None


def retry_failed_talks(core_db_path, json_path):
    """
    Retry fetching data-aid for talks that failed in the initial run.

    Args:
        core_db_path: Path to core database
        json_path: Path to JSON file with talk data

    Returns:
        Number of talks successfully recovered
    """
    # Load JSON data
    with open(json_path, "r") as f:
        talk_data = json.load(f)

    # Filter for failed talks
    failed_talks = [entry for entry in talk_data if entry["dataAid"] is None]

    if not failed_talks:
        print("No failed talks to retry")
        return 0

    print(f"\nFound {len(failed_talks)} failed talks to retry")
    print("-" * 80)

    # Get URIs for failed talks
    conn = sqlite3.connect(core_db_path)
    cursor = conn.cursor()

    recovered = 0

    with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
        future_to_talk = {}

        for entry in failed_talks:
            talk_id = entry["talkID"]
            cursor.execute("SELECT URI, Title FROM talk WHERE ID = ?", (talk_id,))
            result = cursor.fetchone()

            if result:
                uri, title = result
                future = executor.submit(retry_failed_talk, talk_id, uri, title)
                future_to_talk[future] = entry

        for future in as_completed(future_to_talk):
            entry = future_to_talk[future]
            data_aid = future.result()

            if data_aid:
                entry["dataAid"] = data_aid
                recovered += 1

    conn.close()

    # Save updated JSON
    with open(json_path, "w") as f:
        json.dump(talk_data, indent=2, fp=f)

    print("-" * 80)
    print(f"Retry complete: Recovered {recovered}/{len(failed_talks)} talks")

    return recovered


def populate_talk_topic_table(core_db_path, topic_db_path, json_path):
    """
    Populate talk_topic table with mappings from JSON data.

    Args:
        core_db_path: Path to core database
        topic_db_path: Path to topic database
        json_path: Path to JSON file with talk data
    """
    # Load JSON data
    with open(json_path, "r") as f:
        talk_data = json.load(f)

    # Create table if needed
    create_talk_topic_table(core_db_path)

    # Connect to databases
    core_conn = sqlite3.connect(core_db_path)
    core_cursor = core_conn.cursor()

    total_mappings = 0
    talks_with_topics = 0
    talks_without_topics = 0

    print("\n" + "=" * 80)
    print("Populating talk_topic table...")
    print("=" * 80)

    for entry in talk_data:
        talk_id = entry["talkID"]
        data_aid = entry["dataAid"]

        if not data_aid:
            talks_without_topics += 1
            continue

        # Get all topic_ids for this data_aid
        topic_ids = get_topic_ids(topic_db_path, data_aid)

        if topic_ids:
            talks_with_topics += 1
            for topic_id in topic_ids:
                try:
                    core_cursor.execute(
                        "INSERT OR IGNORE INTO talk_topic (TalkID, TopicID) VALUES (?, ?)",
                        (talk_id, topic_id),
                    )
                    total_mappings += 1
                except sqlite3.Error as e:
                    print(f"Error inserting TalkID {talk_id}, TopicID {topic_id}: {e}")

            print(f"✓ TalkID {talk_id}: Added {len(topic_ids)} topic mapping(s)")
        else:
            talks_without_topics += 1
            print(f"⚠️  TalkID {talk_id}: No topics found for data-aid {data_aid}")

    core_conn.commit()
    core_conn.close()

    print("\n" + "=" * 80)
    print("Summary:")
    print(f"  Talks with topics: {talks_with_topics}")
    print(f"  Talks without topics: {talks_without_topics}")
    print(f"  Total topic mappings inserted: {total_mappings}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="General Conference Talk Topic Extractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("core_db", help="Path to core database (e.g., core.52.db)")
    parser.add_argument(
        "topic_db", help="Path to topic database (e.g., topic.content.db)"
    )
    parser.add_argument("output_json", help="Path to output JSON file")
    parser.add_argument(
        "--retry", action="store_true", help="Enable retry logic for failed talks"
    )

    args = parser.parse_args()

    core_db_path = args.core_db
    topic_db_path = args.topic_db
    output_json_path = args.output_json
    enable_retry = args.retry

    print("=" * 80)
    print("General Conference Talk Topic Extractor")
    print("=" * 80)
    print(f"Core Database: {core_db_path}")
    print(f"Topic Database: {topic_db_path}")
    print(f"Output JSON: {output_json_path}")
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Worker Threads: {WORKER_COUNT}")
    print(f"Retry Enabled: {enable_retry or 'Auto (after initial run)'}")
    print("=" * 80)

    # Step 1: Get talks from database
    print("\nStep 1: Loading talks from database...")
    talks = get_talks_from_db(core_db_path)
    print(f"Found {len(talks)} talks with URIs")

    # Step 2: Fetch data from API (multithreaded)
    print(f"\nStep 2: Fetching talk data from API ({WORKER_COUNT} workers)...")
    print("-" * 80)

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
        # Submit all tasks
        future_to_talk = {
            executor.submit(fetch_talk_data, talk_id, uri): (talk_id, uri)
            for talk_id, uri in talks
        }

        # Process completed tasks
        completed = 0
        for future in as_completed(future_to_talk):
            talk_id, data_aid = future.result()
            results.append({"talkID": talk_id, "dataAid": data_aid})
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
    save_to_json(results, output_json_path)
    successful = sum(1 for r in results if r["dataAid"] is not None)
    print(
        f"Saved {len(results)} talks ({successful} successful, {len(results)-successful} failed)"
    )

    # Step 3.5: Retry failed talks (always runs automatically)
    print("\nStep 3.5: Retrying failed talks...")
    print("=" * 80)
    recovered = retry_failed_talks(core_db_path, output_json_path)

    if recovered > 0:
        print(f"\n✓ Recovered {recovered} additional talks")

    # Step 4: Populate talk_topic table
    print("\nStep 4: Populating talk_topic table...")
    if recovered > 0:
        populate_talk_topic_table(core_db_path, topic_db_path, output_json_path)

    print("\n" + "=" * 80)
    print("✓ All steps completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
