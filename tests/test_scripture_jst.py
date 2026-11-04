"""Tests for extractors/scripture_jst.py: footnote text parsing, appendix passages, and ref resolution.

Pure parsing runs on a recorded appendix page; resolution runs on an in-memory sqlite with a tiny jst_verse.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from extractors import scripture_jst as jst

FIXTURES = Path(__file__).parent / "fixtures" / "scriptures"
GEN, EX, MATT = 101, 102, 140


@pytest.mark.parametrize("text,expect", [
    ("JST Gen. 8:13 And it repented Noah …", ("Gen.", 8, 13, 13, GEN)),
    ("JST Gen. 8:23–24 …", ("Gen.", 8, 23, 24, GEN)),
    ("JST Ex. 7:3 … harden …", ("Ex.", 7, 3, 3, EX)),
    ("JST Gen. 9:4–6 (Appendix).", ("Gen.", 9, 4, 6, GEN)),
    ("JST Matt. 5:24 and 3 Ne. 12:22 omit the words “without a cause.”", ("Matt.", 5, 24, 24, MATT)),
    ("JST 1 Cor. 14:2 … another tongue … (Note: JST uses “another” in vv. 4, 13.)", ("1 Cor.", 14, 2, 2, None)),
])
def test_parse_jst_note(text, expect):
    t = jst.parse_jst_note(text)
    cite, chapter, v1, v2, core = expect
    assert (t.cite_abbr, t.chapter, t.verse_start, t.verse_end) == (cite, chapter, v1, v2)
    if core:
        assert t.core_book_id == core


@pytest.mark.parametrize("text", ["JST entitles this book …", "JS—M 1:4 adds …", "Compare JST Gen. 8:13", ""])
def test_parse_jst_note_rejects_text_without_a_leading_reference(text):
    assert jst.parse_jst_note(text) is None


@pytest.mark.parametrize("spec,expect", [
    ("9:4–6", [(9, 4, 9, 6)]),
    ("14:25–40.", [(14, 25, 14, 40)]),
    ("4:1, 5–6, 8–9", [(4, 1, 4, 1), (4, 5, 4, 6), (4, 8, 4, 9)]),
    ("19:15, 21", [(19, 15, 19, 15), (19, 21, 19, 21)]),
    ("1:1–8:18", [(1, 1, 8, 18)]),
    ("7:1, 5", [(7, 1, 7, 1), (7, 5, 7, 5)]),
])
def test_parse_verse_spec(spec, expect):
    assert jst.parse_verse_spec(spec) == expect


@pytest.mark.parametrize("spec", ["", "x", "9:6–4", "9:4, y"])
def test_parse_verse_spec_rejects(spec):
    assert jst.parse_verse_spec(spec) is None


def test_core_book_for_jst_uri():
    assert jst.core_book_for_jst_uri("/scriptures/jst/jst-gen/9") == GEN
    assert jst.core_book_for_jst_uri("/scriptures/jst/jst-1-cor/7") is not None
    assert jst.core_book_for_jst_uri("/scriptures/ot/gen/9") is None
    assert jst.core_book_for_jst_uri("/scriptures/jst/introduction") is None


def _page(uri):
    return json.loads((FIXTURES / (uri.strip("/").replace("/", "__") + ".json")).read_text())


def test_parse_appendix_passages_and_compare_links():
    ps = jst.parse_appendix("/scriptures/jst/jst-gen/9", _page("/scriptures/jst/jst-gen/9"))
    assert [p.verse_spec for p in ps][:2] == ["9:4–6", "9:10–15"]
    first = ps[0]
    assert first.title == "JST, Genesis 9:4–6." and first.ranges == [(9, 4, 9, 6)]
    assert [v for _, v in first.verse_numbers] == [4, 5, 6]
    assert [(r.rel, r.book_uri, r.chapter, r.verse_start, r.verse_end) for r in first.refs] == [
        ("compare", "/scriptures/ot/gen", 8, 20, 22)]


def _heading(inner):
    body = ('<section id="s"><header><h2 data-aid="1"><strong>JST, Genesis 9:4–6.</strong> '
            f'{inner}</h2></header><p class="verse" id="p4"><span class="verse-number">4 </span>x</p></section>')
    return {"content": {"body": body}}


def test_heading_links_are_split_by_relation():
    inner = ('Compare <a href="/study/scriptures/ot/ex/7?lang=eng&amp;id=p3%2Cp13#p3">7:3, 13</a>; '
             '<a href="/study/scriptures/ot/ex/9?lang=eng&amp;id=p12#p12">9:12</a>; similar changes were made in '
             '<a href="/study/scriptures/nt/luke/4?lang=eng&amp;id=p2#p2">Luke 4:2</a>; see also '
             '<a href="/study/scriptures/jst/jst-luke/12?lang=eng&amp;id=p9-p12#p9">JST, Luke 12:9–12</a>')
    (p,) = jst.parse_appendix("/scriptures/jst/jst-gen/9", _heading(inner))
    assert [(r.rel, r.chapter, r.verse_start) for r in p.refs] == [
        ("compare", 7, 3), ("compare", 7, 13), ("compare", 9, 12), ("similar", 4, 2), ("see-also", 12, 9)]


def test_span_href_crossing_chapters():
    inner = 'Compare <a href="/study/scriptures/ot/gen/1?lang=eng&amp;span=1%3A1-6%3A13#p1">Genesis 1:1–6:13</a>'
    (p,) = jst.parse_appendix("/scriptures/jst/jst-gen/1-8", _heading(inner))
    (r,) = p.refs
    assert (r.chapter, r.chapter_end, r.verse_start, r.verse_end) == (1, 6, 1, 13)


def test_page_without_passages():
    assert jst.parse_appendix("/scriptures/jst/introduction", {"content": {"body": "<p>Following are</p>"}}) == []


# -- resolution against a small jst_verse ------------------------------------

SCHEMA = """
CREATE TABLE book (book_id INTEGER PRIMARY KEY, uri TEXT, core_book_id INTEGER);
CREATE TABLE jst_verse (jst_verse_id INTEGER PRIMARY KEY, core_id INTEGER, book_id INTEGER, chapter INTEGER,
                        verse INTEGER, source_flag TEXT, text TEXT);
