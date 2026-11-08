"""`get_verse`, `get_chapter_overview` and the scripture side of `search` (SPEC-v2 §9).

The tool functions take a `ScriptureStore` and return a dict (the tool serializes it) or a string (a message for the
caller: unknown book, no such chapter, ...). get_verse and get_chapter_overview read only scripture.db.
"""
from dataclasses import dataclass
from typing import Optional

from config.book_resolver import BookResolver
from config.scripture_books import BOOK_CROSSWALK, CORE_BOOKS
from db import Database

NOT_AVAILABLE = (
    "The scripture corpus not available: scripture.db is missing or unusable on this server "
    "(set SCRIPTURE_DB_PATH to a built scripture.db). The talk tools are unaffected."
)

TOP_CROSS_REFERENCES = 10
_ALL = 10 ** 6          # "to the end of the chapter"


@dataclass
class ScriptureStore:
    db: Database
    resolver: BookResolver

    @classmethod
    def open(cls, db: Database) -> "ScriptureStore":
        return cls(db, BookResolver(db.select(
            "SELECT book_id, uri, name, abbr, cite_abbr, core_book_id, num_chapters FROM book ORDER BY sort")))


# ---------------------------------------------------------------------------
# References in cite form (SPEC-v2 §13)
# ---------------------------------------------------------------------------

def _span(a: int, b: Optional[int]) -> str:
    return f"{a}–{b}" if b is not None and b != a else str(a)


def format_reference(cite: str, chapter: int, verse_start: Optional[int] = None,
                     verse_end: Optional[int] = None) -> str:
    """"Alma 32", "Alma 32:21", "Alma 32:20–22"."""
    return f"{cite} {chapter}" if verse_start is None else f"{cite} {chapter}:{_span(verse_start, verse_end)}"


def _jst_reference(row: dict) -> str:
    """"JST Gen. 8:13" for a jst_verse row (its core_book_id names the book even when the store has no pages)."""
    return f"JST {CORE_BOOKS.get(row['core_book_id'], (None, None, '?'))[2]} {row['chapter']}:{row['verse']}"


def _ref_target(store: ScriptureStore, r: dict) -> Optional[str]:
    """What a footnote ref points at: "John 20:29", "JST Gen. 8:13", "tg/hope", or the raw target URI."""
    if r.get("target_help"):
        return r["target_help"]
    if r.get("jst_verse") is not None:
        return _jst_reference(dict(core_book_id=r["jst_core_book_id"], chapter=r["jst_chapter"], verse=r["jst_verse"]))
    if r.get("target_chapter") is not None:
        b = store.resolver.by_id.get(r.get("target_book_id"))
        parts = (r.get("target_uri") or "").split("/")      # /scriptures/<volume>/<book path>/<chapter>
        cite = b["cite_abbr"] if b else (BOOK_CROSSWALK.get((parts[2], "/".join(parts[3:-1])), (None,))[0]
                                         if len(parts) >= 5 and parts[1] == "scriptures" else None)
        if cite:
            return format_reference(cite, r["target_chapter"], r.get("target_verse_start"), r.get("target_verse_end"))
    return r.get("target_uri")


def _unknown_book(book: str) -> str:
    return (f"Unknown book '{book}'. Use a book of the standard works, e.g. 'Alma', '1 Nephi', '1 Ne.', "
            f"'D&C', 'Doctrine and Covenants', 'Psalms', or 'JST Genesis'.")


def _chapter(store: ScriptureStore, b: dict, number: int) -> Optional[dict]:
    return store.db.select_one("SELECT chapter_id, number, title, summary, intro FROM chapter "
                               "WHERE book_id = ? AND number = ?", (b["book_id"], number))


def _no_chapter(b: dict, chapter: int) -> str:
    n = b["num_chapters"]
    have = f" ({b['display_name']} has {n} chapter{'s' if n != 1 else ''})" if n else ""
    return f"No chapter {chapter} in {b['display_name']}{have}."


def _bounds(verse_start: Optional[int], verse_end: Optional[int]) -> tuple[int, int]:
    lo = verse_start if verse_start is not None else 1
    return lo, verse_end if verse_end is not None else (verse_start if verse_start is not None else _ALL)


# ---------------------------------------------------------------------------
# get_verse
# ---------------------------------------------------------------------------

