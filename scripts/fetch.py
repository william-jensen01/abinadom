#!/usr/bin/env python3
"""
fetch: Church API → committed JSON files.

The only step that talks to the network. Calls the existing scripts'
functions in order (see docs/update/FETCH_BUILD_SPEC.md):

  1. Conference contents page → talk URIs         (fresh)
  2. Each talk page → talk_metadata.json          (cached)
  3. Each talk page → talk_previews.json          (cached)
  4. Topics index → topics.json                   (fresh)
  5. Every topic page → conference_topics.json    (fresh)

Everything is fetched before anything is written, so a failure leaves the
files untouched.

Usage:
    pipenv run python scripts/fetch.py --conference 2026-04
    pipenv run python scripts/fetch.py --all
"""

import argparse
import logging
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from api.fetch_talk_previews import (
    all_conferences,
    fetch_previews,
    fetch_talk_list,
    parse_conference,
    save_previews,
)
from process_topic_talks.extract_talk_metadata import fetch_all_metadata, save_metadata
from scripts.process_topics import (
    TOPICS_FILE,
    fetch_topics_index,
    load_previous,
    process_topics,
    save_results,
    save_topics_index,
)
from utils.church_api import cached_session, fresh_session
from utils.json_io import read_json


def print_summary(uris, metadata, previews, new_topics, missing_pages):
    fetched = {r["uri"] for r in metadata}
    print("\n" + "=" * 70)
    print("fetch summary")
    print("=" * 70)
    print(f"Talks fetched: {len(metadata)}/{len(uris)}")
    failed = [u for u in uris if u not in fetched]
    if failed:
        print(f"Fetch failures (old entries kept): {len(failed)}")
        for u in failed:
            print(f"  {u}")
    for field in ("title", "speaker_role", "data_aid"):
        missing = [r["uri"] for r in metadata if not r[field]]
        print(f"Missing {field}: {len(missing)}")
        for u in missing:
            print(f"  {u}")
    missing = [r["uri"] for r in previews if not r["preview"]]
    print(f"Missing preview: {len(missing)}")
    for u in missing:
        print(f"  {u}")
    print(f"New topics: {len(new_topics)}")
    for t in new_topics:
        print(f"  {t['title']} ({t['uri']})")
    print(f"Topic pages 404 (old entries kept): {len(missing_pages)}")
    for t in missing_pages:
        print(f"  {t['title']} ({t['uri']})")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch Church API data into the committed JSON files.")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--conference", type=parse_conference, metavar="YYYY-MM")
    which.add_argument("--all", action="store_true", help="1971-04 through the latest conference")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    conferences = all_conferences() if args.all else [args.conference]
    fresh = fresh_session()
    cached = cached_session()

    print(f"Step 1: conference contents ({len(conferences)} conferences)")
    talks = fetch_talk_list(fresh, conferences)
    uris = [t["uri"] for t in talks]

    print(f"Step 2: talk metadata ({len(uris)} talks)")
    metadata = fetch_all_metadata(cached, uris)

    print("Step 3: talk previews")
    previews = fetch_previews(cached, talks)

    print("Step 4: topics index")
    topics = fetch_topics_index(fresh)
    known = {t["uri"] for t in read_json(TOPICS_FILE)}
    new_topics = [t for t in topics if t["uri"] not in known]

    print(f"Step 5: topic pages ({len(topics)} topics)")
    topic_results, missing_pages = process_topics(topics, fresh, load_previous())

    save_metadata(metadata)
    save_previews(previews)
    save_topics_index(topics)
    save_results(topic_results)

    print_summary(uris, metadata, previews, new_topics, missing_pages)


if __name__ == "__main__":
    main()
