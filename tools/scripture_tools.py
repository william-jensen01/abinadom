"""`get_verse` and `get_chapter_overview` (SPEC-v2 §9): pure functions over scripture.db.

Each takes a `ScriptureStore` and returns a dict (the tool serializes it) or a string (a message for the caller:
unknown book, no such chapter, ...). Nothing here touches Weaviate or the embedder.
"""
from dataclasses import dataclass
from typing import Optional

from config.book_resolver import BookResolver, ResolvedBook
from config.scripture_books import BOOK_CROSSWALK, CORE_BOOKS
from db import Database

NOT_AVAILABLE = (
    "The scripture corpus not available: scripture.db is missing or unusable on this server "
    "(set SCRIPTURE_DB_PATH to a built scripture.db). The talk tools are unaffected."
)

TOP_CROSS_REFERENCES = 10


@dataclass
class ScriptureStore:
    db: Database
    resolver: BookResolver

    @classmethod
    def open(cls, db: Database) -> "ScriptureStore":
        rows = db.select(
            "SELECT book_id, uri, name, abbr, cite_abbr, core_book_id, num_chapters FROM book ORDER BY sort")
        return cls(db=db, resolver=BookResolver.from_rows(rows))


# ---------------------------------------------------------------------------
# Reference text
# ---------------------------------------------------------------------------

def _span(a: int, b: Optional[int]) -> str:
    return f"{a}–{b}" if b is not None and b != a else str(a)


def format_reference(cite: str, chapter: int, verse_start: Optional[int] = None,
                     verse_end: Optional[int] = None) -> str:
    """"Alma 32", "Alma 32:21", "Alma 32:20–22" (cite form, SPEC-v2 §13)."""
    if verse_start is None:
        return f"{cite} {chapter}"
    return f"{cite} {chapter}:{_span(verse_start, verse_end)}"


def _cite_for_uri(uri: Optional[str]) -> Optional[str]:
    """Cite abbreviation of the book a `/scriptures/<volume>/<book>/<chapter>` URI is in."""
    parts = (uri or "").split("/")
    if len(parts) < 5 or parts[1] != "scriptures":
        return None
    path = "/".join(parts[3:-1])
    hit = BOOK_CROSSWALK.get((parts[2], path))
    return hit[0] if hit else None


def _jst_cite(store: ScriptureStore, book_id, core_book_id) -> str:
    b = store.resolver.by_id(book_id) if book_id is not None else None
    if b is None and core_book_id is not None:
        b = store.resolver.by_core_id(core_book_id)
    if b is not None:
        return b.cite_abbr
    return CORE_BOOKS[core_book_id][2] if core_book_id in CORE_BOOKS else "?"


def _jst_reference(store: ScriptureStore, book_id, core_book_id, chapter, verse) -> str:
    return f"JST {_jst_cite(store, book_id, core_book_id)} {chapter}:{verse}"


def _ref_target(store: ScriptureStore, r: dict) -> Optional[str]:
    """What a footnote ref points at, in cite form: "John 20:29", "JST Gen. 8:13", "tg/hope"."""
    if r.get("target_help"):
        return r["target_help"]
    if r.get("jst_verse") is not None:
        return _jst_reference(store, r["jst_book_id"], r["jst_core_book_id"], r["jst_chapter"], r["jst_verse"])
    if r.get("target_chapter") is not None:
        b = store.resolver.by_id(r["target_book_id"]) if r.get("target_book_id") is not None else None
        cite = b.cite_abbr if b else _cite_for_uri(r.get("target_uri"))
        if cite:
            return format_reference(cite, r["target_chapter"], r.get("target_verse_start"), r.get("target_verse_end"))
    return r.get("target_uri")


# ---------------------------------------------------------------------------
# Locating a chapter
# ---------------------------------------------------------------------------

