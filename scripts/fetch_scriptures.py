#!/usr/bin/env python3
"""Fetch the scripture pages into the raw layer of scripture.db.

Walks the five volume tables of contents and the JST appendix TOC, and stores every page they link to
(`_contents` pages included) from the `type/content` endpoint, sequentially through utils.church_api (throttle,
User-Agent, uncached session). A row is added only when the page's sha256 changed, so pages fetched before an
interruption are kept and a re-fetch that finds no change writes nothing. A page that reverts to content stored
earlier has that row re-stamped so it is the latest again (counted as "reverted").

  --only-missing   skip pages that are already stored (walks the stored TOCs)
  --refresh        re-fetch every page, recording only changes (also what a run without a flag does)

Exits non-zero, naming the URIs, when a page could not be stored. After 10 failures in a row it stops.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from extractors.scripture_page import TOC_VOLUMES, toc_links  # noqa: E402
from utils import church_api  # noqa: E402

DEFAULT_DB = os.path.join(ROOT, "db", "scripture.db")
SCHEMA = os.path.join(ROOT, "db", "scripture_schema.sql")
LANG = "eng"
MAX_FAILURES_IN_A_ROW = 10


def content_hash(data) -> str:
    """sha256 of the response JSON, normalized (sorted keys), so key order never counts as a change."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def stored(conn, uri):
    """The stored JSON of a page, or None."""
    row = conn.execute("SELECT json FROM raw_latest WHERE uri = ? AND lang = ? AND status = 200", (uri, LANG)).fetchone()
    return json.loads(row[0]) if row else None


def fetch(conn, session, uri) -> str:
    """Fetch one page and store it if it changed. Returns 'added', 'reverted' or 'unchanged'; raises on failure."""
    resp = church_api.get_content(session, uri)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    digest = content_hash(resp.json())
    latest = conn.execute("SELECT content_hash FROM raw_latest WHERE uri = ? AND lang = ?", (uri, LANG)).fetchone()
    if latest and latest[0] == digest:
        return "unchanged"
    known = conn.execute("SELECT 1 FROM raw_page WHERE uri = ? AND lang = ? AND content_hash = ?",
                         (uri, LANG, digest)).fetchone()
    # REPLACE re-inserts an earlier row with a new rowid and fetched_at, so it wins raw_latest even within a second
    conn.execute(
        "INSERT OR REPLACE INTO raw_page (uri, lang, fetched_at, content_hash, status, json) VALUES (?,?,?,?,?,?)",
        (uri, LANG, datetime.now(timezone.utc).isoformat(timespec="seconds"), digest, resp.status_code, resp.text))
    conn.commit()
    return "reverted" if known else "added"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--only-missing", action="store_true", help="skip pages already stored")
    mode.add_argument("--refresh", action="store_true", help="re-fetch every page, record only changes")
    args = ap.parse_args(argv)

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    conn = sqlite3.connect(args.db)
    with open(SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read().split("-- ==== normalized layer ====")[0])  # the raw layer only
    session = church_api.fresh_session()

    queue = [f"/scriptures/{v}" for v in TOC_VOLUMES]   # TOCs first; the pages they link to are appended
    tocs, done, failed, in_a_row = set(queue), {"added": 0, "reverted": 0, "unchanged": 0, "skipped": 0}, {}, 0
    i = 0
    while i < len(queue) and in_a_row < MAX_FAILURES_IN_A_ROW:
        uri = queue[i]
        i += 1
        if args.only_missing and stored(conn, uri) is not None:
            done["skipped"] += 1
        else:
            try:
                done[fetch(conn, session, uri)] += 1
                in_a_row = 0
            except Exception as e:  # noqa: BLE001 - record it and go on
                failed[uri] = f"{type(e).__name__}: {e}"
                in_a_row += 1
        if uri in tocs and (data := stored(conn, uri)) is not None:   # a TOC that failed now: walk the stored one
            queue += [u for u in toc_links(data) if u not in queue]
        if i % 100 == 0:
            print(f"  {i}/{len(queue)} {done}, failed {len(failed)}", flush=True)
    conn.close()

    print(f"done: {done}, failed {len(failed)}")
    not_attempted = queue[i:]
    if failed or not_attempted:
        print(f"ERROR: {len(failed)} URIs could not be stored:", file=sys.stderr)
        for uri, why in failed.items():
            print(f"  {uri}  ({why})", file=sys.stderr)
        if not_attempted:
            print(f"ERROR: stopped after {MAX_FAILURES_IN_A_ROW} failures in a row; {len(not_attempted)} URIs not "
                  f"attempted (resume with --only-missing), e.g. {', '.join(not_attempted[:10])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
