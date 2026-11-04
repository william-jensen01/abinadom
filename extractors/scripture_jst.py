"""The JST (Joseph Smith Translation) import and its links to the KJV (SPEC-v2 §5, phase 3).

Three jobs, all run by `scripts/build_scriptures.py` inside its one transaction:

1. `read_core_jst` / `import_jst_verses`: every core.db `Flag IN ('J','F')` row goes into `jst_verse`, in JST
   chapter/verse numbering, text decoded and otherwise unchanged. core.db is read only through `db.Database`.
2. `resolve_footnote_refs`: the Church's `jst`-category footnotes name a JST verse. A footnote with a link
   (`/scriptures/jst/jst-gen/9?id=p4-p6`) names it through the href; one without (KJV Gen 6:6 -> "JST Gen. 8:13 …")
   names it only in its text, which is parsed here ("JST Gen. 8:13", "JST Gen. 8:23–24", the abbreviation is
   core.db's `CiteAbbr`). Each ref is resolved to `jst_verse` by (book, chapter, verse); a range is expanded to
   one `footnote_ref` row per JST verse (the I4 rule). A ref that finds no `jst_verse` keeps a NULL target and
   is reported.
3. `parse_appendix` / `store_passages`: the JST appendix pages (`/scriptures/jst/jst-gen/9`) hold passages, one
   `<section>` each with a heading "JST, Genesis 9:4–6. Compare <a>Genesis 8:20–22</a>". Each becomes a
   `jst_passage` row, linked to its KJV range through its "Compare" links (`jst_passage_ref`). Appendix verses
   are never `verse` rows, and passages never become `footnote_ref` rows (GOAL.md overrides spec §5.2.2).

The parsing functions are pure; the `*_rows`/`store_*`/`resolve_*` functions take a sqlite3 connection.
"""
import html as _html
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from bs4 import NavigableString, Tag

from config.scripture_books import BOOK_CROSSWALK
from extractors import scripture_page as sp

JST_FLAGS = ("J", "F")
# volumes whose books have a JST (core.db has no JST for the Song of Solomon)
JST_VOLUMES = ("ot", "nt")


# ---------------------------------------------------------------------------
# book lookups (static crosswalk: no core.db read is needed to name a book)
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _book_maps() -> Tuple[Dict[str, int], Dict[str, int]]:
    """(cite abbreviation -> core BookID, URI segment -> core BookID) for the OT and NT books."""
    by_cite, by_seg = {}, {}
    for (vol, seg), (_abbr, cite, core_id) in BOOK_CROSSWALK.items():
        if vol not in JST_VOLUMES or core_id is None:
            continue
        by_cite[_norm(cite)] = core_id
        by_seg[seg] = core_id
    return by_cite, by_seg


_BY_CITE, _BY_SEG = _book_maps()


def core_book_for_jst_uri(uri: str) -> Optional[int]:
    """core.db BookID for an appendix URI: `/scriptures/jst/jst-gen/9` -> Genesis (101)."""
    segs = sp.uri_segments(uri)
    if len(segs) < 2 or segs[0] != sp.JST_VOLUME or not segs[1].startswith("jst-"):
        return None
    return _BY_SEG.get(segs[1][len("jst-"):])


# ---------------------------------------------------------------------------
# the text of a hrefless `jst` footnote
# ---------------------------------------------------------------------------

# "JST Gen. 8:13 And it repented …", "JST 1 Cor. 14:34 … rule …", "JST Matt. 18:8–9 …", "JST Ex. 4:21 (Appendix)"
_JST_NOTE = re.compile(
    r"^JST\s+((?:\d\s+)?[A-Z][A-Za-z]*\.?)\s+(\d+):(\d+)(?:\s*[–—-]\s*(\d+))?(?!\d)")


@dataclass
class JstNoteTarget:
    cite_abbr: str
    chapter: int
    verse_start: int
    verse_end: int
    core_book_id: Optional[int]