def _no_chapter(rb: ResolvedBook, chapter: int) -> str:
    have = f" ({rb.display_name} has {rb.num_chapters} chapter{'s' if rb.num_chapters != 1 else ''})" \
        if rb.num_chapters else ""
    return f"No chapter {chapter} in {rb.display_name}{have}."


def _find_chapter(store: ScriptureStore, rb: ResolvedBook, chapter: int, verse_start: Optional[int],
                  verse_end: Optional[int]):
    """(chapter row, chapter number, verse_start, verse_end), or a message.

    Single-chapter shorthand: ("Jude", 3) with no verse is Jude 1:3 when the book has no chapter 3."""
    row = store.db.select_one(
        "SELECT chapter_id, number, title, summary, intro FROM chapter WHERE book_id = ? AND number = ?",
        (rb.book_id, chapter))
    if row is None and rb.num_chapters == 1 and verse_start is None and verse_end is None:
        row = store.db.select_one(
            "SELECT chapter_id, number, title, summary, intro FROM chapter WHERE book_id = ? AND number = 1",
            (rb.book_id,))
        if row is not None:
            return row, 1, chapter, None
    if row is None:
        return _no_chapter(rb, chapter)
    return row, chapter, verse_start, verse_end


def _unknown_book(book: str) -> str:
    return (f"Unknown book '{book}'. Use a book of the standard works, e.g. 'Alma', '1 Nephi', '1 Ne.', "
            f"'D&C', 'Doctrine and Covenants', 'Psalms', or 'JST Genesis'.")


# ---------------------------------------------------------------------------
# get_verse
# ---------------------------------------------------------------------------

def _range_bounds(verse_start: Optional[int], verse_end: Optional[int]) -> tuple[int, int]:
    lo = verse_start if verse_start is not None else 1
    hi = verse_end if verse_end is not None else (verse_start if verse_start is not None else 10 ** 6)
    return lo, hi


def get_verse(store: ScriptureStore, book: str, chapter: int, verse_start: Optional[int] = None,
              verse_end: Optional[int] = None, include_footnotes: bool = True, include_jst: bool = False,
              numbering: str = "standard"):
    rb = store.resolver.resolve(book)
    if rb is None:
        return _unknown_book(book)
    if rb.jst or (numbering or "").lower() == "jst":
        return _get_jst_verses(store, rb, chapter, verse_start, verse_end)

    found = _find_chapter(store, rb, chapter, verse_start, verse_end)
    if isinstance(found, str):
        return found
    ch, chapter, verse_start, verse_end = found
    lo, hi = _range_bounds(verse_start, verse_end)
    if hi < lo:
        return f"verse_end {verse_end} is before verse_start {verse_start}."

    verses = store.db.select(
        "SELECT verse_id, verse, text FROM verse WHERE chapter_id = ? AND verse BETWEEN ? AND ? ORDER BY verse",
        (ch["chapter_id"], lo, hi))
    if not verses:
        return f"No verses {lo}–{hi} in {format_reference(rb.cite_abbr, chapter)}." if hi != 10 ** 6 \
            else f"No verses in {format_reference(rb.cite_abbr, chapter)}."

    out = [{"reference": format_reference(rb.cite_abbr, chapter, v["verse"]), "verse": v["verse"], "text": v["text"]}
           for v in verses]
    by_verse = {v["verse"]: o for v, o in zip(verses, out)}

    if include_footnotes:
        _attach_footnotes(store, ch["chapter_id"], lo, hi, by_verse)
    if include_jst:
        _attach_jst(store, rb, chapter, ch["chapter_id"], lo, hi, by_verse)

    if verse_start is None:
        reference = format_reference(rb.cite_abbr, chapter)
    else:
        last = verses[-1]["verse"] if verse_end is not None else verse_start
        reference = format_reference(rb.cite_abbr, chapter, verse_start, last)
    return {"reference": reference, "chapter_summary": ch["summary"] or "", "verses": out}