CREATE TABLE footnote_ref (footnote_id INTEGER, seq INTEGER, category TEXT, ref_type TEXT, href TEXT, label TEXT,
  target_uri TEXT, target_book_id INTEGER, target_chapter INTEGER, target_verse_start INTEGER,
  target_verse_end INTEGER, target_help TEXT, target_jst_verse_id INTEGER, PRIMARY KEY (footnote_id, seq));
"""
CORE = [  # core.db rows: Gen 8:13, 8:23, 8:24 (JST) and Ex 7:3
    {"ID": 10, "BookID": GEN, "Chapter": 8, "Verse": 13, "Flag": "F", "Text": "a".encode()},
    {"ID": 11, "BookID": GEN, "Chapter": 8, "Verse": 23, "Flag": "F", "Text": "b".encode()},
    {"ID": 12, "BookID": GEN, "Chapter": 8, "Verse": 24, "Flag": "F", "Text": "c".encode()},
    {"ID": 13, "BookID": EX, "Chapter": 7, "Verse": 3, "Flag": "F", "Text": "d".encode()},
    {"ID": 14, "BookID": GEN, "Chapter": 9, "Verse": 10, "Flag": "F", "Text": "e".encode()},
]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    c.execute("INSERT INTO book VALUES (1, '/scriptures/ot/gen', ?)", (GEN,))
    jst.import_jst_verses(c, CORE)
    return c


def _ref(c, fid, seq, ref_type, label, href=None, uri=None, chapter=None, verse=None):
    c.execute("INSERT INTO footnote_ref (footnote_id, seq, category, ref_type, href, label, target_uri, "
              "target_chapter, target_verse_start, target_verse_end) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (fid, seq, "jst", ref_type, href, label, uri, chapter, verse, verse))


def test_import_keeps_numbering_and_text(conn):
    rows = conn.execute("SELECT core_id, book_id, chapter, verse, source_flag, text FROM jst_verse ORDER BY core_id").fetchall()
    assert rows[0] == (10, 1, 8, 13, "F", "a")
    assert rows[3][1] is None          # Exodus has no book row here


def test_text_refs_resolve_and_ranges_expand(conn):
    conn.execute("INSERT INTO footnote_ref (footnote_id, seq, category, ref_type, label) VALUES (1,0,'cross-ref','scripture-ref','keep')")
    _ref(conn, 1, 1, "jst-note", "JST Gen. 8:13 And it repented …")
    _ref(conn, 2, 0, "jst-note", "JST Gen. 8:23–24 …")
    _ref(conn, 3, 0, "jst-note", "JST Gen. 8:99 …")
    index = jst.JstIndex(conn, CORE)
    stats = jst.resolve_footnote_refs(conn, index)
    got = {fid: [(s, cat, c, v, t) for s, cat, c, v, t in conn.execute(
        "SELECT seq, category, target_chapter, target_verse_start, target_jst_verse_id FROM footnote_ref "
        "WHERE footnote_id = ? ORDER BY seq", (fid,))] for fid in (1, 2, 3)}
    assert got[1] == [(0, "cross-ref", None, None, None), (1, "jst", 8, 13, 1)]
    assert got[2] == [(0, "jst", 8, 23, 2), (1, "jst", 8, 24, 3)]
    assert got[3] == [(0, "jst", 8, 99, None)]
    assert stats["unresolved"] == ["JST Gen. 8:99 …"]
    assert conn.execute("SELECT COUNT(*) FROM footnote_ref WHERE target_book_id IS NOT NULL").fetchone()[0] == 0


def test_href_refs_resolve_by_book_chapter_verse(conn):
    _ref(conn, 1, 0, "scripture-ref", "JST Ex. 7:3", href="h", uri="/scriptures/jst/jst-ex/7", chapter=7, verse=3)
    _ref(conn, 1, 1, "scripture-ref", "JST Gen. 9:10–15", href="h", uri="/scriptures/jst/jst-gen/9", chapter=9, verse=10)
    _ref(conn, 1, 2, "scripture-ref", "JST Gen. 9:11", href="h", uri="/scriptures/jst/jst-gen/9", chapter=9, verse=11)
    stats = jst.resolve_footnote_refs(conn, jst.JstIndex(conn, CORE))
    ids = [r[0] for r in conn.execute("SELECT target_jst_verse_id FROM footnote_ref ORDER BY seq")]
    assert ids == [4, 5, None] and stats["unresolved"] == ["JST Gen. 9:11"]