def parse_jst_note(text: str) -> Optional[JstNoteTarget]:
    """The JST verse(s) a `jst` footnote's text names, from its leading "JST <book> <chapter>:<verse>[–<verse>]".

    Only the leading reference counts: the rest is the abbreviated JST text or a remark ("JST Matt. 5:24 and
    3 Ne. 12:22 omit …", "(Note: … in vv. 4, 13 …)"). None when the text does not start with such a reference.
    """
    m = _JST_NOTE.match(_norm(_html.unescape(text)))
    if not m:
        return None
    cite = m.group(1)
    start = int(m.group(3))
    end = int(m.group(4)) if m.group(4) else start
    if end < start:
        return None
    core = _BY_CITE.get(cite)
    if core is None and not cite.endswith("."):
        core = _BY_CITE.get(cite + ".")
    return JstNoteTarget(cite, int(m.group(2)), start, end, core)


# ---------------------------------------------------------------------------
# JST appendix pages
# ---------------------------------------------------------------------------

@dataclass
class PassageRef:
    seq: int
    rel: str                       # compare | similar | see-also
    href: str
    label: str
    target_uri: Optional[str]
    book_uri: Optional[str]
    chapter: Optional[int]
    chapter_end: Optional[int]
    verse_start: Optional[int]
    verse_end: Optional[int]


@dataclass
class Passage:
    seq: int
    section_id: Optional[str]
    anchor_aid: Optional[str]
    title: str                                   # "JST, Genesis 9:4–6."
    verse_spec: Optional[str]                    # "9:4–6"
    ranges: List[Tuple[int, int, int, int]]      # (chapter, verse, chapter_end, verse_end) in JST numbering
    intro: Optional[str]
    verse_numbers: List[Tuple[int, int]]         # (chapter, verse) of the <p class="verse"> paragraphs, page chapter
    refs: List[PassageRef] = field(default_factory=list)


_SPEC_START = re.compile(r"\d+:\d+")
_TOKEN_FULL = re.compile(r"^(\d+):(\d+)(?:\s*[–—-]\s*(?:(\d+):(\d+)|(\d+)))?$")
_TOKEN_VERSE = re.compile(r"^(\d+)(?:\s*[–—-]\s*(\d+))?$")


def parse_verse_spec(spec: str) -> Optional[List[Tuple[int, int, int, int]]]:
    """"9:4–6" -> [(9,4,9,6)]; "4:1, 5–6, 8–9" -> [(4,1,4,1),(4,5,4,6),(4,8,4,9)]; "1:1–8:18" -> [(1,1,8,18)].

    A bare number after a comma continues the previous chapter. None when a token does not parse.
    """
    out: List[Tuple[int, int, int, int]] = []
    chapter = None
    for token in _norm(spec).rstrip(".").split(","):
        token = token.strip()
        m = _TOKEN_FULL.match(token)
        if m:
            chapter = int(m.group(1))
            v1 = int(m.group(2))
            if m.group(3):
                out.append((chapter, v1, int(m.group(3)), int(m.group(4))))
                chapter = int(m.group(3))
            else:
                out.append((chapter, v1, chapter, int(m.group(5)) if m.group(5) else v1))
            continue
        m = _TOKEN_VERSE.match(token)
        if m and chapter is not None:
            v1 = int(m.group(1))
            out.append((chapter, v1, chapter, int(m.group(2)) if m.group(2) else v1))
            continue
        return None
    for c1, v1, c2, v2 in out:
        if (c2, v2) < (c1, v1):
            return None
    return out or None


def _parse_span(value: str) -> Optional[Tuple[int, int, int, int]]:
    """href `span=1:1-6:13` -> (1, 1, 6, 13)."""
    m = re.match(r"^(\d+):(\d+)-(\d+):(\d+)$", value or "")
    return tuple(int(x) for x in m.groups()) if m else None


