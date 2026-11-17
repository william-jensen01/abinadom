#!/usr/bin/env python3
"""Build the normalized layer of scripture.db from its raw layer and core.db's JST.

  --db PATH   the scripture.db to build in place (default $SCI_DB_DIR/scripture.db, else db/scripture.db)

Fails, naming them, when a TOC page or a page a TOC links to has no stored response. Otherwise drops and
recreates every normalized table in ONE transaction, parses every page, imports core.db's J/F rows, links the
`jst` footnotes and the JST appendix passages, and runs the build checks; a failed check rolls everything back.
The raw layer is never touched. `build_meta.build_id` is a sha256 over the normalized tables' content, so
rebuilding the same raw data gives the same id.
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

from config.scripture_books import BOOK_CROSSWALK, SUB_BOOK_NAMES, VOLUME_ABBR, book_abbr  # noqa: E402
from db import SCI_DB_VERSION, SCRIPTURE_DB_PATH  # noqa: E402
from extractors import scripture_jst as jst  # noqa: E402
from extractors import scripture_page as sp  # noqa: E402

DEFAULT_DB = SCRIPTURE_DB_PATH  # beside the talk dbs: $SCI_DB_DIR/scripture.db, else db/scripture.db
SCHEMA = os.path.join(ROOT, "db", "scripture_schema.sql")
MARKER = "-- ==== normalized layer ===="
TABLES = ["volume", "book", "page", "chapter", "verse", "jst_verse", "footnote", "footnote_ref",
          "jst_passage", "jst_passage_verse", "jst_passage_ref"]   # hashed into build_id, in this order
SAMPLE = 8
VERSE_P = re.compile(r'<p\b[^>]*\bclass="(?:[^"]*\s)?verse(?:\s[^"]*)?"')   # an independent count of verse paragraphs


class BuildError(Exception):
    pass


def insert(conn, table, **row):
    cur = conn.execute(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                       list(row.values()))
    return cur.lastrowid


def build_id_of(conn) -> str:
    h = hashlib.sha256()
    for table in TABLES:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        h.update(f"#{table}:{','.join(cols)}\n".encode())
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY {', '.join(str(i + 1) for i in range(len(cols)))}"):
            h.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
    return h.hexdigest()


class Builder:
    def __init__(self, conn, raw: dict, core_rows: list):
        self.conn, self.raw = conn, raw
        self.errors, self.report = [], []
        self.book_ids, self.page_ids, self.pages = {}, {}, {}   # pages: uri -> sp.Page
        # JST verses: ids are 1.. in core.db ID order; looked up by (core BookID, JST chapter, JST verse)
        self.core_rows = core_rows
        self.jst_ids = {(r["BookID"], r["Chapter"], r["Verse"]): i for i, r in enumerate(core_rows, 1)}
        self.jst_by_book = defaultdict(list)   # core BookID -> sorted [(chapter, verse, jst_verse_id)]
        for i, r in enumerate(core_rows, 1):
            self.jst_by_book[r["BookID"]].append((r["Chapter"], r["Verse"], i))
        for rows in self.jst_by_book.values():
            rows.sort()

    def fail(self, msg, items):
        if items:
            self.errors.append(f"{msg}: {len(items)} — " + "; ".join(map(str, items[:SAMPLE])))

    def data(self, uri) -> dict:
        return json.loads(self.raw[uri])

    # -- volumes, books, pages ---------------------------------------------
    def structure(self, tocs: dict) -> None:
        order = dict.fromkeys(u for vol, links in tocs.items() for u in [f"/scriptures/{vol}", *links])
        self.pages = {uri: sp.parse_page(uri, self.data(uri)) for uri in order}
        for sort, (vol, links) in enumerate(tocs.items()):
            vuri = f"/scriptures/{vol}"
            if vol != "jst":
                volume_id = insert(self.conn, "volume", uri=vuri, title=self.pages[vuri].title or vol,
                                   abbr=VOLUME_ABBR.get(vol), sort=sort)
                groups = sp.toc_groups(self.data(vuri))
                for uri in links:
                    if b := sp.book_uri(uri):
                        names, parent = groups.get(uri) or [None], "/".join(b.split("/")[:4])
                        # a sub-book's parent first (abr for abr/fac), named by the outermost group; the sub-book
                        # by its own group nested in the parent's, or else by SUB_BOOK_NAMES
                        self.add_book(vol, volume_id, parent, names[-1])
                        self.add_book(vol, volume_id, b, names[0] if b == parent or len(names) > 1 else None)
        for sort, (uri, page) in enumerate(self.pages.items()):
            self.page_ids[uri] = insert(self.conn, "page", uri=uri, book_id=self.book_ids.get(sp.book_uri(uri)),
                                        kind=page.kind, title=page.title, sort=sort)
        self.num_chapters({u for links in tocs.values() for u in links})

    def add_book(self, vol, volume_id, uri, name) -> None:
        if uri not in self.book_ids:
            path = uri.split("/", 3)[3]
            name = name or SUB_BOOK_NAMES.get((vol, path))
            cite, core_id = BOOK_CROSSWALK.get((vol, path), (name or path, None))
            self.book_ids[uri] = insert(self.conn, "book", volume_id=volume_id, uri=uri, name=name or path,
                                        abbr=book_abbr(path), cite_abbr=cite, sort=len(self.book_ids),
                                        num_chapters=None, core_book_id=core_id)

    def num_chapters(self, toc_links: set) -> None:
        """book.num_chapters from the TOC pages, never from chapter rows: the pages a book's `_contents` page lists
        (Abraham's `fac-N` links count toward the Facsimiles), or, for a book without one, its chapter-like links
        in the volume TOC. `_contents` links that no volume TOC lists were not fetched; they are reported."""
        from_contents, unlisted = Counter(), []
        for uri, page in self.pages.items():
            if page.kind == "book_toc" and sp.book_uri(uri):
                from_contents[sp.book_uri(uri)] += 0
                for link in sp.contents_links(self.data(uri)):
                    if link in toc_links:
                        from_contents[sp.book_uri(link) or sp.book_uri(uri)] += 1
                    else:
                        unlisted.append(link)
        in_toc = Counter(sp.book_uri(u) for u, page in self.pages.items() if page.kind in sp.CHAPTER_KINDS)
        self.fail("_contents links that count toward a book with no book row",
                  [b for b in from_contents if b not in self.book_ids])
        self.conn.executemany("UPDATE book SET num_chapters = ? WHERE uri = ?", [
            (from_contents[b] if b in from_contents else in_toc[b], b) for b in self.book_ids])
        if unlisted:
            self.report.append(f"_contents links no volume TOC lists (not fetched, not counted): {len(unlisted)} "
                               f"(e.g. {', '.join(unlisted[:SAMPLE])})")

    # -- JST verses ----------------------------------------------------------
    def jst_verses(self) -> None:
        books = {core: bid for core, bid in self.conn.execute(
            "SELECT core_book_id, book_id FROM book WHERE core_book_id IS NOT NULL")}
        text = lambda t: t.decode("utf-8") if isinstance(t, (bytes, bytearray)) else ("" if t is None else str(t))
        self.conn.executemany(
            "INSERT INTO jst_verse (jst_verse_id, core_id, book_id, core_book_id, chapter, verse, source_flag, text) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(i, r["ID"], books.get(r["BookID"]), r["BookID"], r["Chapter"], r["Verse"], r["Flag"], text(r["Text"]))
             for i, r in enumerate(self.core_rows, 1)])

    # -- chapters, verses, footnotes -----------------------------------------
    def content(self) -> None:
        bad_verses, bad_pids, bad_markers = [], [], []
        for uri, page in self.pages.items():
            page_id, book_id = self.page_ids[uri], self.book_ids.get(sp.book_uri(uri))
            verse_ids = {}
            if page.kind in sp.CHAPTER_KINDS:
                chapter_id = insert(self.conn, "chapter", page_id=page_id, book_id=book_id, number=page.number,
                                    title=page.title, summary=page.summary, intro=page.intro,
                                    summary_html=page.summary_html, intro_html=page.intro_html)
                for v in page.verses:
                    verse_ids[v.aid] = insert(self.conn, "verse", chapter_id=chapter_id, book_id=book_id,
                                              chapter=page.number, verse=v.verse, aid=v.aid, pid_html_id=v.html_id,
                                              text=v.text, text_html=v.text_html)
                numbers = [v.verse for v in page.verses]
                if numbers != list(range(1, len(numbers) + 1)) or \
                        len(VERSE_P.findall(self.data(uri)["content"].get("body") or "")) != len(numbers):
                    bad_verses.append(uri)
            for fn in page.footnotes:
                footnote_id = insert(self.conn, "footnote", verse_id=verse_ids.get(fn.pid), note_key=fn.note_key,
                                     marker=fn.marker, letter=fn.letter, context=fn.context, text=fn.text,
                                     text_html=fn.text_html, page_id=page_id, anchor_aid=fn.pid)
                for seq, r in enumerate(fn.refs):
                    insert(self.conn, "footnote_ref", footnote_id=footnote_id, seq=seq, category=r.category,
                           ref_type=r.ref_type, href=r.href, label=r.label, target_uri=r.target_uri,
                           target_book_id=self.book_ids.get(r.book_uri), target_chapter=r.chapter,
                           target_verse_start=r.verse_start, target_verse_end=r.verse_end, target_help=r.help,
                           target_jst_verse_id=self.jst_ids.get((r.jst_book, r.chapter, r.verse_start))
                           if r.category == "jst" else None)
            # a verse note's pid is a verse aid; body markers and footnote entries match (a note that is not
            # on a verse, e.g. a table note, may have no marker)
            if page.kind in ("chapter", "section"):
                bad_pids += [(uri, fn.note_key) for fn in page.footnotes
                             if re.fullmatch(r"note\d+_[a-z]+", fn.note_key) and fn.pid not in verse_ids]
            keys, markers = {fn.note_key for fn in page.footnotes}, set(page.note_markers)
            on_verses = {fn.note_key for fn in page.footnotes if fn.pid in verse_ids}
            if markers - keys or on_verses - markers:
                bad_markers.append((uri, sorted(markers - keys)[:3], sorted(on_verses - markers)[:3]))
        self.fail("chapters whose verses are not 1..N or not the body's verse paragraphs", bad_verses)
        self.fail("verse footnotes whose pid matches no verse aid", bad_pids)
        self.fail("pages whose study-note-ref markers and footnote entries differ (uri, marker only, entry only)",
                  bad_markers)

    # -- JST appendix passages -----------------------------------------------
    def passages(self) -> None:
        books = {core: bid for core, bid in self.conn.execute(
            "SELECT core_book_id, book_id FROM book WHERE core_book_id IS NOT NULL")}
        unparsed, mismatched, no_compare, unnamed, rels, named = [], [], [], [], Counter(), 0
        for uri, page in self.pages.items():
            if page.kind != "jst_appendix":
                continue
            core_book = sp.jst_book(uri)
            for seq, p in enumerate(jst.parse_appendix(uri, self.data(uri))):
                if not p.ranges or core_book is None:
                    unparsed.append(f"{uri} ({p.title})")
                first, last = (p.ranges[0], p.ranges[-1]) if p.ranges else ((None,) * 4, (None,) * 4)
                passage_id = insert(self.conn, "jst_passage", page_id=self.page_ids[uri], seq=seq,
                                    section_id=p.section_id, anchor_aid=p.anchor_aid, title=p.title,
                                    verse_spec=p.verse_spec, book_id=books.get(core_book), core_book_id=core_book,
                                    chapter_start=first[0], verse_start=first[1], chapter_end=last[2],
                                    verse_end=last[3], intro=p.intro)
                ids = [i for c1, v1, c2, v2 in p.ranges or [] for c, v, i in self.jst_by_book.get(core_book, [])
                       if (c1, v1) <= (c, v) <= (c2, v2)]
                self.conn.executemany("INSERT INTO jst_passage_verse (passage_id, jst_verse_id) VALUES (?,?)",
                                      [(passage_id, i) for i in dict.fromkeys(ids)])
                named += len(set(ids))
                wanted = [(c1, v) for c1, v1, c2, v2 in p.ranges or [] if c1 == c2 for v in range(v1, v2 + 1)]
                heading = sorted({v for _, v in wanted})
                if p.paragraphs and heading != sorted(p.paragraphs):
                    mismatched.append(p.title)
                if any((core_book, c, v) not in self.jst_ids for c, v in wanted):
                    unnamed.append(p.title)
                if not any(rel == "compare" for rel, _, _ in p.refs):
                    no_compare.append(p.title)
                for ref_seq, (rel, r, chapter_end) in enumerate(p.refs):
                    rels[rel] += 1
                    insert(self.conn, "jst_passage_ref", passage_id=passage_id, seq=ref_seq, rel=rel, href=r.href,
                           label=r.label, target_uri=r.target_uri, target_book_id=self.book_ids.get(r.book_uri),
                           target_chapter=r.chapter, target_chapter_end=chapter_end,
                           target_verse_start=r.verse_start, target_verse_end=r.verse_end)
        self.fail("appendix passages whose heading does not parse to a JST verse range", unparsed)
        n = self.conn.execute("SELECT COUNT(*) FROM jst_passage").fetchone()[0]
        self.report.append(f"jst appendix passages: {n}, heading links: {dict(rels)}, jst_verse rows named: "
                           f"{named}; no Compare link: {len(no_compare)}; heading verses not in jst_verse: "
                           f"{len(unnamed)}" + (f" ({'; '.join(unnamed[:SAMPLE])})" if unnamed else "")
                           + f"; headings whose verses differ from the printed paragraphs: {mismatched[:SAMPLE]}")

    # -- the remaining build checks ----------------------------------------------
    def validate(self, core_count: int) -> None:
        c = self.conn
        self.fail("verse.text with HTML, a leading verse number or no text", c.execute(
            "SELECT verse_id, substr(text, 1, 50) FROM verse WHERE text LIKE '%<%' OR text LIKE '%>%' "
            "OR text GLOB '[0-9]*' OR trim(text) = ''").fetchall())
        self.fail("books whose chapter rows != num_chapters from the TOC (uri, num_chapters, chapter rows)", c.execute(
            "SELECT uri, num_chapters, (SELECT COUNT(*) FROM chapter ch WHERE ch.book_id = b.book_id) n FROM book b "
            "WHERE num_chapters IS NULL OR num_chapters != n ORDER BY sort").fetchall())
        self.fail("verse-bearing pages without a chapter number", c.execute(
            "SELECT p.uri FROM chapter ch JOIN page p USING (page_id) WHERE ch.number IS NULL "
            "AND EXISTS (SELECT 1 FROM verse v WHERE v.chapter_id = ch.chapter_id)").fetchall())
        n_jst = c.execute("SELECT COUNT(*) FROM jst_verse").fetchone()[0]
        if n_jst != core_count or n_jst == 0:
            self.errors.append(f"jst_verse rows {n_jst} != core.db J+F rows {core_count}")
        unresolved = [r[0] for r in c.execute(
            "SELECT label FROM footnote_ref WHERE category = 'jst' AND target_jst_verse_id IS NULL")]
        total = c.execute("SELECT COUNT(*) FROM footnote_ref WHERE category = 'jst'").fetchone()[0]
        self.report.append(f"jst_verse: {n_jst}; jst refs: {total}, unresolved: {len(unresolved)}"
                           + (f" ({'; '.join(sorted(set(unresolved))[:SAMPLE])})" if unresolved else ""))
        rows = c.execute(  # scripture refs that resolve to no book: reported, not fatal
            "SELECT target_uri, COUNT(*) FROM footnote_ref WHERE target_help IS NULL AND target_book_id IS NULL "
            "AND target_uri IS NOT NULL AND target_uri NOT LIKE '/scriptures/jst/%' GROUP BY 1 ORDER BY 2 DESC, 1"
        ).fetchall()
        total = c.execute("SELECT COUNT(*) FROM footnote_ref WHERE target_uri IS NOT NULL AND target_help IS NULL "
                          "AND target_uri NOT LIKE '/scriptures/jst/%'").fetchone()[0]
        self.jst_checks()
        self.report.append(f"scripture refs: {total}; resolved to no book: {sum(n for _, n in rows)}"
                           + (f" ({', '.join(f'{u} x{n}' for u, n in rows[:SAMPLE])})" if rows else ""))

    def jst_checks(self) -> None:
        c = self.conn
        # F rows (the JST the Church's Bible shows) that no jst footnote and no appendix passage names: reported
        rows = c.execute(
            "SELECT COALESCE(b.abbr, '?') || ' ' || j.chapter || ':' || j.verse "
            "FROM jst_verse j LEFT JOIN book b ON b.book_id = j.book_id WHERE j.source_flag = 'F' "
            "AND NOT EXISTS (SELECT 1 FROM footnote_ref r WHERE r.category = 'jst' AND r.target_jst_verse_id = j.jst_verse_id) "
            "AND NOT EXISTS (SELECT 1 FROM jst_passage_verse pv WHERE pv.jst_verse_id = j.jst_verse_id) "
            "ORDER BY j.jst_verse_id").fetchall()
        self.report.append(f"jst_verse F rows no jst footnote or appendix passage names: {len(rows)}"
                           + (f" (e.g. {', '.join(r for r, in rows[:SAMPLE])})" if rows else ""))
        # KJV Ex 7:3 must have a jst footnote_ref to JST Ex 7:3
        if not c.execute("SELECT 1 FROM page WHERE uri = '/scriptures/ot/ex/7'").fetchone():
            self.report.append("KJV Ex 7:3 -> JST Ex 7:3: not checked, /scriptures/ot/ex/7 is not in the store")
        elif c.execute(
                "SELECT 1 FROM footnote_ref r JOIN footnote f USING (footnote_id) JOIN verse v USING (verse_id) "
                "JOIN chapter ch ON ch.chapter_id = v.chapter_id JOIN page p ON p.page_id = ch.page_id "
                "JOIN jst_verse j ON j.jst_verse_id = r.target_jst_verse_id "
                "WHERE r.category = 'jst' AND p.uri = '/scriptures/ot/ex/7' AND v.verse = 3 "
                "AND j.book_id = ch.book_id AND j.chapter = 7 AND j.verse = 3").fetchone():
            self.report.append("KJV Ex 7:3 -> JST Ex 7:3: linked")
        else:
            self.errors.append("KJV Ex 7:3 has no jst footnote_ref to JST Ex 7:3 (jst_verse chapter 7, verse 3)")


def build(db_path: str) -> int:
    if not os.path.exists(db_path):
        print(f"ERROR: {db_path} does not exist; run scripts/fetch_scriptures.py first", file=sys.stderr)
        return 1
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        if conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('raw_page', 'raw_latest')").fetchone()[0] < 2:
            raise BuildError(f"{db_path} has no raw layer; run scripts/fetch_scriptures.py first")
        raw = {u: (h, js) for u, h, js in conn.execute(
            "SELECT uri, content_hash, json FROM raw_latest WHERE lang = 'eng' AND status = 200")}
        tocs = {v: sp.toc_links(json.loads(raw[f"/scriptures/{v}"][1])) if f"/scriptures/{v}" in raw else None
                for v in sp.TOC_VOLUMES}
        missing = [f"/scriptures/{v}" for v, links in tocs.items() if links is None]
        missing += [u for links in tocs.values() for u in links or [] if u not in raw]
        if missing:
            raise BuildError(f"{len(missing)} TOC page(s) or page(s) linked from a TOC have no stored response "
                             f"(fetch them first): {', '.join(missing[:50])}")
        try:
            core_rows, core_count = jst.read_core_jst()
        except FileNotFoundError as e:
            raise BuildError(str(e))

        with open(SCHEMA, encoding="utf-8") as f:
            ddl = f.read().split(MARKER, 1)[1]
        drops = "".join(f"DROP TABLE IF EXISTS {t};" for t in ["build_meta", *reversed(TABLES)])
        conn.executescript("BEGIN;" + drops + ddl)   # the transaction stays open until COMMIT below
        try:
            b = Builder(conn, {u: js for u, (_, js) in raw.items()}, core_rows)
            b.structure(tocs)
            b.jst_verses()
            b.content()
            b.passages()
            b.validate(core_count)
            if b.errors:
                raise BuildError("validation failed:\n  - " + "\n  - ".join(b.errors))
            build_id = build_id_of(conn)
            meta = {"build_id": build_id, "schema_version": "1", "raw_pages": str(len(raw)),
                    "raw_hash": hashlib.sha256("\n".join(f"{u}\t{h}" for u, (h, _) in sorted(raw.items()))
                                               .encode()).hexdigest(),
                    "core_db_version": SCI_DB_VERSION,
                    "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            conn.executemany("INSERT INTO build_meta (key, value) VALUES (?, ?)", sorted(meta.items()))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ["volume", "book", "page", "chapter", "verse", "footnote", "footnote_ref"]}
    except BuildError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print("build ok: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("\n".join(b.report))
    print(f"build_id: {build_id}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB, help="scripture.db to build in place (default $SCI_DB_DIR/scripture.db, else db/scripture.db)")
    return build(ap.parse_args(argv).db)


if __name__ == "__main__":
    sys.exit(main())