def get_verse(store: ScriptureStore, book: str, chapter: int, verse_start: Optional[int] = None,
              verse_end: Optional[int] = None, include_footnotes: bool = True, include_jst: bool = False,
              numbering: str = "standard"):
    found = store.resolver.resolve(book)
    if found is None:
        return _unknown_book(book)
    b, jst = found
    if jst or (numbering or "").lower() == "jst":
        return _get_jst_verses(store, b, chapter, verse_start, verse_end)

    ch = _chapter(store, b, chapter)
    if ch is None and b["num_chapters"] == 1 and verse_start is None and verse_end is None:
        # single-chapter shorthand: ("Jude", 3) is Jude 1:3 when the book has no chapter 3
        ch = _chapter(store, b, 1)
        chapter, verse_start = (1, chapter) if ch else (chapter, None)
    if ch is None:
        return _no_chapter(b, chapter)
    lo, hi = _bounds(verse_start, verse_end)
    if hi < lo:
        return f"verse_end {verse_end} is before verse_start {verse_start}."

    verses = store.db.select(
        "SELECT verse_id, verse, text FROM verse WHERE chapter_id = ? AND verse BETWEEN ? AND ? ORDER BY verse",
        (ch["chapter_id"], lo, hi))
    if not verses:
        where = format_reference(b["cite_abbr"], chapter)
        return f"No verses {lo}–{hi} in {where}." if hi != _ALL else f"No verses in {where}."
    by_verse = {v["verse"]: {"reference": format_reference(b["cite_abbr"], chapter, v["verse"]),
                             "verse": v["verse"], "text": v["text"]} for v in verses}
    if include_footnotes:
        _attach_footnotes(store, ch["chapter_id"], lo, hi, by_verse)
    if include_jst:
        _attach_jst(store, b, chapter, ch["chapter_id"], lo, hi, by_verse)

    last = verses[-1]["verse"] if verse_end is not None else verse_start
    reference = format_reference(b["cite_abbr"], chapter, verse_start, last if verse_start is not None else None)
    return {"reference": reference, "chapter_summary": ch["summary"] or "", "verses": list(by_verse.values())}


_IN_RANGE = "JOIN verse v ON v.verse_id = f.verse_id WHERE v.chapter_id = ? AND v.verse BETWEEN ? AND ?"


def _attach_footnotes(store: ScriptureStore, chapter_id: int, lo: int, hi: int, by_verse: dict) -> None:
    refs: dict[int, list] = {}
    for r in store.db.select(
            "SELECT r.*, jv.verse AS jst_verse, jv.chapter AS jst_chapter, jv.core_book_id AS jst_core_book_id "
            "FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
            "LEFT JOIN jst_verse jv ON jv.jst_verse_id = r.target_jst_verse_id "
            f"{_IN_RANGE} ORDER BY r.footnote_id, r.seq", (chapter_id, lo, hi)):
        refs.setdefault(r["footnote_id"], []).append(
            {"category": r["category"], "label": r["label"], "target": _ref_target(store, r)})
    for n in store.db.select(f"SELECT f.footnote_id, v.verse, f.marker, f.context, f.text FROM footnote f "
                             f"{_IN_RANGE} ORDER BY v.verse, f.footnote_id", (chapter_id, lo, hi)):
        by_verse[n["verse"]].setdefault("footnotes", []).append(
            {"marker": n["marker"], "context": n["context"], "text": n["text"], "refs": refs.get(n["footnote_id"], [])})