def _attach_footnotes(store: ScriptureStore, chapter_id: int, lo: int, hi: int, by_verse: dict) -> None:
    notes = store.db.select(
        "SELECT f.footnote_id, v.verse, f.marker, f.context, f.text FROM footnote f "
        "JOIN verse v ON v.verse_id = f.verse_id "
        "WHERE v.chapter_id = ? AND v.verse BETWEEN ? AND ? ORDER BY v.verse, f.footnote_id",
        (chapter_id, lo, hi))
    refs = store.db.select(
        "SELECT r.footnote_id, r.category, r.label, r.target_uri, r.target_book_id, r.target_chapter, "
        "r.target_verse_start, r.target_verse_end, r.target_help, "
        "jv.verse AS jst_verse, jv.chapter AS jst_chapter, jv.book_id AS jst_book_id, "
        "jv.core_book_id AS jst_core_book_id "
        "FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
        "JOIN verse v ON v.verse_id = f.verse_id "
        "LEFT JOIN jst_verse jv ON jv.jst_verse_id = r.target_jst_verse_id "
        "WHERE v.chapter_id = ? AND v.verse BETWEEN ? AND ? ORDER BY r.footnote_id, r.seq",
        (chapter_id, lo, hi))
    by_note: dict[int, list] = {}
    for r in refs:
        by_note.setdefault(r["footnote_id"], []).append(
            {"category": r["category"], "label": r["label"], "target": _ref_target(store, r)})
    for n in notes:
        by_verse[n["verse"]].setdefault("footnotes", []).append(
            {"marker": n["marker"], "context": n["context"], "text": n["text"],
             "refs": by_note.get(n["footnote_id"], [])})


def _attach_jst(store: ScriptureStore, rb: ResolvedBook, chapter: int, chapter_id: int, lo: int, hi: int,
                by_verse: dict) -> None:
    """The JST verses the Church links to each KJV verse: its `jst` footnotes, then the appendix passages whose
    "Compare" range covers it. Text is core.db's full verse."""
    found: dict[int, dict[int, dict]] = {}      # KJV verse -> jst_verse_id -> row (insertion order = footnote first)

    for r in store.db.select(
            "SELECT v.verse AS kjv_verse, jv.jst_verse_id, jv.book_id, jv.core_book_id, jv.chapter, jv.verse, jv.text "
            "FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
            "JOIN verse v ON v.verse_id = f.verse_id "
            "JOIN jst_verse jv ON jv.jst_verse_id = r.target_jst_verse_id "
            "WHERE r.category = 'jst' AND v.chapter_id = ? AND v.verse BETWEEN ? AND ? "
            "ORDER BY v.verse, f.footnote_id, r.seq",
            (chapter_id, lo, hi)):
        found.setdefault(r["kjv_verse"], {}).setdefault(r["jst_verse_id"], r)

    compares = store.db.select(
        "SELECT pr.passage_id, pr.target_chapter, pr.target_chapter_end, pr.target_verse_start, pr.target_verse_end "
        "FROM jst_passage_ref pr WHERE pr.rel = 'compare' AND pr.target_book_id = ? AND pr.target_chapter <= ? "
        "AND COALESCE(pr.target_chapter_end, pr.target_chapter) >= ? ORDER BY pr.passage_id, pr.seq",
        (rb.book_id, chapter, chapter))
    if compares:
        passage_verses: dict[int, list] = {}
        for pid in {c["passage_id"] for c in compares}:
            passage_verses[pid] = store.db.select(
                "SELECT jv.jst_verse_id, jv.book_id, jv.core_book_id, jv.chapter, jv.verse, jv.text "
                "FROM jst_passage_verse pv JOIN jst_verse jv ON jv.jst_verse_id = pv.jst_verse_id "
                "WHERE pv.passage_id = ? ORDER BY jv.chapter, jv.verse", (pid,))
        for verse in by_verse:
            for c in compares:
                first = (c["target_chapter"], c["target_verse_start"] or 0)
                end_ch = c["target_chapter_end"] or c["target_chapter"]
                end_v = c["target_verse_end"] or c["target_verse_start"] or 10 ** 6
                if first <= (chapter, verse) <= (end_ch, end_v):
                    for jv in passage_verses[c["passage_id"]]:
                        found.setdefault(verse, {}).setdefault(jv["jst_verse_id"], jv)

    for verse, rows in found.items():
        by_verse[verse]["jst"] = [
            {"reference": _jst_reference(store, j["book_id"], j["core_book_id"], j["chapter"], j["verse"]),
             "text": j["text"]}
            for j in rows.values()]


