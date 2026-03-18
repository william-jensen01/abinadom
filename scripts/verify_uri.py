"""
Verify URI columns in the database against conference sessions JSON.
"""

import json
import sys
import os
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import backfill_core_db as core_db


def load_conference_data(json_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Load conference sessions from JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_all_uris(sessions_dict: Dict[str, List[Dict[str, Any]]]) -> set:
    """
    Collect all URIs from the conference sessions JSON.

    Returns a set of URIs for fast lookup.
    """
    all_uris = set()

    for session_key, talks in sessions_dict.items():
        for talk in talks:
            content = talk.get("content", {})
            uri = content.get("uri")

            if uri:
                all_uris.add(uri)
            else:
                print(f"Warning: Talk in session {session_key} has no URI")

    return all_uris


def get_all_talks_from_db() -> List[Dict[str, Any]]:
    """
    Get all talks from the database with ID and URI_GC.
    """
    query = """
        SELECT ID, URI_GC
        FROM talk
        WHERE URI_GC IS NOT NULL AND URI_GC != '';
    """
    return core_db.select(query)


def find_invalid_db_talks(json_uris: set) -> List[Dict[str, Any]]:
    """
    Loop through all talks in the database and check if their URI_GC is in the JSON URIs set.
    Return talks with invalid URIs.
    """
    invalid_talks = []
    valid_count = 0

    db_talks = get_all_talks_from_db()
    total_count = len(db_talks)
    print(
        f"Checking {total_count} database talks against {len(json_uris)} JSON URIs..."
    )
    print("-" * 60)

    for talk in db_talks:
        talk_id = talk["ID"]
        uri_gc = talk["URI_GC"]

        if uri_gc not in json_uris:
            invalid_talks.append({"uri": uri_gc, "TalkID": talk_id})
            print(f"✗ Invalid: Talk ID {talk_id}, URI: {uri_gc}")
        else:
            valid_count += 1
            print(f"✓ Valid: Talk ID {talk_id}, URI: {uri_gc}")

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Total DB talks checked: {total_count}")
    print(f"  Valid talks (URI in JSON): {valid_count}")
    print(f"  Invalid talks (URI not in JSON): {len(invalid_talks)}")
    print(f"{'='*60}\n")

    return invalid_talks


def save_invalid_uris(invalid_uris: List[Dict[str, Any]], output_path: str):
    """Save invalid URIs to a JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(invalid_uris, f, indent=2, ensure_ascii=False)
    print(f"Invalid URIs saved to: {output_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_uris.py <input_json_path> [output_json_path]")
        print("Example: python verify_uris.py conferences.json invalid_uris.json")
        sys.exit(1)

    input_json = sys.argv[1]
    output_json = sys.argv[2] if len(sys.argv) > 2 else "invalid_uris.json"

    if not os.path.exists(input_json):
        print(f"Error: Input file not found: {input_json}")
        sys.exit(1)

    print(f"Loading conference data from: {input_json}")
    sessions_dict = load_conference_data(input_json)
    total_sessions = len(sessions_dict)
    total_talks = sum(len(talks) for talks in sessions_dict.values())
    print(
        f"Loaded {total_sessions} conference sessions with {total_talks} total talks\n"
    )

    print("Collecting URIs from JSON...")
    json_uris = collect_all_uris(sessions_dict)
    print(f"Collected {len(json_uris)} unique URIs from JSON\n")

    print("Verifying database talks against JSON URIs...")
    invalid_talks = find_invalid_db_talks(json_uris)

    if invalid_talks:
        save_invalid_uris(invalid_talks, output_json)
    else:
        print("All database talks have valid URIs! No output file created.")


if __name__ == "__main__":
    main()