def _attach_jst(store: ScriptureStore, b: dict, chapter: int, chapter_id: int, lo: int, hi: int,
                by_verse: dict) -> None:
    """What the Church links to each KJV verse as JST, kept bounded. First the targets of its `jst` footnotes, one
    {reference, text} per JST verse with core.db's full text. Then one entry per appendix passage whose "Compare"
    range covers the verse: the passage's JST range as the reference, its verses joined as the text. The text is in
    full only on the first verse of the response the passage covers; later verses get a short pointer to it."""
    found: dict[int, dict[int, dict]] = {}      # KJV verse -> jst_verse_id -> row
    for r in store.db.select(
            "SELECT v.verse AS kjv_verse, jv.* FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
            f"JOIN jst_verse jv ON jv.jst_verse_id = r.target_jst_verse_id {_IN_RANGE} AND r.category = 'jst' "
            "ORDER BY v.verse, f.footnote_id, r.seq", (chapter_id, lo, hi)):
        found.setdefault(r["kjv_verse"], {}).setdefault(r["jst_verse_id"], r)
    out = {v: [{"reference": _jst_reference(j), "text": j["text"]} for j in rows.values()] for v, rows in found.items()}

    passages: dict[int, Optional[tuple]] = {}   # passage_id -> (reference, text, jst ids), built once
    holders: dict[int, str] = {}                 # passage_id -> the verse carrying its full text
    carried: dict[int, set[int]] = {}            # KJV verse -> passage_ids already attached to it
    for c in store.db.select(
            "SELECT * FROM jst_passage_ref WHERE rel = 'compare' AND target_book_id = ? AND target_chapter <= ? "
            "AND COALESCE(target_chapter_end, target_chapter) >= ? ORDER BY passage_id, seq",
            (b["book_id"], chapter, chapter)):
        pid = c["passage_id"]
        first = (c["target_chapter"], c["target_verse_start"] or 0)
        last = (c["target_chapter_end"] or c["target_chapter"], c["target_verse_end"] or c["target_verse_start"] or _ALL)
        covered = [v for v in by_verse if first <= (chapter, v) <= last and pid not in carried.get(v, ())]
        if not covered:
            continue
        if pid not in passages:
            passages[pid] = _jst_passage(store, pid)
        if passages[pid] is None:
            continue
        reference, text, ids = passages[pid]
        for v in covered:
            carried.setdefault(v, set()).add(pid)
            if ids <= set(found.get(v, ())):     # the verse's footnotes already carry all of it
                continue
            holder = holders.setdefault(pid, by_verse[v]["reference"])
            out.setdefault(v, []).append({"reference": reference, "text": text if holder == by_verse[v]["reference"]
                                          else f"See {reference} under {holder}."})
    for verse, entries in out.items():
        by_verse[verse]["jst"] = entries


def _jst_passage(store: ScriptureStore, passage_id: int) -> Optional[tuple]:
    """(reference, text, jst_verse_ids) of an appendix passage. The reference is the passage's printed verse spec in
    cite form ("JST Gen. 9:10–15", "JST Matt. 4:1, 5–6, 8–9"); its text is its JST verses joined in order."""
    rows = store.db.select("SELECT jv.* FROM jst_passage_verse pv JOIN jst_verse jv USING (jst_verse_id) "
                           "WHERE pv.passage_id = ? ORDER BY jv.chapter, jv.verse", (passage_id,))
    if not rows:
        return None
    spec = store.db.scalar("SELECT verse_spec FROM jst_passage WHERE passage_id = ?", (passage_id,), None)
    if spec:
        reference = f"JST {CORE_BOOKS.get(rows[0]['core_book_id'], (None, None, '?'))[2]} {spec.strip()}"
    else:
        reference = _jst_reference(rows[0])
        if (rows[0]["chapter"], rows[0]["verse"]) != (rows[-1]["chapter"], rows[-1]["verse"]):
            tail = (f"{rows[-1]['chapter']}:" if rows[-1]["chapter"] != rows[0]["chapter"] else "") + str(rows[-1]["verse"])
            reference += f"–{tail}"
    return reference, " ".join(j["text"] for j in rows), {j["jst_verse_id"] for j in rows}


def _get_jst_verses(store: ScriptureStore, b: dict, chapter: int, verse_start: Optional[int],
                    verse_end: Optional[int]):
    """JST numbering input ("JST Genesis" 8:19): read jst_verse directly, J and F rows alike."""
    lo, hi = _bounds(verse_start, verse_end)
    if hi < lo:
        return f"verse_end {verse_end} is before verse_start {verse_start}."
    where, key = ("core_book_id", b["core_book_id"]) if b["core_book_id"] is not None else ("book_id", b["book_id"])
    rows = store.db.select(f"SELECT core_book_id, chapter, verse, text FROM jst_verse WHERE {where} = ? "
                           "AND chapter = ? AND verse BETWEEN ? AND ? ORDER BY verse", (key, chapter, lo, hi))
    if not rows:
        return (f"No JST verses for {b['display_name']} {chapter}"
                f"{'' if verse_start is None else ':' + _span(verse_start, verse_end)} "
                "(the JST covers the Old and New Testaments, in its own chapter and verse numbering).")
    reference = f"JST {b['cite_abbr']} {chapter}"
    if verse_start is not None:
        reference += f":{_span(verse_start, rows[-1]['verse'] if verse_end is not None else verse_start)}"
    return {"reference": reference, "chapter_summary": "",
            "verses": [{"reference": _jst_reference(r), "verse": r["verse"], "text": r["text"]} for r in rows]}


# ---------------------------------------------------------------------------
# get_chapter_overview
# ---------------------------------------------------------------------------

