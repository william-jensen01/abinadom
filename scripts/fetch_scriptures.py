#!/usr/bin/env python3
"""Fetch the scripture pages into the raw layer of scripture.db (SPEC-v2 §4.1, §8).

Walks the five volume tables of contents and the JST appendix TOC, then stores
every linked page (including `_contents` pages) from the `type/content` endpoint.
A row is added only when the sha256 of the response changes.

  --only-missing   skip pages that already have a stored 200 response
  --refresh        re-fetch everything, recording only changes (the default does the same)

Exit status is non-zero, naming the URIs, if any page could not be stored.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils import church_api  # noqa: E402

DEFAULT_DB = os.path.join(ROOT, "db", "scripture.db")
SCHEMA = os.path.join(ROOT, "db", "scripture_schema.sql")
LANG = "eng"
TOC_URIS = [f"/scriptures/{v}" for v in ("ot", "nt", "bofm", "dc-testament", "pgp", "jst")]
VOLUME_SEGMENTS = {u.split("/")[2] for u in TOC_URIS}
MAX_CONSECUTIVE_FAILURES = 10
SHOW_NOT_ATTEMPTED = 10
HREF_RE = re.compile(r'href="/study(/scriptures/[^"?#]+)')


def content_hash(data) -> str:
    norm = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def toc_links(data: dict) -> list:
    """Page URIs linked from a TOC body, in order, without duplicates; links outside the six volumes (tg/bd/gs study helps) are skipped."""
    body = (data.get("content") or {}).get("body") or ""
    seen, out = set(), []
    for uri in HREF_RE.findall(body.replace('\\"', '"')):
        uri = uri.rstrip("/")
        if uri.split("/")[2] not in VOLUME_SEGMENTS or uri in seen:
            continue
        seen.add(uri)
        out.append(uri)
    return out


def open_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    with open(SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


class Fetcher:
    def __init__(self, conn, session):
        self.conn, self.session = conn, session
        self.failed = {}      # uri -> reason
        self.consecutive = 0
        self.added = self.unchanged = 0

    def stored(self, uri) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM raw_latest WHERE uri=? AND lang=? AND status=200", (uri, LANG)).fetchone() is not None

    def fetch(self, uri):
        """Fetch and store one page. Returns the parsed JSON, or None on failure."""
        try:
            resp = church_api.get_content_response(self.session, uri)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            data = resp.json()
        except Exception as e:  # noqa: BLE001 - record and carry on
            self.failed[uri] = f"{type(e).__name__}: {e}"
            self.consecutive += 1
            return None
        self.consecutive = 0
        h = content_hash(data)
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO raw_page (uri, lang, fetched_at, content_hash, status, json) VALUES (?,?,?,?,?,?)",
            (uri, LANG, datetime.now(timezone.utc).isoformat(timespec="seconds"), h, resp.status_code, resp.text))
        self.conn.commit()
        if cur.rowcount:
            self.added += 1
        else:
            self.unchanged += 1
        return data

    def aborted(self) -> bool:
        return self.consecutive >= MAX_CONSECUTIVE_FAILURES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--only-missing", action="store_true", help="skip pages already stored")
    ap.add_argument("--refresh", action="store_true", help="re-fetch all pages, record only changes")
    args = ap.parse_args(argv)
    if args.only_missing and args.refresh:
        ap.error("--only-missing and --refresh are mutually exclusive")

    conn = open_db(args.db)
    f = Fetcher(conn, church_api.fresh_session())

    pages, seen = [], set()
    for toc in TOC_URIS:
        data = f.fetch(toc)
        if data is None:
            # fall back to the stored TOC so a resume can still walk it
            row = conn.execute("SELECT json FROM raw_latest WHERE uri=? AND lang=? AND status=200",
                               (toc, LANG)).fetchone()
            data = json.loads(row[0]) if row else None
            if data is not None and not args.refresh:
                # resuming: the stored TOC is good enough. Under --refresh the TOC
                # was not refreshed, so it stays in f.failed.
                f.failed.pop(toc, None)
        if data is None:
            continue
        for uri in toc_links(data):
            if uri not in seen:
                seen.add(uri)
                pages.append(uri)
        if f.aborted():
            break
    print(f"{len(pages)} pages linked from {len(TOC_URIS)} TOCs", flush=True)

    not_attempted = []
    for i, uri in enumerate(pages, 1):
        if f.aborted():
            not_attempted = [u for u in pages[i - 1:] if not (args.only_missing and f.stored(u))]
            break
        if args.only_missing and f.stored(uri):
            continue
        f.fetch(uri)
        if i % 100 == 0:
            print(f"  {i}/{len(pages)} (added {f.added}, unchanged {f.unchanged}, failed {len(f.failed)})", flush=True)

    conn.close()
    print(f"done: added {f.added}, unchanged {f.unchanged}, failed {len(f.failed)}")
    if f.failed or not_attempted:
        print(f"ERROR: {len(f.failed)} URIs could not be stored:", file=sys.stderr)
        for uri, why in sorted(f.failed.items()):
            print(f"  {uri}  ({why})", file=sys.stderr)
        if not_attempted:
            shown = not_attempted[:SHOW_NOT_ATTEMPTED]
            print(f"ERROR: aborted after {MAX_CONSECUTIVE_FAILURES} consecutive failures; "
                  f"{len(not_attempted)} URIs not attempted (resume with --only-missing), first {len(shown)}:",
                  file=sys.stderr)
            for uri in shown:
                print(f"  {uri}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
