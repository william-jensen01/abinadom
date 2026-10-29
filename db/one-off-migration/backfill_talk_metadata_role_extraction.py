#!/usr/bin/env python3
"""
Backfill speaker_role for general conference talks by extracting it from HTML.

Targets all talks in the core DB where talk.Corpus is 'G' (General Conference)
or 'E' whose talk_metadata.speaker_role_id is not yet set (e.g. by
backfill_talk_metadata.py from the Church API). HTML is sourced from the
content DB's talkbody.TextRaw.

1. Ensures the speaker_role table exists
2. Queries the core DB for GC talks lacking a speaker role
3. Fetches TextRaw HTML from the content DB for each talk
4. Extracts speaker role using several HTML patterns
5. Inserts new roles into speaker_role and upserts talk_metadata.speaker_role_id

Extraction patterns (tried in order):
  - <p class="author-role">
  - Second <p> within <div class="byline">
  - <div class="gcspkpos">

Usage:
    pipenv run py db/one-off-migration/backfill_talk_metadata_role_extraction.py
    pipenv run py db/one-off-migration/backfill_talk_metadata_role_extraction.py --dry-run
    pipenv run py db/one-off-migration/backfill_talk_metadata_role_extraction.py --overwrite

Example:
    pipenv run py db/one-off-migration/backfill_talk_metadata_role_extraction.py --core-db ./db/core.52.db --content-db ./db/content.52.db
"""

import argparse
import re
import sys
import os
import sqlite3
from typing import Dict, List, Optional, Set

from bs4 import BeautifulSoup

# Ensure Unicode output works on Windows (cp1252 can't encode ✓, ⚠️, etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add parent directories to path for importing Database
db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(db_dir)
sys.path.insert(0, root_dir)

from db import Database, CORE_DB_PATH, CONTENT_DB_PATH

migration_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, migration_dir)
from create_talk_metadata_table import upsert_talk_metadata


# ---------------------------------------------------------------------------
# Text utilities (shared with backfill_talk_metadata.py)
# ---------------------------------------------------------------------------


def title_case_role(text: str) -> str:
    """Convert role text to proper title case."""
    if not text:
        return ""

    lowercase_words = {
        "a",
        "an",
        "the",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "to",
        "with",
        "over",
        "under",
        "upon",
        "after",
        "before",
        "and",
        "but",
        "or",
        "nor",
        "yet",
        "so",
    }

    words = text.split()
    result = []
    for i, word in enumerate(words):
        if i == 0:
            result.append(word.capitalize())
        elif word.lower() in lowercase_words:
            result.append(word.lower())
        else:
            result.append(word.capitalize())

    return " ".join(result)


def slugify(text: str) -> str:
    """Convert text to lowercase hyphenated slug."""
    if not text:
        return ""
    slug = text.lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------


def _valid_role(text: str) -> Optional[str]:
    """
    Return text if it is a usable role string, otherwise None.

    Discards values that are entirely wrapped in parentheses, e.g. "(Bishop)".
    """
    if not text:
        return None
    if re.fullmatch(r"\(.*\)", text):
        return None
    return text


