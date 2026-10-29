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
from typing import Dict, List, Optional

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

# Church items that never have an SCI talk (see docs/backfill/UNMATCHED_TALKS_ANALYSIS.md).
# Matched on the lowercased title; only applied to URIs that found no SCI talk.
EXPECTED_CHURCH_TITLES = [
    ("sustaining", "sustaining of"),  # incl. "The Sustaining of Church Officers"
    ("sustaining", "solemn assembly"),
    ("statistical report", "statistical report"),
    ("audit/finance report", "audit"),  # Audit Report, Audit Committee, Auditing Department
    ("audit/finance report", "finance committee report"),
    ("welfare services", "welfare services"),
    ("video", "video"),
    ("broadcast", "music and the spoken word"),
]
EXPECTED_CHURCH_URIS = {  # one-offs whose titles don't say what they are
    "/general-conference/1976/04/regional-representatives-announcement": "one-off",
    "/general-conference/1976/10/the-reconstitution-of-the-first-quorum-of-the-seventy": "one-off",
    "/general-conference/1977/04/presentation-of-scouting-award": "one-off",
    "/general-conference/1995/10/the-family-a-proclamation-to-the-world": "one-off",
}


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
def expected_church_category(uri: str, title: str) -> Optional[str]:
    """Category of a Church item that is expected to have no SCI talk, else None."""
    if uri in EXPECTED_CHURCH_URIS:
        return EXPECTED_CHURCH_URIS[uri]
    lowered = (title or "").lower()
    for category, needle in EXPECTED_CHURCH_TITLES:
        if needle in lowered:
            return category
    return None


def bucket_church_items(items: Dict[str, str]) -> Dict:
    """Split {uri: title} into expected (by category) and unexpected."""
    expected: Dict[str, List[str]] = {}
    unexpected = []
    for uri, title in sorted(items.items()):
        category = expected_church_category(uri, title)
        if category:
            expected.setdefault(category, []).append(uri)
        else:
            unexpected.append({"uri": uri, "title": title})
    return {"expected": expected, "unexpected": unexpected}


def match_report(core_db_path: str) -> Dict:
    """How SCI conference talks and Church URIs match up (after step 3)."""
    db = Database(core_db_path, timeout=60)
    index = load_talk_uri_index(db)
    church_titles = {r["uri"]: r.get("title") for r in read_json(PREVIEWS_PATH)}
    church_titles.update({r["uri"]: r.get("title") for r in read_json(METADATA_PATH)})
    church_uris = set(church_titles)
    corrections = read_json(CORRECTIONS_PATH)
    corrected_ids = {c["TalkID"] for c in corrections}
    ensign_ids = {c["TalkID"] for c in corrections if not c.get("gc")}

    sci_talks = db.select(
        """
        SELECT t.ID, t.Title, t.Date, t.URL, tm.uri_gc, tm.uri_l
          FROM talk t
          LEFT JOIN talk_metadata tm ON tm.talk_id = t.ID
         WHERE t.Corpus = 'G'
         ORDER BY t.ID
        """
    )
    matched, by_correction = 0, 0
    sci_unmatched = {"expected_ensign": [], "unexpected": []}
    for t in sci_talks:
        if t["uri_gc"] in church_uris or t["uri_l"] in church_uris:
            matched += 1
            by_correction += t["ID"] in corrected_ids
        else:
            bucket = "expected_ensign" if t["ID"] in ensign_ids else "unexpected"
            sci_unmatched[bucket].append(
                {"talk_id": t["ID"], "date": t["Date"], "title": t["Title"], "uri_gc": t["uri_gc"]}
            )

    church_unmatched = bucket_church_items(
        {u: church_titles[u] for u in church_uris if u not in index}
    )
    topic_unmatched = bucket_church_items(
        {
            e["uri"]: e.get("title")
            for t in read_json(TOPICS_PATH)
            for e in t["entries"]
            if e["uri"] not in index
        }
    )

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
        "topic_entries_without_sci_talk": topic_unmatched,
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
    print(
        f"\nSCI talks with no Church data: {len(sci['unexpected'])} unexpected"
        f" ({len(sci['expected_ensign'])} expected: Ensign-only, gc=false correction)"
    )
    by_year = Counter((t["date"] or "?")[:4] for t in sci["unexpected"])
    if by_year:
        print("  by year: " + ", ".join(f"{y}: {n}" for y, n in sorted(by_year.items())))
    for t in sci["unexpected"][:REPORT_SHOWN]:
        print(f"  {t['talk_id']:>6} {t['date']} {t['title']}  ({t['uri_gc']})")
    if len(sci["unexpected"]) > REPORT_SHOWN:
        print(f"  ... {len(sci['unexpected']) - REPORT_SHOWN} more in the saved report")

    for key, label in (
        ("church_uris_without_sci_talk", "Church URIs with no SCI talk"),
        ("topic_entries_without_sci_talk", "Topic entries with no SCI talk"),
    ):
        buckets = report[key]
        expected = ", ".join(f"{c}: {len(u)}" for c, u in sorted(buckets["expected"].items()))
        print(f"\n{label}: {len(buckets['unexpected'])} unexpected (expected: {expected or 'none'})")
        for item in buckets["unexpected"][:REPORT_SHOWN]:
            print(f"  {item['uri']}  {item['title']}")
        if len(buckets["unexpected"]) > REPORT_SHOWN:
            print(f"  ... {len(buckets['unexpected']) - REPORT_SHOWN} more in the saved report")

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