def _heading_refs(h2: Tag) -> List[PassageRef]:
    """The links of a heading. Those after "Compare" and before "similar changes were made …" / "see also"
    are the KJV range ("compare"); the later ones are stored with their own `rel`."""
    refs: List[PassageRef] = []
    rel = "compare"
    seq = 0
    for node in h2.descendants:
        if isinstance(node, NavigableString):
            if node.parent is not None and node.parent.name == "a":
                continue
            low = str(node).lower()
            if "similar change" in low:
                rel = "similar"
            elif "see also" in low:
                rel = "see-also"
            elif "compare" in low:
                rel = "compare"
            continue
        if not (isinstance(node, Tag) and node.name == "a" and node.get("href")):
            continue
        href = _html.unescape(node["href"])
        label = sp.plain_text(node)
        target = sp.resolve_href(href)
        parts = urlsplit(href)
        span = _parse_span((parse_qs(parts.query).get("span") or [""])[0])
        if span:
            ranges = [(span[1], span[3])]
            chapter_end = span[2]
            chapter = span[0]
        else:
            ranges = target.verse_ranges
            chapter, chapter_end = target.chapter, None
        for start, end in ranges:
            refs.append(PassageRef(seq, rel, href, label, target.target_uri, target.book_uri, chapter,
                                   chapter_end, start, end))
            seq += 1
    return refs


def parse_appendix(uri: str, data: dict) -> List[Passage]:
    """The passages of one JST appendix page (`type/content` JSON), in page order.

    A passage is a `<section>` whose header holds an `<h2>` "<strong>JST, Genesis 9:4–6.</strong> Compare …".
    Nested sections (sub-parts with their own study-intro) belong to the passage. Pages without such a
    heading (the introduction, `_contents` pages) have no passages.
    """
    body = ((data.get("content") or {}).get("body")) or ""
    soup = sp._soup(body)
    page_chapter_m = re.search(r"/(\d+)$", uri)
    page_chapter = int(page_chapter_m.group(1)) if page_chapter_m else None
    passages: List[Passage] = []
    for h2 in soup.find_all("h2"):
        strong = h2.find("strong")
        title = sp.plain_text(strong) if strong is not None else ""
        if not title.startswith("JST,"):
            continue
        section = h2.find_parent("section")
        m = _SPEC_START.search(title)
        spec = title[m.start():].rstrip(". ").strip() if m else None
        ranges = parse_verse_spec(spec) if spec else None
        intro = None
        if section is not None:
            for p in section.find_all("p"):
                if sp._has_class(p, "study-intro"):
                    intro = sp.plain_text(p)
                    break
        verse_numbers = []
        if section is not None:
            for p in section.find_all("p"):
                if sp._has_class(p, "verse"):
                    vm = re.match(r"^p(\d+)$", p.get("id") or "")
                    if vm:
                        verse_numbers.append((page_chapter or 0, int(vm.group(1))))
        passages.append(Passage(
            seq=len(passages), section_id=(section.get("id") if section is not None else None),
            anchor_aid=h2.get("data-aid"), title=title, verse_spec=spec, ranges=ranges or [], intro=intro,
            verse_numbers=verse_numbers, refs=_heading_refs(h2)))
    return passages


# ---------------------------------------------------------------------------
# core.db -> jst_verse
# ---------------------------------------------------------------------------

def read_core_jst(core_db_path: Optional[str] = None) -> List[dict]:
    """Every core.db J/F row as {ID, BookID, Chapter, Verse, Flag, Text}, ordered by ID. Read-only, through db.Database."""
    import os
    from db import CORE_DB_PATH, Database
    path = core_db_path or CORE_DB_PATH
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise FileNotFoundError(
            f"PREREQUISITE: {path} is missing or empty; build it first "
            f"(`pipenv run python scripts/build.py --version 55`)")
    db = Database(path, timeout=120)
    try:
        return db.select("SELECT ID, BookID, Chapter, Verse, Flag, Text FROM scripture "
                         "WHERE Flag IN ('J','F') ORDER BY ID")
    finally:
        db.close()


def _decode(text) -> str:
    if text is None:
        return ""
    return text.decode("utf-8") if isinstance(text, (bytes, bytearray)) else str(text)


