#!/usr/bin/env python3
"""Load a built scripture.db into Weaviate (ScriptureVerses, ScriptureChapters, ScriptureMeta).

  --db PATH     the built scripture.db (default $SCRIPTURE_DB_PATH, else db/scripture.db)
  --book NAME   load one book only (name, cite abbreviation, or URI segment: "Enos", "1 Ne.", "dc"); a slice
                never writes ScriptureMeta's build_id
  --force       reload instead of resuming (with --book: only that book's objects)

Loads one book at a time (its verses, its JST `F` verses, its chapter pages), then the JST verses of books the store
has no pages for, then the front matter. Resume is by existence: an object whose deterministic UUID is stored is
skipped without being embedded. Every run records the db's build_id as ScriptureMeta's loading_build_id before its
first insert. When a recorded build (loading or finished) differs from the db's, or objects are stored with no build
recorded, anything stored may be stale, so all three collections are reset first. Only a complete load (no --book, no
failed insert) sets ScriptureMeta's build_id. Needs the embedder (EMBEDDING_URL) and Weaviate (WEAVIATE_HOST/PORT/GRPC_PORT).
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

FRONT_MATTER = None     # unit key of the pages that belong to no book


def read_store(path: str, book: str | None = None) -> tuple[str, list[tuple[str, ScriptureBundle]]]:
    """(build_id, [(label, bundle)]): every unit of the store, or only the books matching `book`."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    try:
        build_id = rows("SELECT value FROM build_meta WHERE key='build_id'")[0][0]
    except (sqlite3.OperationalError, IndexError):
        raise SystemExit(f"{path} has no build_id; run scripts/build_scriptures.py first")
    volumes = {r["uri"]: r["title"] for r in rows("SELECT uri, title FROM volume")}
    books = {r["book_id"]: r for r in rows("SELECT b.*, v.title AS volume FROM book b JOIN volume v USING (volume_id) "
                                           "ORDER BY b.sort")}
    info = {k: dict(book=display_book_name(b["uri"], b["name"]), book_uri=b["uri"], cite_abbr=b["cite_abbr"],
                    volume=b["volume"]) for k, b in books.items()}   # the book fields of a verse object

    jst = {r["jst_verse_id"]: r for r in rows("SELECT * FROM jst_verse ORDER BY chapter, verse")}
    unknown = sorted({r["core_book_id"] for r in jst.values() if r["book_id"] is None
                      and r["core_book_id"] not in CORE_BOOKS}, key=str)
    if unknown:
        raise SystemExit(f"jst_verse rows with no book in the store and a core_book_id not in "
                         f"config.scripture_books.CORE_BOOKS: {unknown}; add the book to CORE_BOOKS")

    def jst_book(r) -> dict:
        """A JST row's book: the KJV book row, or core.db's book list when the store has no pages for it."""
        if r["book_id"] is not None:
            return info[r["book_id"]]
        vol, bpath, cite = CORE_BOOKS[r["core_book_id"]]
        return dict(book=cite, book_uri=f"/scriptures/{vol}/{bpath}", cite_abbr=cite, volume=volumes.get(f"/scriptures/{vol}"))

    has_jst, jst_refs, kjv_refs = set(), {}, {}
    for r in rows("SELECT f.verse_id, r.target_jst_verse_id AS jid, b.cite_abbr, v.chapter, v.verse "
                  "FROM footnote_ref r JOIN footnote f USING (footnote_id) JOIN verse v USING (verse_id) "
                  "JOIN book b ON b.book_id = v.book_id WHERE r.category = 'jst' ORDER BY f.footnote_id, r.seq"):
        has_jst.add(r["verse_id"])
        if r["jid"] is not None:
            j = jst[r["jid"]]
            _add(jst_refs, r["verse_id"], f"JST {CORE_BOOKS[j['core_book_id']][2]} {j['chapter']}:{j['verse']}")
            _add(kjv_refs, r["jid"], f"{r['cite_abbr']} {r['chapter']}:{r['verse']}")

    units: dict = {b: ScriptureBundle([], [], []) for b in books}
    for r in rows("SELECT v.*, (SELECT COUNT(*) FROM footnote f WHERE f.verse_id = v.verse_id) AS fc "
                  "FROM verse v ORDER BY v.chapter, v.verse"):
        units[r["book_id"]].verses.append(dict(
            info[r["book_id"]], chapter=r["chapter"], verse=r["verse"], text=r["text"], aid=r["aid"], footnote_count=r["fc"],
            has_jst=r["verse_id"] in has_jst, jst_refs=jst_refs.get(r["verse_id"], [])))
    for r in jst.values():
        if r["source_flag"] == "F":
            key = r["book_id"] if r["book_id"] is not None else ("JST", r["core_book_id"])
            units.setdefault(key, ScriptureBundle([], [], [])).jst_verses.append(dict(
                jst_book(r), chapter=r["chapter"], verse=r["verse"], text=r["text"],
                kjv_refs=kjv_refs.get(r["jst_verse_id"], [])))
    units = {k: units[k] for k in [*books, *sorted(k for k in units if k not in books)]}   # books, then JST-only books
    units[FRONT_MATTER] = ScriptureBundle([], [], [])
    for r in rows("SELECT p.uri, p.kind, ch.*, (SELECT COUNT(*) FROM verse v WHERE v.chapter_id = ch.chapter_id) AS vc "
                  "FROM chapter ch JOIN page p USING (page_id) ORDER BY p.sort"):
        b = info.get(r["book_id"])
        units[r["book_id"]].chapters.append(dict(
            page_uri=r["uri"], kind=r["kind"], number=r["number"], title=r["title"], summary=r["summary"],
            intro=r["intro"], verse_count=r["vc"], volume=volumes.get("/".join(r["uri"].split("/")[:3])),
            book=b["book"] if b else None, cite_abbr=b["cite_abbr"] if b else None))
    conn.close()

    def label(key) -> str:
        return books[key]["name"] if key in books else "front matter" if key is FRONT_MATTER else CORE_BOOKS[key[1]][2]

    if book:
        wanted = book.strip().lower()
        hits = [k for k, b in books.items() if wanted in {(x or "").lower() for x in (
            b["name"], info[k]["book"], b["cite_abbr"], b["abbr"], b["uri"].rsplit("/", 1)[-1])}]
        if not hits:
            raise SystemExit(f"no book matches --book {book!r}")
        units = {k: units[k] for k in hits}
    return build_id, [(label(k), u) for k, u in units.items()]