def extract_speaker_role(html: str) -> Optional[str]:
    """
    Extract speaker role text from talk HTML.

    Tries several patterns in order:
    1. <p class="author-role"> — direct class match
    2. Second <p> within <div class="byline"> — covers author-role, id="p3", empty-class variants
    3. <div class="gcspkpos"> — older General Conference era markup

    Returns the stripped text of the role element, or None if not found or invalid.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Method 1: explicit author-role class
    author_role_el = soup.find("p", class_="author-role")
    if author_role_el:
        if role := _valid_role(author_role_el.get_text(strip=True)):
            return role

    # Method 2: second <p> inside any <div class="byline">
    byline = soup.find("div", class_="byline")
    if byline:
        paragraphs = byline.find_all("p", recursive=False)
        if len(paragraphs) >= 2:
            if role := _valid_role(paragraphs[1].get_text(strip=True)):
                return role

    # Method 3: <div class="gcspkpos"> (General Conference speaker position)
    gcspkpos = soup.find("p", class_="gcspkpos")
    if gcspkpos:
        if role := _valid_role(gcspkpos.get_text(strip=True)):
            return role

    return None


# ---------------------------------------------------------------------------
# Schema setup (idempotent — mirrors backfill_talk_metadata.py)
# ---------------------------------------------------------------------------


def ensure_speaker_role_table(db: Database):
    """Create the speaker_role table if it doesn't exist."""
    print("\nStep 1: Ensuring speaker_role table exists...")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS speaker_role (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE
        )
        """
    )
    print("  ✓ speaker_role table ready")


# ---------------------------------------------------------------------------
# Role table helpers
# ---------------------------------------------------------------------------


def get_or_create_role(
    db: Database, role_map: Dict[str, int], raw_role: str
) -> Optional[int]:
    """
    Return the speaker_role.id for *raw_role*, inserting a new row if needed.
    Updates role_map in-place as a cache.
    """
    normalized = title_case_role(raw_role)
    if not normalized:
        return None

    if normalized in role_map:
        return role_map[normalized]

    # Check DB
    existing = db.select_one(
        "SELECT id FROM speaker_role WHERE role = ?", (normalized,)
    )
    if existing:
        role_map[normalized] = existing["id"]
        return existing["id"]

    # Insert
    slug = slugify(normalized)

    # Handle slug collisions
    candidate_slug = slug
    counter = 2
    while db.select_one(
        "SELECT id FROM speaker_role WHERE slug = ?", (candidate_slug,)
    ):
        candidate_slug = f"{slug}-{counter}"
        counter += 1

    try:
        db.execute(
            "INSERT INTO speaker_role (role, slug) VALUES (?, ?)",
            (normalized, candidate_slug),
        )
        result = db.select_one(
            "SELECT id FROM speaker_role WHERE role = ?", (normalized,)
        )
        if result:
            role_map[normalized] = result["id"]
            print(
                f"  ✓ New role: '{normalized}' → '{candidate_slug}' (id: {result['id']})"
            )
            return result["id"]
    except sqlite3.IntegrityError:
        # Race / duplicate — try to fetch
        existing = db.select_one(
            "SELECT id FROM speaker_role WHERE role = ?", (normalized,)
        )
        if existing:
            role_map[normalized] = existing["id"]
            return existing["id"]

    return None


# ---------------------------------------------------------------------------
# Core extraction & update logic
# ---------------------------------------------------------------------------


def load_gc_talks(core_db: Database, skip_existing: bool) -> List[Dict]:
    """
    Load general conference talks (Corpus 'G' or 'E') from the core DB.

    If skip_existing is True, only returns talks whose
    talk_metadata.speaker_role_id IS NULL (no row counts as NULL).
    """
    where = "AND tm.speaker_role_id IS NULL" if skip_existing else ""
    return core_db.select(
        f"""
        SELECT t.ID, tm.speaker_role_id
          FROM talk t
          LEFT JOIN talk_metadata tm ON tm.talk_id = t.ID
         WHERE t.Corpus IN ('G', 'E')
           {where}
         ORDER BY t.ID
        """
    )


def extract_and_apply_roles(
    core_db: Database,
    content_db: Database,
    skip_existing: bool,
    dry_run: bool,
):
    """Main extraction and update loop."""
    print("\nStep 3: Loading general conference talks from core DB (Corpus G/E)...")
    talks = load_gc_talks(core_db, skip_existing)
    print(f"  ✓ Found {len(talks)} talks to process")

    if not talks:
        print("  No talks to process.")
        return

    role_map: Dict[str, int] = {}  # normalized_role → speaker_role.id cache
    updated = 0
    no_talkbody = []
    no_role_extracted = []
    errors = []

    print(f"\nStep 4: Extracting and applying speaker roles...")
    print("-" * 80)

    for talk in talks:
        talk_id = talk["ID"]

        # Fetch HTML from content DB
        body_row = content_db.select_one(
            "SELECT TextRaw FROM talkbody WHERE TalkID = ?", (talk_id,)
        )
        if not body_row:
            no_talkbody.append(talk_id)
            continue

        text_raw = body_row.get("TextRaw") or ""

        # Extract role from HTML
        role_text = extract_speaker_role(text_raw)

        if not role_text:
            print(f"  ⚠️  WARNING: Could not extract speaker role for talk ID {talk_id}")
            no_role_extracted.append(talk_id)
            continue

        # Get or create role
        if dry_run:
            normalized = title_case_role(role_text)
            print(f"  [dry-run] TalkID {talk_id}: would set role → '{normalized}'")
            updated += 1
            continue

        role_id = get_or_create_role(core_db, role_map, role_text)
        if role_id is None:
            errors.append(f"TalkID {talk_id}: failed to get/create role '{role_text}'")
            continue

        try:
            upsert_talk_metadata(core_db, talk_id, speaker_role_id=role_id)
            updated += 1

            if updated % 50 == 0:
                print(f"  Progress: {updated} talks updated so far...")
        except Exception as e:
            errors.append(f"TalkID {talk_id}: {e}")

    # Summary
    print("-" * 80)
    print(f"\nExtraction Summary:")
    print(f"  Total GC talks processed: {len(talks)}")
    print(f"  Talks updated: {updated}")
    print(f"  No talkbody row in content DB: {len(no_talkbody)}")
    print(f"  No role extracted (warned above): {len(no_role_extracted)}")
    print(f"  Errors: {len(errors)}")

    if no_talkbody:
        print(f"\n  Talk IDs with no talkbody row:")
        for tid in no_talkbody[:20]:
            print(f"    {tid}")
        if len(no_talkbody) > 20:
            print(f"    ... and {len(no_talkbody) - 20} more")

    if no_role_extracted:
        print(f"\n  Talk IDs with no extractable speaker role:")
        for tid in no_role_extracted[:20]:
            print(f"    {tid}")
        if len(no_role_extracted) > 20:
            print(f"    ... and {len(no_role_extracted) - 20} more")

    if errors:
        print(f"\n  Errors:")
        for err in errors[:10]:
            print(f"    {err}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")

    return {
        "processed": len(talks),
        "updated": updated,
        "no_talkbody": len(no_talkbody),
        "no_role": len(no_role_extracted),
        "errors": len(errors),
    }


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_sample(core_db: Database):
    """Print a sample of updated talks for spot-checking."""
    print("\nStep 5: Verifying updates (sample)...")
    print("-" * 80)

    sample = core_db.select(
        """
        SELECT t.ID, t.Title, sr.role AS speaker_role, sr.slug AS speaker_role_slug
          FROM talk t
          JOIN talk_metadata tm ON tm.talk_id = t.ID
          JOIN speaker_role sr ON tm.speaker_role_id = sr.id
         WHERE t.Corpus IN ('G', 'E')
         ORDER BY t.ID
         LIMIT 10
        """
    )

    if sample:
        print(f"\nSample of {len(sample)} talks with speaker role set:")
        for talk in sample:
            title = talk.get("Title") or ""
            display_title = (title[:55] + "...") if len(title) > 55 else title
            print(f"\n  TalkID: {talk['ID']}")
            print(f"  Title:  {display_title}")
            print(f"  Role:   {talk['speaker_role']}")
            print(f"  Slug:   {talk['speaker_role_slug']}")
    else:
        print("  No updated records found in range.")

    print("-" * 80)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill speaker_role for talks by extracting it from HTML "
            "in the content DB's talkbody.TextRaw"
        )
    )
    parser.add_argument(
        "--core-db",
        default=CORE_DB_PATH,
        help="Path to core.52.db (default: from db module)",
    )
    parser.add_argument(
        "--content-db",
        default=CONTENT_DB_PATH,
        help="Path to content.52.db (default: from db module)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Update speaker_role_id even if it is already set (default: skip existing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be done without writing any changes",
    )
    return parser.parse_args()


def run(
    core_db_path: str, content_db_path: str, overwrite: bool = False, dry_run: bool = False
):
    core_db = Database(core_db_path, read_only=dry_run)
    content_db = Database(content_db_path, read_only=True)

    if not dry_run:
        ensure_speaker_role_table(core_db)

    stats = extract_and_apply_roles(
        core_db=core_db,
        content_db=content_db,
        skip_existing=not overwrite,
        dry_run=dry_run,
    )

    if not dry_run and stats and stats["updated"] > 0:
        verify_sample(core_db)
    return stats


def main():
    args = parse_args()

    print("=" * 80)
    print("Backfill Talk Speaker Roles (HTML Extraction)")
    print("=" * 80)
    print(f"Core DB:       {args.core_db}")
    print(f"Content DB:    {args.content_db}")
    print(f"Corpus filter: G, E")
    print(f"Skip existing: {not args.overwrite}")
    print(f"Dry run:       {args.dry_run}")
    print("=" * 80)

    run(args.core_db, args.content_db, overwrite=args.overwrite, dry_run=args.dry_run)

    print("\n" + "=" * 80)
    print("COMPLETE")
    print("=" * 80)
    if args.dry_run:
        print("Dry run — no changes were written.")


if __name__ == "__main__":
    main()