def import_jst_verses(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    """Insert the J/F rows into `jst_verse` (JST numbering, text unchanged). Returns the row count."""
    book_of = {core: bid for core, bid in conn.execute(
        "SELECT core_book_id, book_id FROM book WHERE core_book_id IS NOT NULL")}
    batch = [(r["ID"], book_of.get(r["BookID"]), r["Chapter"], r["Verse"], r["Flag"], _decode(r["Text"]))
             for r in rows]
    conn.executemany("INSERT INTO jst_verse (core_id, book_id, chapter, verse, source_flag, text) "
                     "VALUES (?,?,?,?,?,?)", batch)
    return len(batch)


class JstIndex:
    """(core BookID, JST chapter, JST verse) -> jst_verse_id, built from the stored jst_verse rows and the
    core ID -> BookID of the imported rows."""

    def __init__(self, conn: sqlite3.Connection, rows: Iterable[dict]):
        core_book = {r["ID"]: r["BookID"] for r in rows}
        self.ids: Dict[Tuple[int, int, int], int] = {}
        self.by_book: Dict[int, List[Tuple[int, int, int]]] = {}
        for jid, core_id, chapter, verse in conn.execute(
                "SELECT jst_verse_id, core_id, chapter, verse FROM jst_verse ORDER BY jst_verse_id"):
            book = core_book[core_id]
            self.ids[(book, chapter, verse)] = jid
            self.by_book.setdefault(book, []).append((chapter, verse, jid))
        for lst in self.by_book.values():
            lst.sort()

    def get(self, core_book: Optional[int], chapter, verse) -> Optional[int]:
        if core_book is None or chapter is None or verse is None:
            return None
        return self.ids.get((core_book, chapter, verse))

    def between(self, core_book: int, start: Tuple[int, int], end: Tuple[int, int]) -> List[int]:
        return [jid for c, v, jid in self.by_book.get(core_book, []) if start <= (c, v) <= end]


# ---------------------------------------------------------------------------
# footnote_ref resolution
# ---------------------------------------------------------------------------

def resolve_footnote_refs(conn: sqlite3.Connection, index: JstIndex) -> dict:
    """Point every `jst` footnote_ref at its `jst_verse`. Returns counts and the unresolved list.

    - href rows (`/scriptures/jst/jst-gen/9`, already one row per verse): looked up by (book, chapter, verse).
    - text rows (`ref_type='jst-note'`): the label is parsed (`parse_jst_note`); a range becomes one row per
      JST verse, with the footnote's refs renumbered from 0. `target_book_id` stays NULL on every `jst` row: its
      chapter and verse are JST numbers, and must not match a KJV verse by (book, chapter, verse).
    """
    stats = {"href": 0, "text": 0, "expanded_from": 0, "unresolved": []}

    # href rows
    for fid, seq, uri, chapter, verse, label in conn.execute(
            "SELECT footnote_id, seq, target_uri, target_chapter, target_verse_start, label FROM footnote_ref "
            "WHERE category = 'jst' AND ref_type = 'scripture-ref' ORDER BY footnote_id, seq").fetchall():
        stats["href"] += 1
        jid = index.get(core_book_for_jst_uri(uri or ""), chapter, verse)
        if jid is None:
            stats["unresolved"].append(label)
            continue
        conn.execute("UPDATE footnote_ref SET target_jst_verse_id = ? WHERE footnote_id = ? AND seq = ?",
                     (jid, fid, seq))

    # text rows: rebuild the refs of each footnote that has one
    cols = [r[1] for r in conn.execute("PRAGMA table_info(footnote_ref)")]
    fids = [r[0] for r in conn.execute(
        "SELECT DISTINCT footnote_id FROM footnote_ref WHERE ref_type = 'jst-note' ORDER BY footnote_id")]
    insert = f"INSERT INTO footnote_ref ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    for fid in fids:
        old = [dict(zip(cols, r)) for r in conn.execute(
            "SELECT * FROM footnote_ref WHERE footnote_id = ? ORDER BY seq", (fid,))]
        new = []
        for row in old:
            if row["ref_type"] != "jst-note":
                new.append(row)
                continue
            stats["text"] += 1
            t = parse_jst_note(row["label"])
            if t is None or t.core_book_id is None:
                stats["unresolved"].append(row["label"])
                new.append(row)
                continue
            if t.verse_end > t.verse_start:
                stats["expanded_from"] += 1
            for v in range(t.verse_start, t.verse_end + 1):
                jid = index.get(t.core_book_id, t.chapter, v)
                if jid is None:
                    stats["unresolved"].append(row["label"])
                new.append(dict(row, target_chapter=t.chapter, target_verse_start=v, target_verse_end=v,
                                target_jst_verse_id=jid))
        conn.execute("DELETE FROM footnote_ref WHERE footnote_id = ?", (fid,))
        for seq, row in enumerate(new):
            row["seq"] = seq
            conn.execute(insert, [row[c] for c in cols])
    return stats


# ---------------------------------------------------------------------------
# appendix passages -> jst_passage
# ---------------------------------------------------------------------------

def store_passages(conn: sqlite3.Connection, index: JstIndex, pages: Iterable[Tuple[str, int, dict]]) -> dict:
    """Parse and store the passages of the appendix pages given as (uri, page_id, JSON). Returns counts and findings."""
    book_ids = {uri: bid for uri, bid in conn.execute("SELECT uri, book_id FROM book")}
    book_of = {core: bid for core, bid in conn.execute(
        "SELECT core_book_id, book_id FROM book WHERE core_book_id IS NOT NULL")}
    stats = {"passages": 0, "refs": 0, "compare": 0, "verses": 0, "bad_title": [], "paragraph_mismatch": [],
             "missing_verses": [], "no_compare": []}
    for uri, page_id, data in pages:
        core_book = core_book_for_jst_uri(uri)
        for p in parse_appendix(uri, data):
            where = f"{uri} #{p.seq + 1} ({p.title})"
            if not p.ranges or core_book is None:
                stats["bad_title"].append(where)
            first = p.ranges[0] if p.ranges else (None,) * 4
            last = p.ranges[-1] if p.ranges else (None,) * 4
            cur = conn.execute(
                "INSERT INTO jst_passage (page_id, seq, section_id, anchor_aid, title, verse_spec, book_id, "
                "core_book_id, chapter_start, verse_start, chapter_end, verse_end, intro) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (page_id, p.seq, p.section_id, p.anchor_aid, p.title, p.verse_spec, book_of.get(core_book),
                 core_book, first[0], first[1], last[2], last[3], p.intro))
            pid = cur.lastrowid
            stats["passages"] += 1

            ids, wanted = [], []
            for c1, v1, c2, v2 in p.ranges if core_book is not None else []:
                got = index.between(core_book, (c1, v1), (c2, v2))
                ids += got
                if c1 == c2:
                    wanted += [(c1, v) for v in range(v1, v2 + 1)]
            for jid in dict.fromkeys(ids):
                conn.execute("INSERT INTO jst_passage_verse (passage_id, jst_verse_id) VALUES (?,?)", (pid, jid))
                stats["verses"] += 1
            if any(index.get(core_book, c, v) is None for c, v in wanted):
                stats["missing_verses"].append(where)
            if p.verse_numbers and wanted and sorted(v for _, v in p.verse_numbers) != sorted({v for _, v in wanted}):
                stats["paragraph_mismatch"].append(where)

            if not any(r.rel == "compare" for r in p.refs):
                stats["no_compare"].append(where)
            for r in p.refs:
                conn.execute(
                    "INSERT INTO jst_passage_ref (passage_id, seq, rel, href, label, target_uri, target_book_id, "
                    "target_chapter, target_chapter_end, target_verse_start, target_verse_end) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, r.seq, r.rel, r.href, r.label, r.target_uri, book_ids.get(r.book_uri) if r.book_uri else None,
                     r.chapter, r.chapter_end, r.verse_start, r.verse_end))
                stats["refs"] += 1
                stats["compare"] += r.rel == "compare"
    return stats
