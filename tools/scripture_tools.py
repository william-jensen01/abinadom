"""`get_verse`, `get_chapter_overview` and the scripture side of `search`.

The tool functions take a `ScriptureStore` and return a dict (the tool serializes it) or a string (a message for the
caller: unknown book, no such chapter, ...). get_verse, get_chapter_overview and find_cross_references read only
scripture.db; get_verse's citing talk counts and get_citing_talks also read core.db.
"""
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from config.book_resolver import BookResolver
from config.scripture_books import BOOK_CROSSWALK, CORE_BOOKS
import db as sci_db
from db import Database

NOT_AVAILABLE = (
    "Error: scripture corpus not available on this server (scripture.db is missing or unusable; "
    "build scripture.db into the directory SCI_DB_DIR names). The talk tools are unaffected."
)

TOP_CROSS_REFERENCES = 10
_ALL = 10 ** 6          # "to the end of the chapter"
# The one appendix passage whose text is published as the Book of Moses, named by its JST range: (book, first
# chapter, first verse, last chapter, last verse). Citing talks do not follow it; the Moses footnotes stand in for it.
MOSES_PASSAGE = ("Genesis", 1, 1, 8, 18)


@dataclass
class ScriptureStore:
    db: Database
    resolver: BookResolver

    @classmethod
    def open(cls, db: Database) -> "ScriptureStore":
        return cls(db, BookResolver(db.select(
            "SELECT book_id, uri, name, abbr, cite_abbr, core_book_id, num_chapters FROM book ORDER BY sort")))


# ---------------------------------------------------------------------------
# References in cite form
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


_JST_CITES = {path: cite for (volume, path), (cite, _) in BOOK_CROSSWALK.items() if volume in ("ot", "nt")}
_JST_TEXT_CITE = re.compile(r"JST\s+((?:\d\s+)?[A-Z][A-Za-z]*\.?)\s+\d")


def _jst_link_target(r: dict) -> Optional[str]:
    """"JST Ex. 33:20" for a ref into the JST appendix (`/scriptures/jst/jst-ex/33`, verses from the link) or a
    JST verse named by a note's text, when it has no jst_verse row; else the label (it names the JST passage)."""
    parts = (r.get("target_uri") or "").split("/")      # /scriptures/jst/jst-<book>/<chapter>
    path = parts[3].removeprefix("jst-") if len(parts) == 5 else None
    if path in _JST_CITES and parts[2] == "jst" and parts[4].isdigit():
        return format_reference(f"JST {_JST_CITES[path]}", int(parts[4]), r.get("target_verse_start"),
                                r.get("target_verse_end"))
    m = _JST_TEXT_CITE.match(r.get("label") or "") if r.get("ref_type") == "jst-note" else None
    if m and r.get("target_chapter") is not None:
        return format_reference(f"JST {m.group(1)}", r["target_chapter"], r.get("target_verse_start"),
                                r.get("target_verse_end"))
    return r.get("label") or r.get("target_uri")


def _ref_target(store: ScriptureStore, r: dict) -> Optional[str]:
    """What a footnote ref points at: "John 20:29", "JST Gen. 8:13", "tg/hope", or (a page that is not a chapter)
    the raw target URI."""
    if r.get("target_help"):
        return r["target_help"]
    if r.get("jst_verse") is not None:
        return _jst_reference(dict(core_book_id=r["jst_core_book_id"], chapter=r["jst_chapter"], verse=r["jst_verse"]))
    if r.get("category") == "jst" or (r.get("target_uri") or "").startswith("/scriptures/jst/"):
        return _jst_link_target(r)
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
              numbering: str = "standard", include_citing_talks: bool = False):
    result, scope = _read_verses(store, book, chapter, verse_start, verse_end, include_footnotes, include_jst,
                                 numbering, include_citing_talks)
    if include_citing_talks and scope is not None:
        _attach_citing_counts(result, scope)
    return result


