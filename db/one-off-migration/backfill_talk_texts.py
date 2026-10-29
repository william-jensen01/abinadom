#!/usr/bin/env python3
"""
Full backfill script for decompressing and projecting talk text.

This generalizes the sample script to process the full talkbody table in
manageable batches with idempotent updates. It will:

- Ensure four columns exist on talkbody (manual IF NOT EXISTS):
  - TextRaw: exact decompressed payload (HTML or plain text)
  - TextSimple: readable plain text with paragraph breaks
  - TextMinimal: aggressively normalized text for search
  - TextEnhanced: markdown-like, structure-preserving text

- Iterate rows using seek-pagination on TalkID, only updating rows where any of
  the four columns are NULL (resume-safe).

Usage:
  python3 backfill_talk_texts.py [--db ./content.52.db] [--batch 1000] [--dry-run] [--sample True|False] [--talk-ids 1 2 3]

Notes:
- This script is idempotent and safe to re-run. It uses COALESCE to avoid
  overwriting non-NULL values.
- Third-party libs used (optional but recommended): beautifulsoup4, lxml,
  readability-lxml, markdownify. If unavailable, the script falls back to
  minimal transformations.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
import unicodedata
import zlib
import gzip
from typing import Iterable, Optional

# --- Resolve local imports ---
# HERE = os.path.dirname(os.path.abspath(__file__))
# if HERE not in sys.path:
#     sys.path.insert(0, HERE)

db_dir = os.path.dirname(os.path.dirname(__file__))
root_dir = os.path.dirname(db_dir)
sys.path.insert(0, root_dir)
from db import Database, CORE_DB_PATH, CONTENT_DB_PATH

# Optional third-party libs with graceful fallback
try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None  # type: ignore

try:
    from readability import Document  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Document = None  # type: ignore

try:
    from markdownify import markdownify as md  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    md = None  # type: ignore


def _is_zlib_header(b0: int, b1: int) -> bool:
    """Check if two bytes form a valid zlib header."""
    # zlib header: CMF/FLG where CM must be 8 (deflate), and (CMF<<8 | FLG) % 31 == 0
    cm = b0 & 0x0F
    return cm == 8 and ((b0 << 8) | b1) % 31 == 0


def _sniff_zlib_offset(data: bytes) -> Optional[int]:
    """Detect zlib header offset in data."""
    # returns 0 if native zlib header is present
    # returns 2 if a custom 2-byte prefix precedes a valid zlib header (observed case)
    # returns None if no zlib header is detected
    if len(data) >= 2 and _is_zlib_header(data[0], data[1]):
        return 0
    if len(data) >= 4 and _is_zlib_header(data[2], data[3]):
        return 2
    return None


def decompress_talk_content(text_data):
    """
    Properly decompress talk content from the database using header-sniffing.

    Args:
        text_data: Raw text data from database (bytes or str)

    Returns:
        str: Decompressed and decoded text content
    """

    if not text_data:
        return ""
    if isinstance(text_data, str):
        return text_data
    if not isinstance(text_data, bytes):
        return str(text_data)

    # Detect gzip
    if len(text_data) >= 2 and text_data[0] == 0x1F and text_data[1] == 0x8B:
        try:
            return gzip.decompress(text_data).decode("utf-8")
        except Exception:
            pass

    # Detect zlib header; use sniffed offset as the first candidate but fall back
    # through all small offsets — prefix bytes can coincidentally pass the header
    # check, so we can't trust the sniff exclusively.
    sniffed = _sniff_zlib_offset(text_data)
    # Build ordered candidate list: sniffed offset first, then 0-4 to cover outliers
    seen: set[int] = set()
    candidates: list[int] = []
    for off in ([sniffed] if sniffed is not None else []) + list(range(5)):
        if off not in seen and off <= len(text_data):
            seen.add(off)
            candidates.append(off)

    for off in candidates:
        try:
            return zlib.decompress(text_data[off:]).decode("utf-8")
        except Exception:
            pass

    for off in candidates:
        try:
            return zlib.decompress(text_data[off:], wbits=-15).decode("utf-8")
        except Exception:
            pass

    # Try plain UTF-8
    try:
        return text_data.decode("utf-8")
    except UnicodeDecodeError:
        return text_data.decode("utf-8", errors="replace")


def is_html(text: str) -> bool:
    if not text:
        return False
    return (
        "<" in text
        and ">" in text
        and re.search(
            r"<\s*(?:html|head|body|div|p|span|h[1-6]|ul|ol|li|a|blockquote|br|section|article|table|tr|td|th)\b",
            text,
            re.I,
        )
        is not None
    )


def extract_main_html(html: str) -> str:
    """Use readability to isolate the main content; fall back gracefully."""
    if not html:
        return ""
    if Document is None:
        return html
    try:
        doc = Document(html)
        main_html = doc.summary(html_partial=True)
        return main_html or html
    except Exception:
        return html


def to_text_simple(html_or_text: str) -> str:
    """Readable plain text with paragraph boundaries preserved."""
    if not html_or_text:
        return ""
    if not is_html(html_or_text):
        return re.sub(r"\s+", " ", html_or_text).strip()

    if BeautifulSoup is None:  # fallback: remove tags naively
        txt = re.sub(r"<br\s*/?>", "\n", html_or_text, flags=re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt

    soup = BeautifulSoup(html_or_text, "html.parser")

    # Remove non-content elements
    for tag in soup(
        ["script", "style", "noscript", "nav", "aside", "header", "footer"]
    ):
        tag.decompose()

    # Convert <br> to newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")

    text = soup.get_text(separator="\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def to_text_minimal(text_simple: str) -> str:
    """Aggressively normalized text: lowercase, strip diacritics, remove punctuation, collapse spaces."""
    if not text_simple:
        return ""
    t = text_simple.lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9'\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def to_text_enhanced(html_or_text: str) -> str:
    """Markdown-like structured text preserving headings/lists/links."""
    if not html_or_text:
        return ""
    if not is_html(html_or_text):
        return to_text_simple(html_or_text)

    main_html = extract_main_html(html_or_text)
    # Pre-remove script/style tags to avoid markdownify strip/convert conflict
    if BeautifulSoup is not None:
        try:
            _soup = BeautifulSoup(main_html, "html.parser")
            for tag in _soup(["script", "style"]):
                tag.decompose()
            main_html = str(_soup)
        except Exception:
            pass

    if md is None:
        # fallback: approximate by simple text with blank lines between paragraphs
        simple = to_text_simple(main_html)
        return re.sub(r"\n{3,}", "\n\n", simple).strip()

    md_text = md(
        main_html,
        heading_style="ATX",
        convert=[
            "p",
            "br",
            "ul",
            "ol",
            "li",
            "em",
            "strong",
            "a",
            "blockquote",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "table",
            "tr",
            "td",
            "th",
        ],
    )
    md_text = re.sub(r"\n{3,}", "\n\n", md_text).strip()
    return md_text


def ensure_columns_exist(conn: sqlite3.Connection, columns: Iterable[str]) -> None:
    """Add columns if they do not exist (manual IF NOT EXISTS)."""
    cur = conn.execute("PRAGMA table_info(talkbody);")
    existing = {row[1] for row in cur.fetchall()}  # name is index 1

    for col in columns:
        if col in existing:
            continue
        if col == "TextRaw":
            conn.execute("ALTER TABLE talkbody ADD COLUMN TextRaw TEXT")
        elif col == "TextSimple":
            conn.execute("ALTER TABLE talkbody ADD COLUMN TextSimple TEXT")
        elif col == "TextMinimal":
            conn.execute("ALTER TABLE talkbody ADD COLUMN TextMinimal TEXT")
        elif col == "TextEnhanced":
            conn.execute("ALTER TABLE talkbody ADD COLUMN TextEnhanced TEXT")
        else:
            raise ValueError(f"Unsupported column request: {col}")


def backfill_all(conn: sqlite3.Connection, batch: int = 1000) -> tuple[int, int]:
    """Recompute TextRaw/Simple/Minimal/Enhanced for every talkbody row."""
    processed = 0
    updated = 0
    # Normal mode
    # Per request: always clear the four columns at the start of each run
    # so repeated test runs recompute from scratch.
    conn.execute("BEGIN")
    try:
        cur = conn.execute(
            """
            UPDATE talkbody
               SET TextRaw = NULL,
                   TextSimple = NULL,
                   TextMinimal = NULL,
                   TextEnhanced = NULL
            """
        )
    finally:
        conn.execute("COMMIT")
    print(
        f"Cleared existing projection columns for {cur.rowcount if hasattr(cur, 'rowcount') else 'N'} rows. Recomputing…"
    )

    last_id = 0
    while True:
        rows = conn.execute(
            """
                SELECT TalkID, Text
                FROM talkbody
                WHERE TalkID > ?
                AND (TextRaw IS NULL OR TextSimple IS NULL OR TextMinimal IS NULL OR TextEnhanced IS NULL)
            ORDER BY TalkID
                LIMIT ?
                """,
            (last_id, batch),
        ).fetchall()
        if not rows:
            break

        conn.execute("BEGIN")
        try:
            for talk_id, blob in rows:
                processed += 1
                try:
                    raw = decompress_talk_content(blob) or ""
                except Exception:
                    raw = ""

                mainish = extract_main_html(raw) if is_html(raw) else raw
                simple = to_text_simple(mainish)
                minimal = to_text_minimal(simple)
                enhanced = to_text_enhanced(raw)

                cur = conn.execute(
                    """
                    UPDATE talkbody
                       SET TextRaw      = COALESCE(TextRaw, ?),
                           TextSimple   = COALESCE(TextSimple, ?),
                           TextMinimal  = COALESCE(TextMinimal, ?),
                           TextEnhanced = COALESCE(TextEnhanced, ?)
                     WHERE TalkID = ?
                    """,
                    (raw, simple, minimal, enhanced, talk_id),
                )
                if cur.rowcount:
                    updated += 1
                last_id = talk_id
                # Progress indicator every 50 records
                if processed % 50 == 0:
                    print(f"Progress: processed={processed}, updated={updated}")
        finally:
            conn.execute("COMMIT")


    return processed, updated


def run(content_db_path: str, batch: int = 1000) -> tuple[int, int]:
    """Add the text columns if needed and fill them for every talk."""
    start = time.time()
    with sqlite3.connect(content_db_path) as conn:
        ensure_columns_exist(conn, ["TextRaw", "TextSimple", "TextMinimal", "TextEnhanced"])
        processed, updated = backfill_all(conn, batch)
    print(f"Backfill complete. Processed: {processed}, Updated: {updated}, Elapsed: {time.time() - start:.2f}s")
    return processed, updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill talk text projections.")
    parser.add_argument(
        "--content-db",
        "--db",
        dest="content_db",
        default=CONTENT_DB_PATH,
        help="Path to content DB (default: CONTENT_DB_PATH)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1000,
        help="Batch size",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write changes; only report counts",
    )
    parser.add_argument(
        "--sample", action="store_true", help="Use a sample of TalkIDs for review"
    )
    parser.add_argument(
        "--talk-ids", nargs="*", type=int, default=[299, 3127, 6975, 7930, 120013]
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = args.content_db
    batch = max(1, args.batch)

    start = time.time()
    processed = 0
    updated = 0

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")

        # Add columns IF NOT EXISTS (via introspection)
        ensure_columns_exist(
            conn, ["TextRaw", "TextSimple", "TextMinimal", "TextEnhanced"]
        )

        # If dry-run, just show how many rows are missing any of the fields
        if args.dry_run:
            (missing_total,) = conn.execute(
                """
                SELECT COUNT(*)
                  FROM talkbody
                 WHERE TextRaw IS NULL
                    OR TextSimple IS NULL
                    OR TextMinimal IS NULL
                    OR TextEnhanced IS NULL
                """
            ).fetchone()
            print(f"[DRY-RUN] Rows with any NULL projection: {missing_total}")
            return

        # Sample mode: process specific TalkIds for review
        if args.sample:
            placeholders = ",".join(["?"] * len(args.talk_ids))

            # Clear the four columns for the target TalkIds on each run
            conn.execute("BEGIN")
            try:
                conn.execute(
                    f"""
                    UPDATE talkbody
                       SET TextRaw = NULL,
                           TextSimple = NULL,
                           TextMinimal = NULL,
                           TextEnhanced = NULL
                     WHERE TalkID IN ({placeholders})
                    """,
                    args.talk_ids,
                )
            finally:
                conn.execute("COMMIT")

            # Fetch only the specific TalkIDs
            rows = conn.execute(
                f"SELECT TalkID, Text FROM talkbody WHERE TalkID in ({placeholders}) ORDER BY TalkID",
                args.talk_ids,
            ).fetchall()

            conn.execute("BEGIN")
            try:
                for idx, (talk_id, blob) in enumerate(rows, start=1):
                    try:
                        raw = decompress_talk_content(blob) or ""
                    except Exception:
                        raw = ""

                    mainish = extract_main_html(raw) if is_html(raw) else raw
                    simple = to_text_simple(mainish)
                    minimal = to_text_minimal(simple)
                    enhanced = to_text_enhanced(raw)

                    # Only set values that are currently NULL to keep idempotent behavior
                    conn.execute(
                        """
                        UPDATE talkbody
                           SET TextRaw      = COALESCE(TextRaw, ?),
                               TextSimple   = COALESCE(TextSimple, ?),
                               TextMinimal  = COALESCE(TextMinimal, ?),
                               TextEnhanced = COALESCE(TextEnhanced, ?)
                         WHERE TalkID = ?
                        """,
                        (raw, simple, minimal, enhanced, talk_id),
                    )
                    processed += 1
                    if idx % 50 == 0:
                        print(f"Progress (sample): processed={processed}")
            finally:
                conn.execute("COMMIT")

            # Simple report to stdout for manual review (when executed)
            review = conn.execute(
                f"""
                SELECT TalkID,
                       length(Text) AS compressed_bytes,
                       length(TextRaw) AS raw_chars,
                       substr(TextSimple,1,120) AS simple_head,
                       substr(TextMinimal,1,120) AS minimal_head,
                       substr(TextEnhanced,1,120) AS enhanced_head
                  FROM talkbody
                 WHERE TalkID IN ({placeholders})
                 ORDER BY TalkID
                """,
                args.talk_ids,
            ).fetchall()

            # Print outside to transaction context
            elapsed = time.time() - start
            print(
                f"\nBackfill (sample) prepared for TalkIDs: {', '.join(map(str, args.talk_ids))}"
            )
            for row in review:
                print(row)
            print(f"\nSample complete. Processed: {processed}, Elapsed: {elapsed:.2f}s")
            return

        processed, updated = backfill_all(conn, batch)

    elapsed = time.time() - start
    print(
        f"Backfill complete. Processed: {processed}, Updated: {updated}, Elapsed: {elapsed:.2f}s"
    )


if __name__ == "__main__":
    main()
