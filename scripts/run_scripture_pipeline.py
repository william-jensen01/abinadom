#!/usr/bin/env python3
"""Load a built scripture.db into Weaviate (ScriptureVerses, ScriptureChapters, ScriptureMeta).

  --db PATH     the built scripture.db (default db/scripture.db)
  --book NAME   load one book only (name, cite abbreviation, or URI segment: "Enos", "1 Ne.", "dc"); a slice
                never writes ScriptureMeta's build_id
  --force       drop what is loaded and reload (with --book: only that book's objects)

Streams one book at a time (verses, the book's JST `F` verses, its chapter pages), then the front matter that
belongs to no book. Resume is by existence: an object whose deterministic UUID is already stored is skipped without
being embedded. Before the first insert every run (full or --book) records the db's build_id as ScriptureMeta's
loading_build_id. When a recorded build (loading or finished) differs from the db's, or objects are stored with no build
recorded, everything stored may be stale, so all three collections are reset first. After a COMPLETE load (no --book, no
failed insert) ScriptureMeta's build_id is set to the db's.
Needs the embedder (EMBEDDING_URL) and Weaviate (WEAVIATE_HOST/PORT/GRPC_PORT).
"""
import argparse
import logging
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.embedding import get_embedding_function  # noqa: E402
from config.scripture_books import CORE_BOOKS, display_book_name  # noqa: E402
from config.weaviate_client import get_weaviate_client  # noqa: E402
from loaders.scripture_loader import ScriptureLoader  # noqa: E402
from loaders.shared_transforms import ScriptureBundle  # noqa: E402

DEFAULT_DB = os.path.join(ROOT, "db", "scripture.db")


class Store:
    """Read-only view of a built scripture.db, shaped for the transforms."""

    def __init__(self, path: str):
        self.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        have = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"verse", "chapter", "book", "jst_verse", "build_meta"} <= have:
            raise SystemExit(f"{path} has no normalized layer; run scripts/build_scriptures.py first")
        row = self.conn.execute("SELECT value FROM build_meta WHERE key='build_id'").fetchone()
        if not row:
            raise SystemExit(f"{path} has no build_meta build_id; run scripts/build_scriptures.py first")
        self.build_id = row[0]
        self.volumes = {r["uri"]: r["title"] for r in self.conn.execute("SELECT uri, title FROM volume")}
        self.books = {r["book_id"]: r for r in self.conn.execute(
            "SELECT b.book_id, b.uri, b.name, b.abbr, b.cite_abbr, b.core_book_id, v.title AS volume "
            "FROM book b JOIN volume v ON v.volume_id = b.volume_id ORDER BY b.sort")}
        self._jst_labels()

    # -- JST links, read once -------------------------------------------------
    def _jst_book(self, row) -> dict:
        """Name/uri/cite/volume of a jst_verse row's book. Normally the KJV book row; core.db's book list otherwise."""
        book = self.books.get(row["book_id"])
        if book is not None:
            return dict(book=display_book_name(book["uri"], book["name"]), book_uri=book["uri"],
                        cite_abbr=book["cite_abbr"], volume=book["volume"])
        vol, path, cite = CORE_BOOKS[row["core_book_id"]]
        return dict(book=cite, book_uri=f"/scriptures/{vol}/{path}", cite_abbr=cite,
                    volume=self.volumes.get(f"/scriptures/{vol}"))

    def _jst_labels(self) -> None:
        self.jst_rows = {r["jst_verse_id"]: r for r in self.conn.execute(
            "SELECT jst_verse_id, book_id, core_book_id, chapter, verse FROM jst_verse")}
        unknown = sorted({r["core_book_id"] for r in self.jst_rows.values()
                          if r["book_id"] not in self.books and r["core_book_id"] not in CORE_BOOKS}, key=str)
        if unknown:
            raise SystemExit(f"jst_verse rows with no book in the store and a core_book_id not in "
                             f"config.scripture_books.CORE_BOOKS: {unknown}; add the book to CORE_BOOKS")
        label = lambda r: f"JST {self._jst_book(r)['cite_abbr']} {r['chapter']}:{r['verse']}"
        self.has_jst: set[int] = set()
        self.jst_refs: dict[int, list[str]] = {}    # verse_id -> ["JST Ex. 7:3", ...]
        self.kjv_refs: dict[int, list[str]] = {}    # jst_verse_id -> ["Gen. 6:6", ...]
        for r in self.conn.execute(
                "SELECT f.verse_id, r.target_jst_verse_id AS jid, b.cite_abbr, v.chapter, v.verse "
                "FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
                "JOIN verse v ON v.verse_id = f.verse_id JOIN book b ON b.book_id = v.book_id "
                "WHERE r.category = 'jst' ORDER BY f.footnote_id, r.seq"):
            self.has_jst.add(r["verse_id"])
            if r["jid"] is None:
                continue
            _append(self.jst_refs.setdefault(r["verse_id"], []), label(self.jst_rows[r["jid"]]))
            _append(self.kjv_refs.setdefault(r["jid"], []), f"{r['cite_abbr']} {r['chapter']}:{r['verse']}")

    # -- bundles --------------------------------------------------------------
    def units(self, book: str | None):
        """(label, book_id or None, orphan core_book_id or None). A unit is one book, a JST-only book, or the front matter."""
        if book:
            key = book.strip().lower()
            hit = [b for b in self.books.values() if key in (
                b["name"].lower(), (b["cite_abbr"] or "").lower(), (b["abbr"] or "").lower(),
                b["uri"].rsplit("/", 1)[-1].lower(), display_book_name(b["uri"], b["name"]).lower())]
            if not hit:
                raise SystemExit(f"no book matches --book {book!r}")
            return [(b["name"], b["book_id"], None) for b in hit]
        units = [(b["name"], b["book_id"], None) for b in self.books.values()]
        orphans = sorted({r["core_book_id"] for r in self.jst_rows.values() if r["book_id"] not in self.books})
        units += [(CORE_BOOKS[c][2], None, c) for c in orphans]
        units.append(("front matter", None, None))
        return units

    def bundle(self, book_id: int | None, orphan_core: int | None) -> ScriptureBundle:
        c = self.conn
        if book_id is not None:
            b = self.books[book_id]
            info = dict(book=display_book_name(b["uri"], b["name"]), book_uri=b["uri"], cite_abbr=b["cite_abbr"],
                        volume=b["volume"])
            verses = [dict(info, chapter=r["chapter"], verse=r["verse"], text=r["text"], aid=r["aid"],
                           footnote_count=r["fc"], has_jst=r["verse_id"] in self.has_jst,
                           jst_refs=self.jst_refs.get(r["verse_id"], []))
                      for r in c.execute(
                          "SELECT v.verse_id, v.chapter, v.verse, v.aid, v.text, "
                          "(SELECT COUNT(*) FROM footnote f WHERE f.verse_id = v.verse_id) AS fc "
                          "FROM verse v WHERE v.book_id = ? ORDER BY v.chapter, v.verse", (book_id,))]
            jst_where, jst_args = "book_id = ?", (book_id,)
            chapter_where, chapter_args = "ch.book_id = ?", (book_id,)
        else:
            verses = []
            jst_where, jst_args = ("book_id IS NULL AND core_book_id = ?", (orphan_core,)) if orphan_core else ("0", ())
            chapter_where, chapter_args = ("ch.book_id IS NULL", ()) if orphan_core is None else ("0", ())
        jst = [dict(self._jst_book(r), chapter=r["chapter"], verse=r["verse"], text=r["text"],
                    kjv_refs=self.kjv_refs.get(r["jst_verse_id"], []))
               for r in c.execute(
                   f"SELECT jst_verse_id, book_id, core_book_id, chapter, verse, text FROM jst_verse "
                   f"WHERE source_flag = 'F' AND {jst_where} ORDER BY chapter, verse", jst_args)]
        chapters = []
        for r in c.execute(
                f"SELECT p.uri, p.kind, ch.number, ch.title, ch.summary, ch.intro, ch.book_id, "
                f"(SELECT COUNT(*) FROM verse v WHERE v.chapter_id = ch.chapter_id) AS vc "
                f"FROM chapter ch JOIN page p ON p.page_id = ch.page_id WHERE {chapter_where} ORDER BY p.sort",
                chapter_args):
            b = self.books.get(r["book_id"])
            volume = self.volumes.get("/".join(r["uri"].split("/")[:3]))
            chapters.append(dict(page_uri=r["uri"], kind=r["kind"], number=r["number"], title=r["title"],
                                 summary=r["summary"], intro=r["intro"], verse_count=r["vc"], volume=volume,
                                 book=display_book_name(b["uri"], b["name"]) if b else None,
                                 cite_abbr=b["cite_abbr"] if b else None))
        return ScriptureBundle(verses, jst, chapters)