def _get_jst_verses(store: ScriptureStore, rb: ResolvedBook, chapter: int, verse_start: Optional[int],
                    verse_end: Optional[int]):
    """JST numbering input ("JST Genesis" 8:19): read jst_verse directly, J and F rows alike."""
    lo, hi = _range_bounds(verse_start, verse_end)
    if hi < lo:
        return f"verse_end {verse_end} is before verse_start {verse_start}."
    if rb.core_book_id is not None:
        where, key = "core_book_id = ?", rb.core_book_id
    else:
        where, key = "book_id = ?", rb.book_id
    rows = store.db.select(
        f"SELECT book_id, core_book_id, chapter, verse, text FROM jst_verse WHERE {where} AND chapter = ? "
        "AND verse BETWEEN ? AND ? ORDER BY verse", (key, chapter, lo, hi))
    if not rows:
        return (f"No JST verses for {rb.display_name} {chapter}"
                f"{'' if verse_start is None else ':' + _span(verse_start, verse_end)} "
                "(the JST covers the Old and New Testaments, in its own chapter and verse numbering).")
    out = [{"reference": _jst_reference(store, r["book_id"], r["core_book_id"], r["chapter"], r["verse"]),
            "verse": r["verse"], "text": r["text"]} for r in rows]
    base = f"JST {rb.cite_abbr} {chapter}"
    if verse_start is None:
        reference = base
    else:
        reference = f"{base}:{_span(verse_start, rows[-1]['verse'] if verse_end is not None else verse_start)}"
    return {"reference": reference, "chapter_summary": "", "verses": out}


# ---------------------------------------------------------------------------
# get_chapter_overview
# ---------------------------------------------------------------------------

def get_chapter_overview(store: ScriptureStore, book: str, chapter: int):
    rb = store.resolver.resolve(book)
    if rb is None:
        return _unknown_book(book)
    if rb.jst:
        return "get_chapter_overview covers the standard works' chapters, not the JST numbering."
    row = store.db.select_one(
        "SELECT chapter_id, number, title, summary, intro FROM chapter WHERE book_id = ? AND number = ?",
        (rb.book_id, chapter))
    if row is None:
        return _no_chapter(rb, chapter)

    verse_count = store.db.scalar("SELECT COUNT(*) FROM verse WHERE chapter_id = ?", (row["chapter_id"],), 0)
    targets = store.db.select(
        "SELECT r.target_uri, r.target_book_id, r.target_chapter, r.target_verse_start, r.target_verse_end, "
        "COUNT(*) AS n FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
        "JOIN verse v ON v.verse_id = f.verse_id "
        "WHERE v.chapter_id = ? AND r.category != 'jst' AND r.target_help IS NULL AND r.target_chapter IS NOT NULL "
        "GROUP BY r.target_uri, r.target_chapter, r.target_verse_start, r.target_verse_end "
        "ORDER BY n DESC, MIN(f.footnote_id), MIN(r.seq) LIMIT ?",
        (row["chapter_id"], TOP_CROSS_REFERENCES))
    top = [{"reference": _ref_target(store, t), "count": t["n"]} for t in targets]
    return {
        "reference": format_reference(rb.cite_abbr, row["number"]),
        "title": row["title"],
        "intro": row["intro"] or "",
        "summary": row["summary"] or "",
        "verse_count": verse_count,
        "top_cross_references": top,
    }