def _add(index: dict, key, value: str) -> None:
    items = index.setdefault(key, [])
    if value not in items:
        items.append(value)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=os.environ.get("SCRIPTURE_DB_PATH") or os.path.join(ROOT, "db", "scripture.db"),
                    help="the built scripture.db (default $SCRIPTURE_DB_PATH, else db/scripture.db)")
    ap.add_argument("--book", help="load one book only (e.g. Enos)")
    ap.add_argument("--force", action="store_true", help="reload instead of resuming")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    if not os.path.exists(args.db):
        print(f"{args.db} does not exist", file=sys.stderr)
        return 2
    build_id, units = read_store(args.db, args.book)

    loader = ScriptureLoader(client=get_weaviate_client(), embed_fn=get_embedding_function(task="document"))
    try:
        meta = loader.meta()
        stale = sorted({b for b in (meta.get("build_id"), meta.get("loading_build_id")) if b and b != build_id})
        unknown = not stale and not (meta.get("build_id") or meta.get("loading_build_id")) and loader.has_objects()
        if stale:
            print(f"ScriptureMeta build {', '.join(b[:12] for b in stale)} != db {build_id[:12]}: reloading everything")
        elif unknown:
            print("Scripture collections hold objects of no recorded build: reloading everything")
        if stale or unknown or (args.force and not args.book):
            loader.reset_collections()      # also drops ScriptureMeta: a stale slice cannot sit beside a new build
        loader.write_meta(loader.meta().get("build_id"), loading_build_id=build_id)
        if not args.force:
            loader.load_existing()          # resume; --force reloads (and replaces) every object of the run

        totals = {"verses": 0, "jst": 0, "chapters": 0}
        for label, bundle in units:
            if bundle.verses or bundle.jst_verses or bundle.chapters:
                loader.load(bundle)
                totals["verses"] += len(bundle.verses)
                totals["jst"] += len(bundle.jst_verses)
                totals["chapters"] += len(bundle.chapters)
                print(f"{label}: {len(bundle.verses)} verses, {len(bundle.jst_verses)} JST, {len(bundle.chapters)} chapters")

        if loader.failures:
            print(f"{len(loader.failures)} insert failures (first: {loader.failures[0]}); "
                  f"ScriptureMeta build_id not written", file=sys.stderr)
            return 1
        if args.book:
            print("slice loaded; ScriptureMeta build_id not written")
        else:
            loader.write_meta(build_id, loading_build_id=build_id)
            print(f"loaded {totals}; ScriptureMeta build_id {build_id[:12]}")
        return 0
    finally:
        loader.close()


if __name__ == "__main__":
    sys.exit(main())