def _append(items: list, value: str) -> None:
    if value not in items:
        items.append(value)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB, help="the built scripture.db (default db/scripture.db)")
    ap.add_argument("--book", help="load one book only (e.g. Enos)")
    ap.add_argument("--force", action="store_true", help="reload instead of resuming")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    if not os.path.exists(args.db):
        print(f"{args.db} does not exist", file=sys.stderr)
        return 2
    store = Store(args.db)
    units = store.units(args.book)

    loader = ScriptureLoader(client=get_weaviate_client(), embed_fn=get_embedding_function(task="document"))
    try:
        # A resume keeps only objects of the db's own build: any recorded build (finished or in progress) that
        # differs, or objects with no build recorded at all, mean stale objects may be stored, so start clean.
        stored, loading = loader.get_build_id(), loader.get_loading_build_id()
        stale = sorted({b for b in (stored, loading) if b and b != store.build_id})
        unknown = not stored and not loading and loader.has_objects()
        changed = bool(stale or unknown)
        if stale:
            print(f"ScriptureMeta build {', '.join(b[:12] for b in stale)} != db {store.build_id[:12]}: "
                  f"reloading everything")
        elif unknown:
            print("Scripture collections hold objects of no recorded build: reloading everything")
        if changed or (args.force and not args.book):
            loader.reset_collections()          # also drops ScriptureMeta; a stale slice cannot sit beside a new build
        loader.mark_loading(store.build_id)     # before the first insert, on full and --book runs
        loader.load_existing()

        totals = {"verses": 0, "jst": 0, "chapters": 0}
        for label, book_id, orphan in units:
            bundle = store.bundle(book_id, orphan)
            if not (bundle.verses or bundle.jst_verses or bundle.chapters):
                continue
            if args.force and args.book and not changed:
                loader.delete_bundle(bundle)
            loader.load(bundle)
            totals["verses"] += len(bundle.verses)
            totals["jst"] += len(bundle.jst_verses)
            totals["chapters"] += len(bundle.chapters)
            print(f"{label}: {len(bundle.verses)} verses, {len(bundle.jst_verses)} JST, {len(bundle.chapters)} chapters")

        failures = loader.pop_insert_failures()
        if failures:
            print(f"{len(failures)} insert failures (first: {failures[0]}); ScriptureMeta build_id not written", file=sys.stderr)
            return 1
        if args.book:
            print("slice loaded; ScriptureMeta build_id not written")
        else:
            loader.write_build_id(store.build_id)
            print(f"loaded {totals}; ScriptureMeta build_id {store.build_id[:12]}")
        return 0
    finally:
        loader.close()


if __name__ == "__main__":
    sys.exit(main())