def _read_verses(store: ScriptureStore, book: str, chapter: int, verse_start: Optional[int],
                 verse_end: Optional[int], include_footnotes: bool, include_jst: bool, numbering: str,
                 want_scope: bool):
    """(result, scope): get_verse's result (or a message string) and, when `want_scope` and verses were found, the
    citation scope of those verses (see _citation_keys)."""
    found = store.resolver.resolve(book)
    if found is None:
        return _unknown_book(book), None
    b, jst = found
    if jst or (numbering or "").lower() == "jst":
        result = _get_jst_verses(store, b, chapter, verse_start, verse_end)
        scope = None
        if want_scope and isinstance(result, dict) and b["core_book_id"] is not None:
            # core.db numbers Flag='J' citations in JST chapters and verses, as read here
            keys = {("J", b["core_book_id"], chapter, v["verse"]): v["reference"] for v in result["verses"]}
            scope = ([v["reference"] for v in result["verses"]], keys, {k: {ref} for k, ref in keys.items()}, {})
        return result, scope

    ch = _chapter(store, b, chapter)
    if ch is None and b["num_chapters"] == 1 and verse_start is None and verse_end is None:
        # single-chapter shorthand: ("Jude", 3) is Jude 1:3 when the book has no chapter 3
        ch = _chapter(store, b, 1)
        chapter, verse_start = (1, chapter) if ch else (chapter, None)
    if ch is None:
        return _no_chapter(b, chapter), None
    lo, hi = _bounds(verse_start, verse_end)
    if hi < lo:
        return f"verse_end {verse_end} is before verse_start {verse_start}.", None

    verses = store.db.select(
        "SELECT verse_id, verse, text FROM verse WHERE chapter_id = ? AND verse BETWEEN ? AND ? ORDER BY verse",
        (ch["chapter_id"], lo, hi))
    if not verses:
        where = format_reference(b["cite_abbr"], chapter)
        if hi == _ALL:
            return f"No verses in {where}.", None
        return (f"No verse {lo} in {where}." if lo == hi else f"No verses {lo}–{hi} in {where}."), None
    by_verse = {v["verse"]: {"reference": format_reference(b["cite_abbr"], chapter, v["verse"]),
                             "verse": v["verse"], "text": v["text"]} for v in verses}
    if include_footnotes:
        _attach_footnotes(store, ch["chapter_id"], lo, hi, by_verse)
    if include_jst:
        _attach_jst(store, b, chapter, ch["chapter_id"], lo, hi, by_verse)

    last = verses[-1]["verse"] if verse_end is not None else verse_start
    reference = format_reference(b["cite_abbr"], chapter, verse_start, last if verse_start is not None else None)
    result = {"reference": reference, "chapter_summary": ch["summary"] or "", "verses": list(by_verse.values())}
    scope = None
    if want_scope:
        keys, origin, via = _citation_keys(store, b, chapter, ch["chapter_id"], lo, hi, by_verse)
        scope = ([row["reference"] for row in by_verse.values()], keys, origin, via)
    return result, scope


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

    passages: dict[int, Optional[tuple]] = {}   # passage_id -> (reference, text, jst rows), built once
    holders: dict[int, str] = {}                 # passage_id -> the verse carrying its full text
    carried: dict[int, set[int]] = {}            # KJV verse -> passage_ids already attached to it
    for pid, linked in _compare_links(store, b, chapter, by_verse):
        covered = [v for v in linked if pid not in carried.get(v, ())]
        if not covered:
            continue
        if pid not in passages:
            passages[pid] = _jst_passage(store, pid)
        if passages[pid] is None:
            continue
        reference, text, rows = passages[pid]
        for v in covered:
            carried.setdefault(v, set()).add(pid)
            if {j["jst_verse_id"] for j in rows} <= set(found.get(v, ())):   # its footnotes already carry all of it
                continue
            holder = holders.setdefault(pid, by_verse[v]["reference"])
            out.setdefault(v, []).append({"reference": reference, "text": text if holder == by_verse[v]["reference"]
                                          else f"See {reference} under {holder}."})
    for verse, entries in out.items():
        by_verse[verse]["jst"] = entries


