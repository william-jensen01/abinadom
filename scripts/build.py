#!/usr/bin/env python3
"""
build: raw SCI release + committed JSON → finished database.

Runs offline. Copies db/sci/core.N.db and db/sci/content.N.db, enriches the
copy by calling the backfill scripts' run() functions in order, and only then
moves it to db/core.N.db and db/content.N.db. The raw release is never
modified, and a failed build leaves no output. See
docs/update/FETCH_BUILD_SPEC.md.

Usage:
    pipenv run python scripts/build.py --version 53 [--force]
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter
from typing import Dict, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION_DIR = os.path.join(ROOT_DIR, "db", "one-off-migration")
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, MIGRATION_DIR)

from db import EXPECTED_CONTENT_TABLES, EXPECTED_CORE_TABLES, Database, validate_schema

import backfill_talk_kicker
import backfill_talk_metadata
import backfill_talk_metadata_role_extraction
import backfill_talk_preview
import backfill_talk_texts
import backfill_talk_uri
import backfill_topics
import create_talk_metadata_table
from create_talk_metadata_table import duplicate_uris, load_talk_uri_index

DB_DIR = os.path.join(ROOT_DIR, "db")
RAW_DIR = os.path.join(DB_DIR, "sci")
METADATA_PATH = os.path.join(MIGRATION_DIR, "talk_metadata.json")
PREVIEWS_PATH = os.path.join(MIGRATION_DIR, "talk_previews.json")
TOPICS_PATH = os.path.join(MIGRATION_DIR, "conference_topics.json")
CORRECTIONS_PATH = os.path.join(MIGRATION_DIR, "talk_corrections.json")
REPORT_SHOWN = 20  # list items printed per report section; the saved report has all


def read_json(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def step(number, title):
    print("\n" + "=" * 80)
    print(f"Step {number}: {title}")
    print("=" * 80)


# ---------------------------------------------------------------------------
# Step 4: match report
# ---------------------------------------------------------------------------
def match_report(core_db_path: str) -> Dict:
    """How SCI conference talks and Church URIs match up (after step 3)."""
    db = Database(core_db_path, timeout=60)
    index = load_talk_uri_index(db)
    church_uris = {r["uri"] for r in read_json(METADATA_PATH)} | {
        r["uri"] for r in read_json(PREVIEWS_PATH)
    }
    corrections = read_json(CORRECTIONS_PATH)
    corrected_ids = {c["TalkID"] for c in corrections}

    sci_talks = db.select(
        """
        SELECT t.ID, t.Title, t.Date, t.URL, tm.uri_gc, tm.uri_l
          FROM talk t
          LEFT JOIN talk_metadata tm ON tm.talk_id = t.ID
         WHERE t.Corpus = 'G'
         ORDER BY t.ID
        """
    )
    matched, by_correction, sci_unmatched = 0, 0, []
    for t in sci_talks:
        if t["uri_gc"] in church_uris or t["uri_l"] in church_uris:
            matched += 1
            by_correction += t["ID"] in corrected_ids
        else:
            sci_unmatched.append(
                {"talk_id": t["ID"], "date": t["Date"], "title": t["Title"], "uri_gc": t["uri_gc"]}
            )

    church_unmatched = sorted(u for u in church_uris if u not in index)

    duplicates = {
        uri: sorted(ids) for uri, ids in duplicate_uris(index).items() if uri in church_uris
    }

    # Corrections are keyed by SCI talk ID; flag any whose talk no longer has
    # the URL the correction was written for (SCI renumbered talks).
    urls = {r["ID"]: r["URL"] for r in db.select("SELECT ID, URL FROM talk")}
    stale_corrections = []
    for c in corrections:
        if not c.get("uri"):
            continue  # nothing to check against
        current = backfill_talk_uri.extract_uri_gc(urls.get(c["TalkID"]))
        if current != c["uri"]:
            stale_corrections.append(
                {"TalkID": c["TalkID"], "expected_uri": c["uri"], "current_uri": current}
            )

    report = {
        "sci_conference_talks": len(sci_talks),
        "matched": matched,
        "matched_via_correction": by_correction,
        "sci_talks_without_church_data": sci_unmatched,
        "church_uris_without_sci_talk": church_unmatched,
        "church_uris_claimed_by_several_talks": duplicates,
        "stale_corrections": stale_corrections,
    }
    print_match_report(report)
    return report


def print_match_report(report: Dict) -> None:
    total = report["sci_conference_talks"]
    pct = lambda n: f"{n / max(total, 1) * 100:.1f}%"
    print(f"SCI conference talks (Corpus G): {total}")
    print(f"  matched to Church data: {report['matched']} ({pct(report['matched'])})")
    print(f"    via a correction:     {report['matched_via_correction']}")

    sci = report["sci_talks_without_church_data"]
    print(f"\nSCI talks with no Church data: {len(sci)}")
    by_year = Counter((t["date"] or "?")[:4] for t in sci)
    print("  by year: " + ", ".join(f"{y}: {n}" for y, n in sorted(by_year.items())))
    for t in sci[:REPORT_SHOWN]:
        print(f"  {t['talk_id']:>6} {t['date']} {t['title']}  ({t['uri_gc']})")
    if len(sci) > REPORT_SHOWN:
        print(f"  ... {len(sci) - REPORT_SHOWN} more in the saved report")

    church = report["church_uris_without_sci_talk"]
    print(f"\nChurch URIs with no SCI talk: {len(church)}")
    for u in church[:REPORT_SHOWN]:
        print(f"  {u}")
    if len(church) > REPORT_SHOWN:
        print(f"  ... {len(church) - REPORT_SHOWN} more in the saved report")

    dups = report["church_uris_claimed_by_several_talks"]
    print(f"\nChurch URIs claimed by several SCI talks: {len(dups)}")
    for uri, ids in dups.items():
        print(f"  {uri}: talks {ids}")

    stale = report["stale_corrections"]
    print(f"\nCorrections whose talk ID no longer has the expected URI: {len(stale)}")
    for c in stale:
        print(f"  TalkID {c['TalkID']}: expected {c['expected_uri']}, now {c['current_uri']}")


# ---------------------------------------------------------------------------
# Steps 10-11
# ---------------------------------------------------------------------------
def apply_title_corrections(core_db_path: str) -> int:
    db = Database(core_db_path, read_only=False)
    count = 0
    for c in read_json(CORRECTIONS_PATH):
        if c.get("title"):
            db.execute("UPDATE talk SET Title = ? WHERE ID = ?", (c["title"], c["TalkID"]))
            print(f"  TalkID {c['TalkID']}: {c['title']}")
            count += 1
    return count


def check(core_db_path: str, content_db_path: str) -> Dict:
    """Schema check against db/__init__.py, then coverage summary."""
    for path, expected, name in (
        (core_db_path, EXPECTED_CORE_TABLES, "core"),
        (content_db_path, EXPECTED_CONTENT_TABLES, "content"),
    ):
        conn = sqlite3.connect(path)
        try:
            validate_schema(conn, expected, name)
        finally:
            conn.close()
    print("  ✓ schema matches db/__init__.py")

    db = Database(core_db_path, timeout=60)
    coverage = db.select_one(
        """
        SELECT COUNT(*) AS talks,
               COUNT(tm.uri_gc) AS uri_gc,
               COUNT(tm.data_aid) AS data_aid,
               COUNT(tm.speaker_role_id) AS speaker_role,
               COUNT(tm.kicker) AS kicker,
               COUNT(NULLIF(tm.talk_preview, '')) AS preview
          FROM talk t
          LEFT JOIN talk_metadata tm ON tm.talk_id = t.ID
         WHERE t.Corpus = 'G'
        """
    )
    coverage["topics"] = db.scalar("SELECT COUNT(*) FROM conference_topic")
    coverage["talk_topics"] = db.scalar("SELECT COUNT(*) FROM talk_topic")
    print("  Corpus G coverage:")
    for key, value in coverage.items():
        print(f"    {key:<14} {value}")
    return coverage


def finalize(tmp_path: str, out_path: str) -> None:
    """Fold any WAL back into the file and move it into place."""
    conn = sqlite3.connect(tmp_path)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
    finally:
        conn.close()
    for suffix in ("-wal", "-shm"):
        if os.path.exists(out_path + suffix):
            os.remove(out_path + suffix)
    os.replace(tmp_path, out_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build(version: str, force: bool = False) -> Dict:
    raw_core = os.path.join(RAW_DIR, f"core.{version}.db")
    raw_content = os.path.join(RAW_DIR, f"content.{version}.db")
    out_core = os.path.join(DB_DIR, f"core.{version}.db")
    out_content = os.path.join(DB_DIR, f"content.{version}.db")
    report_path = os.path.join(DB_DIR, f"build_report.{version}.json")

    for path in (raw_core, raw_content):
        if not os.path.exists(path):
            sys.exit(f"Raw release not found: {path}")
    existing = [p for p in (out_core, out_content) if os.path.exists(p)]
    if existing and not force:
        sys.exit(f"Build already exists: {', '.join(existing)} (use --force to overwrite)")

    core = out_core + ".building"
    content = out_content + ".building"
    start = time.time()

    step(0, "Copy raw release")
    for src, dst in ((raw_core, core), (raw_content, content)):
        for suffix in ("", "-wal", "-shm", "-journal"):
            if os.path.exists(dst + suffix):
                os.remove(dst + suffix)
        shutil.copyfile(src, dst)
        print(f"  {src} → {dst}")

    step(1, "Talk text (content.talkbody)")
    backfill_talk_texts.run(content)

    step(2, "talk_metadata table")
    create_talk_metadata_table.run(core)

    step(3, "Match key (uri_gc, uri_l + URI corrections)")
    backfill_talk_uri.run(core, CORRECTIONS_PATH)

    step(4, "Match report")
    report = match_report(core)

    step(5, "Church metadata (title, speaker role, data_aid)")
    backfill_talk_metadata.run(core, METADATA_PATH)

    step(6, "Missing speaker roles (SCI HTML)")
    backfill_talk_metadata_role_extraction.run(core, content)

    step(7, "Kicker (SCI HTML)")
    backfill_talk_kicker.run(core, content)

    step(8, "Previews")
    backfill_talk_preview.run(core, PREVIEWS_PATH)

    step(9, "Topics")
    backfill_topics.run(core, TOPICS_PATH)

    step(10, "Title corrections")
    report["title_corrections"] = apply_title_corrections(core)

    step(11, "Check")
    report["coverage"] = check(core, content)

    finalize(core, out_core)
    finalize(content, out_content)
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("\n" + "=" * 80)
    print(f"Built {out_core} and {out_content} in {time.time() - start:.0f}s")
    print(f"Match report: {report_path}")
    print("=" * 80)
    return report


def main():
    parser = argparse.ArgumentParser(description="Build the finished DB from a raw SCI release + JSON.")
    parser.add_argument("--version", required=True, help="SCI release number, e.g. 53")
    parser.add_argument("--force", action="store_true", help="overwrite an existing build")
    args = parser.parse_args()
    build(args.version, args.force)


if __name__ == "__main__":
    main()
