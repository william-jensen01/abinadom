#!/usr/bin/env python3
"""Build the normalized layer of scripture.db from the raw layer (SPEC-v2 §4.2, §8, §10).

Drops and recreates every normalized table in ONE transaction, from `raw_latest`. The raw layer is
never touched. Validation (§10) runs before the commit: any failure rolls the whole build back and
leaves the previous normalized tables as they were. Exit status is non-zero on failure.

  --db PATH   the scripture.db to build in place (default db/scripture.db)

Steps: read the six volume TOCs, fail (naming them) if a linked page has no stored 200 response,
parse every page with extractors/scripture_page.py, insert, validate, write build_meta.
`book.num_chapters` is taken from each book's `_contents` page (Abraham's facsimile links count toward
the Facsimiles book), or for a book without one from its chapter links in the volume TOC, and §10 checks
it against the chapter rows the volume TOC walk produced.
`build_meta.build_id` is a sha256 over the content of the normalized tables, so rebuilding identical
raw data gives the same id.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db import SCI_DB_VERSION  # noqa: E402
from config.scripture_books import BOOK_CROSSWALK, VOLUME_ABBR  # noqa: E402
from extractors import scripture_jst as jst  # noqa: E402
from extractors import scripture_page as sp  # noqa: E402

DEFAULT_DB = os.path.join(ROOT, "db", "scripture.db")
SCHEMA = os.path.join(ROOT, "db", "scripture_schema.sql")
MARKER = "-- ==== normalized layer ===="
LANG = "eng"
SCHEMA_VERSION = "1"
NORMALIZED_TABLES = ["jst_passage_ref", "jst_passage_verse", "jst_passage", "footnote_ref", "footnote", "jst_verse", "verse", "chapter", "page", "book", "volume", "build_meta"]
# tables hashed into build_id (build_meta itself is not)
HASHED_TABLES = ["volume", "book", "page", "chapter", "verse", "jst_verse", "footnote", "footnote_ref",
                 "jst_passage", "jst_passage_verse", "jst_passage_ref"]
SAMPLE = 8


class BuildError(Exception):
    pass


def normalized_ddl() -> str:
    with open(SCHEMA, encoding="utf-8") as f:
        return f.read().split(MARKER, 1)[1]


def ddl_statements(ddl: str) -> list:
    """Split DDL text into complete statements (so the build can stay inside one transaction)."""
    out, buf = [], ""
    for line in ddl.splitlines(keepends=True):
        if not buf and (not line.strip() or line.lstrip().startswith("--")):
            continue
        buf += line
        if sqlite3.complete_statement(buf):
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        raise BuildError("unterminated statement in the normalized DDL: " + buf.strip()[:60])
    return out


def load_raw(conn: sqlite3.Connection) -> dict:
    """uri -> (content_hash, json text) for every stored 200 response in raw_latest."""
    rows = conn.execute("SELECT uri, content_hash, json FROM raw_latest WHERE lang = ? AND status = 200", (LANG,))
    return {uri: (h, js) for uri, h, js in rows}


def read_tocs(raw: dict) -> list:
    """[(volume segment, uri, parsed Toc)] for the six volume TOCs, in volume order."""
    missing = [f"/scriptures/{v}" for v in sp.TOC_VOLUMES if f"/scriptures/{v}" not in raw]
    if missing:
        raise BuildError("volume TOC pages with no raw_latest row (fetch them first): " + ", ".join(missing))
    return [(v, f"/scriptures/{v}", sp.parse_toc(json.loads(raw[f"/scriptures/{v}"][1]), v)) for v in sp.TOC_VOLUMES]


def check_toc_links(tocs: list, raw: dict) -> None:
    missing = []
    for _, _, toc in tocs:
        missing += [i.uri for i in toc.items if i.uri not in raw]
    if missing:
        shown = ", ".join(missing[:50]) + (f" … and {len(missing) - 50} more" if len(missing) > 50 else "")
        raise BuildError(f"{len(missing)} page(s) linked from a TOC have no raw_latest row (status 200): {shown}")


def build_id_of(conn: sqlite3.Connection) -> str:
    h = hashlib.sha256()
    for table in HASHED_TABLES:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        h.update(f"#{table}:{','.join(cols)}\n".encode())
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY {', '.join(str(i + 1) for i in range(len(cols)))}"):
            h.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            h.update(b"\n")
    return h.hexdigest()


class Builder:
    def __init__(self, conn: sqlite3.Connection, raw: dict, tocs: list):
        self.conn = conn
        self.raw = raw
        self.tocs = tocs
        self.volume_ids = {}
        self.book_ids = {}
        self.page_ids = {}
        self.parsed = {}          # uri -> ParsedPage
        self.chapter_ids = {}     # uri -> chapter_id
        self.verse_ids = {}       # uri -> {aid: verse_id}
        self.report = []
        self.contents_unlinked = []   # (_contents uri, link) for _contents links no volume TOC lists
        self.contents_no_book = []    # (_contents uri, link, book uri) counted toward a book with no row

    # -- structure ---------------------------------------------------------
    def build_structure(self) -> None:
        c = self.conn
        book_sort = 0
        page_sort = 0
        pages = []   # (uri, book_uri)
        seen = set()
        for vsort, (vseg, vuri, toc) in enumerate(self.tocs):
            if vseg != sp.JST_VOLUME:
                cur = c.execute("INSERT INTO volume (uri, title, abbr, sort) VALUES (?,?,?,?)",
                                (vuri, toc.title or vseg, VOLUME_ABBR.get(vseg), vsort))
                self.volume_ids[vseg] = cur.lastrowid
            for b in toc.books:
                vol_id = self.volume_ids[b.volume]
                segs = sp.uri_segments(b.uri)
                key = (segs[0], "/".join(segs[1:]))
                abbr, cite, core_id = BOOK_CROSSWALK.get(key, (None, b.name, None))
                cur = c.execute(
                    "INSERT INTO book (volume_id, uri, name, abbr, cite_abbr, sort, num_chapters, core_book_id) "
                    "VALUES (?,?,?,?,?,?,NULL,?)", (vol_id, b.uri, b.name, abbr, cite, book_sort, core_id))
                self.book_ids[b.uri] = cur.lastrowid
                book_sort += 1
            if vuri not in seen:
                seen.add(vuri)
                pages.append((vuri, None))
            for item in toc.items:
                if item.uri not in seen:
                    seen.add(item.uri)
                    pages.append((item.uri, item.book_uri if item.book_uri in self.book_ids else None))

        for uri, book_uri in pages:
            data = json.loads(self.raw[uri][1])
            parsed = sp.parse_page(uri, data)
            self.parsed[uri] = parsed
            book_id = self.book_ids.get(book_uri) if book_uri else None
            cur = c.execute("INSERT INTO page (uri, book_id, kind, title, sort) VALUES (?,?,?,?,?)",
                            (uri, book_id, parsed.kind, parsed.title, page_sort))
            page_sort += 1
            self.page_ids[uri] = cur.lastrowid
        for book_uri, n in self.toc_chapter_counts().items():
            c.execute("UPDATE book SET num_chapters = ? WHERE uri = ?", (n, book_uri))

    def toc_chapter_counts(self) -> dict:
        """book uri -> num_chapters, read from the TOC pages (never from the chapter rows).

        A book with a `_contents` page gets the number of pages that page lists, each counted toward
        `sp.contents_link_book` (Abraham's `fac-N` links count toward `/scriptures/pgp/abr/fac`). Only links
        that a volume TOC also lists are counted: the volume TOCs define the corpus (the fetch walks them, and
        a missing page among their links fails the build), and the others are reported. A book with no
        `_contents` page (the one-chapter books) gets its chapter links in the volume TOC.
        """
        toc_links = {item.uri for _, _, toc in self.tocs for item in toc.items}
        from_contents = Counter()
        covered = set()
        for vseg, _, toc in self.tocs:
            if vseg == sp.JST_VOLUME:
                continue
            for item in toc.items:
                if sp.classify_page(item.uri) != sp.KIND_BOOK_TOC:
                    continue
                own_book = item.uri.rsplit("/", 1)[0]
                covered.add(own_book)
                for link in sp.parse_book_contents(json.loads(self.raw[item.uri][1])):
                    if link not in toc_links:
                        self.contents_unlinked.append((item.uri, link))
                        continue
                    book_uri = sp.contents_link_book(link, own_book)
                    if book_uri not in self.book_ids:
                        self.contents_no_book.append((item.uri, link, book_uri))
                        continue
                    covered.add(book_uri)
                    from_contents[book_uri] += 1
        counts = {}
        for book_uri in self.book_ids:
            if book_uri in covered:
                counts[book_uri] = from_contents[book_uri]
            else:
                counts[book_uri] = sum(1 for _, _, toc in self.tocs for item in toc.items
                                       if item.book_uri == book_uri and sp.classify_page(item.uri) in sp.CHAPTER_KINDS)
        return counts

    # -- content -----------------------------------------------------------
    def build_content(self) -> None:
        c = self.conn
        page_book = {uri: bid for uri, bid in c.execute("SELECT uri, book_id FROM page")}
        for uri, parsed in self.parsed.items():
            page_id = self.page_ids[uri]
            book_id = page_book[uri]
            aid_to_verse = {}
            if parsed.kind in sp.CHAPTER_KINDS:
                cur = c.execute(
                    "INSERT INTO chapter (page_id, book_id, number, title, summary, intro, summary_html, intro_html) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (page_id, book_id, parsed.number, parsed.title, parsed.summary, parsed.intro,
                     parsed.summary_html, parsed.intro_html))
                chapter_id = cur.lastrowid
                self.chapter_ids[uri] = chapter_id
                for v in parsed.verses:
                    vc = c.execute(
                        "INSERT INTO verse (chapter_id, book_id, chapter, verse, aid, pid_html_id, text, text_html) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (chapter_id, book_id, parsed.number, v.verse, v.aid, v.html_id, v.text, v.text_html))
                    aid_to_verse[v.aid] = vc.lastrowid
            self.verse_ids[uri] = aid_to_verse
            for fn in parsed.footnotes:
                fc = c.execute(
                    "INSERT INTO footnote (verse_id, note_key, marker, letter, context, text, text_html, page_id, "
                    "anchor_aid) VALUES (?,?,?,?,?,?,?,?,?)",
                    (aid_to_verse.get(fn.pid), fn.note_key, fn.marker, fn.letter, fn.context, fn.text,
                     fn.text_html, page_id, fn.pid))
                fid = fc.lastrowid
                for r in fn.refs:
                    t = r.target
                    c.execute(
                        "INSERT INTO footnote_ref (footnote_id, seq, category, ref_type, href, label, target_uri, "
                        "target_book_id, target_chapter, target_verse_start, target_verse_end, target_help, "
                        "target_jst_verse_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                        (fid, r.seq, r.category, r.ref_type, r.href, r.label, t.target_uri,
                         self.book_ids.get(t.book_uri) if t.book_uri else None,
                         t.chapter, r.verse_start, r.verse_end, t.help))

    # -- JST (§5) ------------------------------------------------------------
    def build_jst(self, core_rows: list) -> None:
        """Import core.db's J/F rows, resolve the `jst` footnote refs, store the appendix passages."""
        c = self.conn
        self.core_jst_rows = len(core_rows)
        jst.import_jst_verses(c, core_rows)
        index = jst.JstIndex(c, core_rows)
        self.jst_refs = jst.resolve_footnote_refs(c, index)
        pages = [(uri, self.page_ids[uri], json.loads(self.raw[uri][1]))
                 for uri, parsed in self.parsed.items() if parsed.kind == sp.KIND_JST_APPENDIX]
        self.jst_passages = jst.store_passages(c, index, pages)

    # -- validation (§10) ----------------------------------------------------
    def validate(self) -> list:
        c = self.conn
        errors = []

        def fail(msg, items):
            if items:
                errors.append(f"{msg}: {len(items)} — " + "; ".join(map(str, items[:SAMPLE])))

        # verse count per chapter = <p class=verse> in the body; verses run 1..N
        body_counts = {}
        for uri, parsed in self.parsed.items():
            if parsed.kind in sp.CHAPTER_KINDS:
                body = json.loads(self.raw[uri][1]).get("content", {}).get("body") or ""
                body_counts[uri] = len(re.findall(r'<p\b[^>]*\bclass="(?:[^"]*\s)?verse(?:\s[^"]*)?"', body))
        stored = {uri: n for uri, n in c.execute(
            "SELECT p.uri, COUNT(v.verse_id) FROM page p JOIN chapter ch ON ch.page_id = p.page_id "
            "LEFT JOIN verse v ON v.chapter_id = ch.chapter_id GROUP BY p.uri")}
        fail("chapters whose verse rows != <p class=verse> in the body",
             [(u, stored.get(u), n) for u, n in body_counts.items() if stored.get(u) != n])
        gaps = []
        for uri, chapter_id in self.chapter_ids.items():
            nums = [r[0] for r in c.execute("SELECT verse FROM verse WHERE chapter_id = ? ORDER BY verse", (chapter_id,))]
            if nums and nums != list(range(1, len(nums) + 1)):
                gaps.append(uri)
        fail("chapters whose verses do not run 1..N", gaps)

        # footnotes: stored count = content.footnotes; verse_id resolves when pid is a verse aid;
        # every study-note-ref has an entry and the reverse
        bad_count, bad_pid, bad_refs = [], [], []
        for uri, parsed in self.parsed.items():
            n = c.execute("SELECT COUNT(*) FROM footnote WHERE page_id = ?", (self.page_ids[uri],)).fetchone()[0]
            if n != len(parsed.footnotes):
                bad_count.append((uri, n, len(parsed.footnotes)))
            aids = self.verse_ids.get(uri, {})
            for fn in parsed.footnotes:
                if fn.pid in aids:
                    continue
                if parsed.kind in (sp.KIND_CHAPTER, sp.KIND_SECTION) and fn.note_key.startswith("note") \
                        and re.match(r"^note\d+_[a-z]+$", fn.note_key):
                    bad_pid.append((uri, fn.note_key, fn.pid))
            # every body marker needs an entry; every entry anchored on a verse needs a marker (a verse-less
            # note may be a table note with no marker, e.g. chron-order figure1_note_asterisk)
            keys = {fn.note_key for fn in parsed.footnotes}
            verse_keys = {fn.note_key for fn in parsed.footnotes if fn.pid in aids}
            body_keys = set(parsed.body_note_keys)
            if body_keys - keys or verse_keys - body_keys:
                bad_refs.append((uri, sorted(body_keys - keys)[:3], sorted(verse_keys - body_keys)[:3]))
        fail("pages whose footnote rows != content.footnotes", bad_count)
        fail("verse footnotes whose pid matches no verse aid", bad_pid)
        fail("pages where study-note-ref markers and footnote entries differ (uri, marker-only, entry-only)", bad_refs)
        orphans = c.execute("SELECT COUNT(*) FROM footnote WHERE verse_id IS NOT NULL AND verse_id NOT IN "
                            "(SELECT verse_id FROM verse)").fetchone()[0]
        if orphans:
            errors.append(f"{orphans} footnotes whose verse_id does not resolve")

        # text is clean
        dirty = c.execute("SELECT verse_id, substr(text, 1, 50) FROM verse WHERE text LIKE '%<%' OR text LIKE '%>%' "
                          "OR text GLOB '[0-9]*' OR trim(text) = '' LIMIT ?", (SAMPLE,)).fetchall()
        fail("verse.text with HTML, a leading verse number or no text", dirty)

        # chapter rows per book = num_chapters (TOC-derived: the book's _contents page, see toc_chapter_counts)
        fail("books whose chapter rows != num_chapters from the TOC (uri, num_chapters, chapter rows)", c.execute(
            "SELECT b.uri, b.num_chapters, (SELECT COUNT(*) FROM chapter ch WHERE ch.book_id = b.book_id) n "
            "FROM book b WHERE b.num_chapters IS NULL OR b.num_chapters != n ORDER BY b.sort").fetchall())
        fail("_contents links that count toward a book with no book row (contents page, link, book)",
             self.contents_no_book)
        if self.contents_unlinked:
            self.report.append(
                f"_contents links that no volume TOC lists (not fetched, not counted in num_chapters): "
                f"{len(self.contents_unlinked)} (e.g. {', '.join(l for _, l in self.contents_unlinked[:SAMPLE])})")

        # chapters with verses need a number
        fail("verse-bearing pages without a chapter number", c.execute(
            "SELECT p.uri FROM chapter ch JOIN page p ON p.page_id = ch.page_id "
            "WHERE ch.number IS NULL AND EXISTS (SELECT 1 FROM verse v WHERE v.chapter_id = ch.chapter_id) LIMIT ?",
            (SAMPLE,)).fetchall())

        # JST: jst_verse = the core.db J/F rows; unresolved `jst` refs are reported (the item check bounds them)
        n_jst = c.execute("SELECT COUNT(*) FROM jst_verse").fetchone()[0]
        if n_jst != self.core_jst_rows:
            errors.append(f"jst_verse rows {n_jst} != core.db J+F rows {self.core_jst_rows}")
        fail("appendix passages whose heading does not parse to a JST verse range", self.jst_passages["bad_title"])
        unres = c.execute("SELECT COUNT(*) FROM footnote_ref WHERE category = 'jst' AND target_jst_verse_id IS NULL"
                          ).fetchone()[0]
        total = c.execute("SELECT COUNT(*) FROM footnote_ref WHERE category = 'jst'").fetchone()[0]
        self.report.append(f"jst_verse: {n_jst}; jst refs: {total}, unresolved: {unres}"
                           + (f" (e.g. {'; '.join(sorted(set(self.jst_refs['unresolved']))[:SAMPLE])})" if unres else ""))
        ps = self.jst_passages
        self.report.append(
            f"jst appendix passages: {ps['passages']}, Compare links: {ps['compare']} (other links: "
            f"{ps['refs'] - ps['compare']}), jst_verse rows named: {ps['verses']}; no Compare link: "
            f"{len(ps['no_compare'])}; heading verses not in jst_verse: {len(ps['missing_verses'])}; "
            f"heading != verse paragraphs: {len(ps['paragraph_mismatch'])}")

        # unresolved scripture refs: reported, not fatal
        rows = c.execute(
            "SELECT target_uri, COUNT(*) FROM footnote_ref WHERE target_help IS NULL AND target_book_id IS NULL "
            "AND target_uri IS NOT NULL AND target_uri NOT LIKE '/scriptures/jst/%' GROUP BY target_uri "
            "ORDER BY 2 DESC, 1").fetchall()
        total_refs = c.execute("SELECT COUNT(*) FROM footnote_ref WHERE target_uri IS NOT NULL "
                               "AND target_help IS NULL AND target_uri NOT LIKE '/scriptures/jst/%'").fetchone()[0]
        n_unres = sum(n for _, n in rows)
        self.report.append(f"scripture refs: {total_refs}; resolved to no book: {n_unres}"
                           + (f" (e.g. {', '.join(f'{u} x{n}' for u, n in rows[:SAMPLE])})" if rows else ""))
        return errors


def counts(conn: sqlite3.Connection) -> dict:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ["volume", "book", "page", "chapter", "verse", "footnote", "footnote_ref"]}