def get_chapter_overview(store: ScriptureStore, book: str, chapter: int):
    found = store.resolver.resolve(book)
    if found is None:
        return _unknown_book(book)
    b, jst = found
    if jst:
        return "get_chapter_overview covers the standard works' chapters, not the JST numbering."
    row = _chapter(store, b, chapter)
    if row is None:
        return _no_chapter(b, chapter)
    targets = store.db.select(
        "SELECT r.target_uri, r.target_book_id, r.target_chapter, r.target_verse_start, r.target_verse_end, "
        "COUNT(*) AS n FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
        "JOIN verse v ON v.verse_id = f.verse_id "
        "WHERE v.chapter_id = ? AND r.category != 'jst' AND r.target_help IS NULL AND r.target_chapter IS NOT NULL "
        "GROUP BY r.target_uri, r.target_chapter, r.target_verse_start, r.target_verse_end "
        "ORDER BY n DESC, MIN(f.footnote_id), MIN(r.seq) LIMIT ?", (row["chapter_id"], TOP_CROSS_REFERENCES))
    return {
        "reference": format_reference(b["cite_abbr"], row["number"]),
        "title": row["title"],
        "intro": row["intro"] or "",
        "summary": row["summary"] or "",
        "verse_count": store.db.scalar("SELECT COUNT(*) FROM verse WHERE chapter_id = ?", (row["chapter_id"],), 0),
        "top_cross_references": [{"reference": _ref_target(store, t), "count": t["n"]} for t in targets],
    }


# ---------------------------------------------------------------------------
# search: filters and result rows
# ---------------------------------------------------------------------------

def _volume_names(store: Optional[ScriptureStore], text: str) -> list[str]:
    """Weaviate `volume` values that `text` names: the text as written, plus a volume whose title (with or
    without a leading "The") or URI segment it is ("Book of Mormon", "bofm")."""
    names = [text.strip()]
    wanted = text.strip().lower().removeprefix("the ")
    try:
        rows = store.db.select("SELECT uri, title FROM volume") if store is not None else []
    except Exception:  # noqa: BLE001 — fall back to the text as written
        rows = []
    for r in rows:
        title = r["title"].lower()
        if wanted in (title, title.removeprefix("the "), r["uri"].rstrip("/").rsplit("/", 1)[-1].lower()):
            names.append(r["title"])
    return list(dict.fromkeys(names))


def build_scripture_filter(store: Optional[ScriptureStore], collection: str, *, book: Optional[str] = None,
                           volume: Optional[str] = None, chapter: Optional[int] = None,
                           variant: Optional[str] = None):
    """A Weaviate filter for a scripture search, or an error string. `collection` is "verses" or "chapters".

    `book` goes through the resolver and matches both the display name the objects hold ("Doctrine and Covenants")
    and the db's name ("Sections"); an unresolved name is matched as written. A verse search defaults to variant
    "standard"; "jst" keeps only the JST verses and "both" drops the filter.
    """
    from weaviate.classes.query import Filter

    conditions = []
    if book and book.strip():
        found = store.resolver.resolve(book) if store is not None else None
        names = [found[0]["display_name"], found[0]["name"]] if found else [book.strip()]
        conditions.append(Filter.by_property("book").contains_any(list(dict.fromkeys(names))))
    if volume and volume.strip():
        conditions.append(Filter.by_property("volume").contains_any(_volume_names(store, volume)))
    if chapter is not None:
        conditions.append(Filter.by_property("chapter").equal(int(chapter)))
    if collection == "verses":
        v = (variant or "standard").strip().lower()
        if v not in ("standard", "jst", "both"):
            return f"Unknown variant '{variant}'. Valid: standard (default), jst, both."
        if v != "both":
            conditions.append(Filter.by_property("variant").equal(v))
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else Filter.all_of(conditions)


def format_scripture_result(collection: str, props: dict, *, relevance=None, score_type=None, distance=None) -> dict:
    """A search result row: `reference` and a snippet (the verse text, or the chapter's title and summary)."""
    if collection == "verses":
        snippet = props.get("text") or ""
    else:
        snippet = "\n\n".join(p for p in (props.get("title"), props.get("summary")) if p) or (props.get("intro") or "")
    row = {"reference": props.get("reference", ""), "snippet": snippet,
           "book": props.get("book"), "volume": props.get("volume"), "chapter": props.get("chapter")}
    if collection == "verses":
        row.update(variant=props.get("variant"), verse=props.get("verse"))
        if props.get("variant") == "standard":
            row["has_jst"] = bool(props.get("has_jst"))
    else:
        row.update(title=props.get("title"), kind=props.get("kind"))
    for key, value in (("relevance", relevance), ("score_type", score_type), ("distance", distance)):
        if value is not None:
            row[key] = value
    return row