def _compare_links(store: ScriptureStore, b: dict, chapter: int, verses) -> list[tuple[int, list[int]]]:
    """(passage_id, covered) for each "Compare" heading link of a JST appendix passage that covers some of these
    verses of the KJV chapter, in passage and link order; covered lists those verses. A link may cross chapters, and
    a passage with several links covers only the verses under them. Similar and see-also links are not Compare."""
    out = []
    for c in store.db.select(
            "SELECT * FROM jst_passage_ref WHERE rel = 'compare' AND target_book_id = ? AND target_chapter <= ? "
            "AND COALESCE(target_chapter_end, target_chapter) >= ? ORDER BY passage_id, seq",
            (b["book_id"], chapter, chapter)):
        first, last = _link_span(c)
        covered = [v for v in verses if first <= (chapter, v) <= last]
        if covered:
            out.append((c["passage_id"], covered))
    return out


def _link_span(c: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    """The first and last KJV (chapter, verse) a jst_passage_ref link covers; no verse means the whole chapter."""
    return ((c["target_chapter"], c["target_verse_start"] or 0),
            (c["target_chapter_end"] or c["target_chapter"], c["target_verse_end"] or c["target_verse_start"] or _ALL))


def _moses_passage_ids(store: ScriptureStore) -> set[int]:
    """The passage_id(s) of the passage published as the Book of Moses, found by its JST range (MOSES_PASSAGE)."""
    return {r["passage_id"] for r in store.db.select(
        "SELECT p.passage_id FROM jst_passage p JOIN book b ON b.book_id = p.book_id WHERE b.name = ? "
        "AND p.chapter_start = ? AND p.verse_start = ? AND p.chapter_end = ? AND p.verse_end = ?", MOSES_PASSAGE)}


def _jst_passage(store: ScriptureStore, passage_id: int) -> Optional[tuple]:
    """(reference, text, rows) of an appendix passage: rows are its jst_verse rows in order. The reference is the
    passage's printed verse spec in cite form ("JST Gen. 9:10–15", "JST Matt. 4:1, 5–6, 8–9"); its text is its JST
    verses joined in order."""
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
    return reference, " ".join(j["text"] for j in rows), rows


def _citation_keys(store: ScriptureStore, b: dict, chapter: int, chapter_id: int, lo: int, hi: int,
                   by_verse: dict) -> tuple[dict, dict, dict]:
    """(keys, origin, via) for the core.db citations of these KJV verses. keys is {(flag, core BookID, chapter,
    verse): reference}: flag "" is an ordinary citation of the verse itself; flag "J" a JST citation of a JST verse
    that one of the verse's `jst` footnotes names, or of any JST verse of an appendix passage whose "Compare" range
    covers the verse (core.db numbers those in JST chapters and verses). The passage published as the Book of
    Moses (JST Gen. 1:1–8:18) is not followed: its text is the Book of Moses, so its talks would be listed against
    verses its JST text barely touches. For the verses its Compare link covers (Gen. 1:1–6:13), flag "" also names
    the Book of Moses verse each footnote ref on the verse links to (the `#pN` anchor of the ref's href, so "Moses
    6:21 (21–68)" is Moses 6:21 only); Moses refs on other verses are not followed. origin maps each key to the set
    of requested verse references it stands for. via maps each key reached only through passages or Moses refs to
    {(canonical sort key, reference)}: the passages, as _jst_passage prints them, and the Moses verses ("Moses 6:59")
    that found it."""
    keys, origin = {}, {}
    if b["core_book_id"] is not None:
        for v, row in by_verse.items():
            keys["", b["core_book_id"], chapter, v] = row["reference"]
            origin["", b["core_book_id"], chapter, v] = {row["reference"]}
    for r in store.db.select(
            "SELECT DISTINCT v.verse AS src, jv.core_book_id, jv.chapter, jv.verse FROM footnote_ref r "
            "JOIN footnote f ON f.footnote_id = r.footnote_id "
            f"JOIN jst_verse jv ON jv.jst_verse_id = r.target_jst_verse_id {_IN_RANGE} AND r.category = 'jst'",
            (chapter_id, lo, hi)):
        key = ("J", r["core_book_id"], r["chapter"], r["verse"])
        keys[key] = _jst_reference(r)
        origin.setdefault(key, set()).add(by_verse[r["src"]]["reference"])
    direct = set(keys)                          # the verses themselves and their `jst` footnote targets
    reached: dict[int, set[str]] = {}           # passage_id -> requested verse references its Compare links cover
    skipped: set[int] = set()                   # requested KJV verses covered by the Book of Moses passage
    moses_passage = _moses_passage_ids(store)
    for pid, covered in _compare_links(store, b, chapter, by_verse):
        if pid in moses_passage:
            skipped.update(covered)
        else:
            reached.setdefault(pid, set()).update(by_verse[v]["reference"] for v in covered)
    via: dict = {}                              # key -> {(canonical sort key, reference)}
    for pid, refs in reached.items():
        passage = _jst_passage(store, pid)
        if passage is None:
            continue
        order = _passage_order(store, passage[2][0], b)
        for r in passage[2]:
            key = ("J", r["core_book_id"], r["chapter"], r["verse"])
            keys.setdefault(key, _jst_reference(r))
            origin.setdefault(key, set()).update(refs)
            if key not in direct:
                via.setdefault(key, set()).add((order, passage[0]))
    # Why Moses: the passage skipped above prints no verses in the appendix; its text is published as the Book of
    # Moses (docs/scriptures/AUDIT.md). The footnotes' Moses refs on the verses its Compare link covers stand in
    # for it, matching each Genesis verse to the Moses verses it points to.
    moses = store.db.select("SELECT book_id, sort, cite_abbr, core_book_id FROM book WHERE name = 'Moses'")
    if skipped and moses and moses[0]["core_book_id"] is not None:
        m = moses[0]
        for r in store.db.select(
                "SELECT DISTINCT v.verse AS src, r.target_chapter, r.href FROM footnote_ref r "
                "JOIN footnote f ON f.footnote_id = r.footnote_id "
                f"{_IN_RANGE} AND r.target_book_id = ? AND r.target_chapter IS NOT NULL",
                (chapter_id, lo, hi, m["book_id"])):
            anchor = re.search(r"#p(\d+)$", r["href"] or "")
            if r["src"] not in skipped or not anchor:
                continue
            verse = int(anchor.group(1))
            key = ("", m["core_book_id"], r["target_chapter"], verse)
            reference = format_reference(m["cite_abbr"], r["target_chapter"], verse)
            keys.setdefault(key, reference)
            origin.setdefault(key, set()).add(by_verse[r["src"]]["reference"])
            if key not in direct:
                via.setdefault(key, set()).add(((m["sort"], r["target_chapter"], verse), reference))
    return keys, origin, via


def _passage_order(store: ScriptureStore, first_row: dict, kjv_book: dict) -> tuple:
    """Canonical sort key (book order, chapter, verse) of a JST appendix passage: under its KJV book, at its first
    JST verse. A JST book with no KJV book row sorts under the book requested."""
    book = store.db.scalar("SELECT sort FROM book WHERE book_id = ?",
                           (first_row["book_id"] or kjv_book["book_id"],), 0)
    return book, first_row["chapter"], first_row["verse"]


def _find_citing_talks(keys: dict, origin: dict, via: dict) -> tuple[dict, set]:
    """({TalkID: entry}, untitled TalkIDs) for the core.db citations matching `keys` (see _citation_keys). An entry is
    {talk_id ("talk_N"), title, date, cites (the references it cites), get_talk_available} plus "verses", the
    requested verse references it reaches. When every citation a talk matched is in `via` (reached only through
    appendix passages or Moses footnote refs), the entry also has "via": the references of those passages and Moses
    verses, in canonical order (book, chapter, first verse). Every titled talk is
    included, conference or not; get_talk serves only conference talks, so get_talk_available is true exactly for
    talks with a conference_talk row. Untitled talks (no title, no date) are only counted. A citation names its
    verses in citation_verse, so a range citation (John 3:14–16) matches each verse it names. Raises OSError,
    sqlite3.Error or SchemaError if core.db cannot be read."""
    by_chapter: dict[tuple, list[int]] = {}
    for flag, book_id, ch, v in keys:
        by_chapter.setdefault((flag, book_id, ch), []).append(v)
    talks: dict[int, dict] = {}
    cited: dict[int, set] = {}
    untitled: set[int] = set()
    for (flag, book_id, ch), verses in by_chapter.items():
        for r in sci_db.core_db.select(
                "SELECT DISTINCT c.TalkID, cv.Verse, t.Title, t.Date, "
                "EXISTS (SELECT 1 FROM conference_talk ct WHERE ct.TalkID = c.TalkID) AS conference "
                "FROM citation c JOIN citation_verse cv ON cv.CitationID = c.ID JOIN talk t ON t.ID = c.TalkID "
                f"WHERE c.BookID = ? AND c.Chapter = ? AND cv.Verse IN ({','.join('?' * len(verses))}) "
                f"AND IFNULL(c.Flag, '') {'=' if flag == 'J' else '!='} 'J'", (book_id, ch, *verses)):
            if not r["Title"]:
                untitled.add(r["TalkID"])
                continue
            key = (flag, book_id, ch, r["Verse"])
            t = talks.setdefault(r["TalkID"], {"talk_id": f"talk_{r['TalkID']}", "title": r["Title"],
                                               "date": r["Date"], "cites": [],
                                               "get_talk_available": bool(r["conference"]), "verses": set()})
            cited.setdefault(r["TalkID"], set()).add(key)
            t["verses"] |= origin[key]
    for talk_id, t in talks.items():
        t["cites"] = _merged_cites(cited[talk_id], keys)
        if cited[talk_id] <= via.keys():
            found = set().union(*(via[k] for k in cited[talk_id]))
            t["via"] = [ref for _, ref in sorted(found)]
    return talks, untitled - talks.keys()


def _merged_cites(cited: set, keys: dict) -> list[str]:
    """The references a talk cites, with consecutive verses of one book and chapter merged into a range ("John
    3:14–17", "JST Gen. 14:17–40"). This is intentional, to keep the response small: core.db stores each verse of a
    range citation separately, so unmerged a long range would list every verse. Standard and JST references are
    never merged together: the flag is part of the grouping, and JST verses are numbered in their own chapters."""
    out: list[str] = []
    run: list[tuple] = []
    for key in sorted(cited) + [None]:
        if run and key is not None and key[:3] == run[-1][:3] and key[3] == run[-1][3] + 1:
            run.append(key)
            continue
        if run:
            cite = keys[run[0]].rsplit(" ", 1)[0]       # "John 3:14" -> "John", "JST Gen. 8:13" -> "JST Gen."
            out.append(format_reference(cite, run[0][2], run[0][3], run[-1][3]))
        run = [key] if key is not None else []
    return out


def _attach_citing_counts(result, scope) -> None:
    """Set citing_talks_count (distinct titled talks across the verses), citing_talks_by_verse ([{reference, count}],
    when there is more than one verse) and untitled_talks_omitted (when any untitled citing talk was left out). The
    talks themselves come from get_citing_talks. If core.db cannot be read, the count is 0 and citing_talks_note
    says why; the verses are returned either way."""
    if not isinstance(result, dict):
        return
    refs, keys, origin, via = scope
    try:
        talks, untitled = _find_citing_talks(keys, origin, via)
    except (OSError, sqlite3.Error, sci_db.SchemaError) as exc:
        result["citing_talks_count"] = 0
        result["citing_talks_note"] = f"core.db citations are not available on this server ({type(exc).__name__})."
        return
    result["citing_talks_count"] = len(talks)
    if len(refs) > 1:
        result["citing_talks_by_verse"] = [{"reference": ref, "count": sum(ref in t["verses"] for t in talks.values())}
                                           for ref in refs]
    if untitled:
        result["untitled_talks_omitted"] = len(untitled)


MAX_CITING_PAGE = 100


def get_citing_talks(store: ScriptureStore, book: str, chapter: int, verse_start: Optional[int] = None,
                     verse_end: Optional[int] = None, limit: int = 25, offset: int = 0,
                     conference_only: bool = False, order: str = "newest"):
    """One page of the talks citing these verses: {reference, total, offset, limit, next_offset (None on the last
    page), citing_talks: [{talk_id, title, date, cites, get_talk_available, via?}]}, newest first (or oldest first
    with order="oldest"). Matching is get_verse's (KJV and JST input, `jst` footnote links, untitled talks left out
    and counted in untitled_talks_omitted when any). For a KJV verse it also follows the JST appendix passages whose
    "Compare" range covers the verse, whatever its size, except JST Gen. 1:1–8:18, whose text is published as the
    Book of Moses, and its Compare range goes through the Moses footnotes instead: for the verses that passage's
    Compare link covers (Gen. 1:1–6:13), it follows each footnote ref on the verse into the Book of Moses, to the
    verse the ref links to ("Moses 6:21 (21–68)" is Moses 6:21 only); a non-JST citation of that Moses verse
    counts for the Genesis verse, and the talk's cites show the Moses verse. Moses refs on other verses (Gen. 9:1)
    are not followed; input "Moses" itself is unchanged. A talk found only through such passages or Moses refs (none of its
    matched citations is of a requested verse itself or of a `jst` footnote's JST verse) has "via": the references of
    the passages and Moses verses that found it ("JST Gen. 14:25–40", "Moses 6:59"), one entry per Moses
    verse, in canonical order (book, then chapter, then first verse: "JST Gen. 9:10–15" before "JST Gen. 14:25–40",
    "Moses 3:7" before "Moses 3:17"); other talks have no "via". conference_only keeps the talks with
    get_talk_available=true; total counts the talks after that filter. limit is capped at 100. A talk's cites merge
    consecutive verses of one book and chapter into a range ("John 3:14–17"; JST references stay separate from
    standard ones); this is intentional, to keep the response small, since core.db stores each verse of a range
    separately."""
    if (order or "").lower() not in ("newest", "oldest"):
        return f'order must be "newest" or "oldest", not {order!r}.'
    result, scope = _read_verses(store, book, chapter, verse_start, verse_end, False, False, "standard", True)
    if not isinstance(result, dict):
        return result
    limit = max(1, min(int(limit), MAX_CITING_PAGE))
    offset = max(0, int(offset))
    page = {"reference": result["reference"], "total": 0, "offset": offset, "limit": limit, "next_offset": None,
            "citing_talks": []}
    if scope is None:
        return page
    try:
        talks, untitled = _find_citing_talks(*scope[1:])
    except (OSError, sqlite3.Error, sci_db.SchemaError) as exc:
        page["citing_talks_note"] = f"core.db citations are not available on this server ({type(exc).__name__})."
        return page
    entries = [{k: v for k, v in t.items() if k != "verses"} for _, t in sorted(talks.items())]
    if conference_only:
        entries = [t for t in entries if t["get_talk_available"]]
    entries.sort(key=lambda t: (t["date"] or "", int(t["talk_id"][5:])), reverse=order.lower() == "newest")
    page["total"] = len(entries)
    page["citing_talks"] = entries[offset:offset + limit]
    if offset + limit < len(entries):
        page["next_offset"] = offset + limit
    if untitled:
        page["untitled_talks_omitted"] = len(untitled)
    return page


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
# find_cross_references
# ---------------------------------------------------------------------------

def find_cross_references(store: ScriptureStore, book: str, chapter: int, verse: int):
    """One hop of the verse graph, from scripture.db alone.

    `outgoing`: the verse's footnotes that point at scripture, each with its marker, context, text and the targets
    it names (study-help links are left out). A JST range is listed one target per JST verse ("JST Rom. 7:5", ...);
    a page that is not a chapter (a facsimile, a book's front matter) has its page URI as target. `incoming`: the
    other verses whose footnotes point at this verse, one entry per source verse with the footnotes that do so. A
    ref to a verse range covers every verse in it; a ref to a whole chapter covers every verse of the chapter, and
    its footnote is marked `whole_chapter: true`.
    """
    found = store.resolver.resolve(book)
    if found is None:
        return _unknown_book(book)
    b, jst = found
    if jst:
        return "find_cross_references covers the standard works' verses, not the JST numbering."
    ch = _chapter(store, b, chapter)
    if ch is None:
        return _no_chapter(b, chapter)
    verse_id = store.db.scalar("SELECT verse_id FROM verse WHERE chapter_id = ? AND verse = ?",
                               (ch["chapter_id"], verse), None)
    if verse_id is None:
        return f"No verse {verse} in {format_reference(b['cite_abbr'], chapter)}."

    outgoing: dict[int, dict] = {}
    for r in store.db.select(
            "SELECT f.marker, f.context, f.text, r.*, jv.verse AS jst_verse, jv.chapter AS jst_chapter, "
            "jv.core_book_id AS jst_core_book_id FROM footnote f JOIN footnote_ref r ON r.footnote_id = f.footnote_id "
            "LEFT JOIN jst_verse jv ON jv.jst_verse_id = r.target_jst_verse_id "
            "WHERE f.verse_id = ? AND r.target_help IS NULL "
            "AND (r.target_uri IS NOT NULL OR r.target_chapter IS NOT NULL OR r.target_jst_verse_id IS NOT NULL) "
            "ORDER BY f.footnote_id, r.seq", (verse_id,)):
        note = outgoing.setdefault(r["footnote_id"], {"marker": r["marker"], "context": r["context"],
                                                      "text": r["text"], "targets": []})
        note["targets"].append({"category": r["category"], "label": r["label"], "target": _ref_target(store, r)})

    incoming: dict[int, dict] = {}
    for r in store.db.select(
            "SELECT sv.verse_id, sv.chapter, sv.verse, sb.cite_abbr, f.footnote_id, f.marker, f.context, f.text, "
            "MIN(r.target_verse_start IS NULL) AS whole_chapter "
            "FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
            "JOIN verse sv ON sv.verse_id = f.verse_id JOIN book sb ON sb.book_id = sv.book_id "
            "WHERE r.target_book_id = ? AND r.target_chapter = ? AND r.target_help IS NULL "
            "AND (r.target_verse_start IS NULL "
            "OR (r.target_verse_start <= ? AND COALESCE(r.target_verse_end, r.target_verse_start) >= ?)) "
            "AND sv.verse_id != ? GROUP BY f.footnote_id ORDER BY sb.sort, sv.chapter, sv.verse, f.footnote_id",
            (b["book_id"], chapter, verse, verse, verse_id)):
        source = incoming.setdefault(r["verse_id"], {
            "reference": format_reference(r["cite_abbr"], r["chapter"], r["verse"]), "footnotes": []})
        note = {"marker": r["marker"], "context": r["context"], "text": r["text"]}
        if r["whole_chapter"]:
            note["whole_chapter"] = True        # the footnote names the chapter, not this verse
        source["footnotes"].append(note)

    return {"reference": format_reference(b["cite_abbr"], chapter, verse),
            "outgoing": list(outgoing.values()), "incoming": list(incoming.values())}


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