def build(db_path: str) -> int:
    if not os.path.exists(db_path):
        print(f"ERROR: {db_path} does not exist; run scripts/fetch_scriptures.py first", file=sys.stderr)
        return 1
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'raw_latest'").fetchone():
            print(f"ERROR: {db_path} has no raw layer; run scripts/fetch_scriptures.py first", file=sys.stderr)
            return 1
        raw = load_raw(conn)
        tocs = read_tocs(raw)
        check_toc_links(tocs, raw)
        try:
            core_rows = jst.read_core_jst()
        except FileNotFoundError as e:
            raise BuildError(str(e))

        conn.execute("BEGIN")
        try:
            for t in NORMALIZED_TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {t}")
            for idx in ("footnote_verse_idx", "footnote_ref_book_idx", "verse_chapter_idx", "jst_verse_ref_idx",
                        "jst_verse_core_idx", "jst_passage_ref_book_idx"):
                conn.execute(f"DROP INDEX IF EXISTS {idx}")
            for stmt in ddl_statements(normalized_ddl()):
                conn.execute(stmt)
            b = Builder(conn, raw, tocs)
            b.build_structure()
            b.build_content()
            b.build_jst(core_rows)
            errors = b.validate()
            if errors:
                raise BuildError("validation failed:\n  - " + "\n  - ".join(errors))
            build_id = build_id_of(conn)
            raw_hash = hashlib.sha256(
                "\n".join(f"{u}\t{h}" for u, (h, _) in sorted(raw.items())).encode()).hexdigest()
            meta = {
                "build_id": build_id,
                "schema_version": SCHEMA_VERSION,
                "raw_hash": raw_hash,
                "raw_pages": str(len(raw)),
                "core_db_version": SCI_DB_VERSION,
                "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            conn.executemany("INSERT INTO build_meta (key, value) VALUES (?, ?)", sorted(meta.items()))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    except BuildError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    c2 = sqlite3.connect(db_path)
    try:
        n = counts(c2)
    finally:
        c2.close()
    print("build ok: " + ", ".join(f"{k}={v}" for k, v in n.items()))
    for line in b.report:
        print(line)
    print(f"build_id: {build_id}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB, help="scripture.db to build in place (default db/scripture.db)")
    args = ap.parse_args(argv)
    return build(args.db)


if __name__ == "__main__":
    sys.exit(main())
