"""Golden-file tests for extractors/scripture_page.py (pure parsing, no database, no network).

Fixtures are recorded Church API pages under tests/fixtures/scriptures/.
"""
import json
from pathlib import Path

import pytest

from extractors import scripture_page as sp

FIXTURES = Path(__file__).parent / "fixtures" / "scriptures"


def load(uri: str) -> dict:
    return json.loads((FIXTURES / (uri.strip("/").replace("/", "__") + ".json")).read_text())


def parse(uri: str) -> sp.ParsedPage:
    return sp.parse_page(uri, load(uri))


# -- classification ----------------------------------------------------------

@pytest.mark.parametrize("uri,kind", [
    ("/scriptures/bofm", "volume_toc"),
    ("/scriptures/jst", "volume_toc"),
    ("/scriptures/ot/gen/_contents", "book_toc"),
    ("/scriptures/bofm/alma/32", "chapter"),
    ("/scriptures/pgp/a-of-f/1", "chapter"),
    ("/scriptures/dc-testament/dc/45", "section"),
    ("/scriptures/dc-testament/od/1", "declaration"),
    ("/scriptures/pgp/abr/fac-1", "facsimile"),
    ("/scriptures/bofm/title-page", "front_matter"),
    ("/scriptures/dc-testament/chron-order", "front_matter"),
    ("/scriptures/jst/jst-gen/9", "jst_appendix"),
    ("/scriptures/jst/introduction", "jst_appendix"),
])
def test_classify_page(uri, kind):
    assert sp.classify_page(uri) == kind


# -- hrefs -------------------------------------------------------------------

def test_resolve_href_scripture_range_and_focus():
    t = sp.resolve_href("/study/scriptures/nt/heb/11?lang=eng&amp;id=p1-p40#p1")
    assert (t.target_uri, t.book_uri, t.chapter, t.verse_ranges, t.help) == \
        ("/scriptures/nt/heb/11", "/scriptures/nt/heb", 11, [(1, 40)], None)


def test_resolve_href_list_gives_one_range_per_segment():
    t = sp.resolve_href("/study/scriptures/ot/gen/6?lang=eng&id=p18%2Cp20-p21#p18")
    assert t.verse_ranges == [(18, 18), (20, 21)]


def test_resolve_href_study_help_and_volume_level_pages():
    t = sp.resolve_href("/study/scriptures/tg/hope?lang=eng")
    assert (t.help, t.book_uri, t.target_uri) == ("tg/hope", None, "/scriptures/tg/hope")
    t = sp.resolve_href("/study/scriptures/bofm/three?lang=eng")
    assert (t.book_uri, t.chapter, t.help) == (None, None, None) and t.target_uri == "/scriptures/bofm/three"
    assert sp.resolve_href("https://example.com/x").target_uri is None


# -- Alma 32 (chapter) -------------------------------------------------------

def test_alma_32_verses_and_header():
    page = parse("/scriptures/bofm/alma/32")
    assert (page.kind, page.number, page.title) == ("chapter", 32, "Alma 32")
    assert [v.verse for v in page.verses] == list(range(1, 44))
    v21 = page.verses[20]
    assert v21.text == ("And now as I said concerning faith—faith is not to have a perfect knowledge of things; "
                        "therefore if ye have faith ye hope for things which are not seen, which are true.")
    assert (v21.aid, v21.html_id) == ("128351643", "p21")
    assert "study-note-ref" in v21.text_html and "verse-number" in v21.text_html
    assert page.summary.startswith("Alma teaches the poor whose afflictions had humbled them")
    assert page.summary.endswith("About 74 B.C.") and "<" not in page.summary
    assert "<small>" in page.summary_html
    assert page.intro is None
    assert page.verse_paragraphs == 43


def test_alma_32_footnotes_and_refs_from_href():
    page = parse("/scriptures/bofm/alma/32")
    notes = {f.note_key: f for f in page.footnotes}
    assert len(notes) == len(load("/scriptures/bofm/alma/32")["content"]["footnotes"])
    assert set(page.body_note_keys) == set(notes)
    a = notes["note21_a"]
    assert (a.marker, a.letter, a.context, a.pid) == ("21a", "a", "faith", "128351643")
    assert a.text == "John 20:29; Heb. 11:1 (1–40)."
    assert [(r.category, r.target.book_uri, r.target.chapter, r.verse_start, r.verse_end) for r in a.refs] == [
        ("cross-ref", "/scriptures/nt/john", 20, 29, 29),
        ("cross-ref", "/scriptures/nt/heb", 11, 1, 40),
    ]
    assert [r.seq for r in a.refs] == [0, 1]
    tg = notes["note21_b"].refs[0]
    assert (tg.category, tg.target.help, tg.label) == ("tg", "tg/hope", "TG Hope")


# -- D&C 45 (section with study-intro) ----------------------------------------

def test_dc_45_section_intro_and_summary():
    page = parse("/scriptures/dc-testament/dc/45")
    assert (page.kind, page.number, len(page.verses)) == ("section", 45, 75)
    assert page.intro.startswith("Revelation given through Joseph Smith the Prophet to the Church, at Kirtland, Ohio")
    assert page.summary.startswith("1–5, Christ is our advocate with the Father")
    assert "<" not in page.intro and "<" not in page.summary
    categories = {r.category for f in page.footnotes for r in f.refs}
    assert {"cross-ref", "tg"} <= categories


# -- Genesis 1 (translation notes) ---------------------------------------------

def test_gen_1_translation_notes_are_text_only():
    page = parse("/scriptures/ot/gen/1")
    assert len(page.verses) == 31
    trn = [f for f in page.footnotes if 'data-note-category="trn"' in f.text_html]
    assert trn, "Genesis 1 has Hebrew/Greek translation notes"
    heb = next(f for f in trn if not f.refs)
    assert heb.text and "<" not in heb.text
    # pilcrows are not text
    assert all("¶" not in v.text for v in page.verses)
    assert "¶" in next(v.text_html for v in page.verses if v.verse == 6)


# -- documents without verses --------------------------------------------------

def test_official_declaration_has_no_verses():
    page = parse("/scriptures/dc-testament/od/1")
    assert (page.kind, page.number, page.verses, page.footnotes) == ("declaration", 1, [], [])
    assert page.intro.startswith("The Bible and the Book of Mormon teach that monogamy")
    assert page.summary is None   # no verses: the study-intro is not copied into the summary


def test_facsimile_and_front_matter():
    fac = parse("/scriptures/pgp/abr/fac-1")
    assert (fac.kind, fac.number, fac.verses) == ("facsimile", 1, [])
    tp = parse("/scriptures/bofm/title-page")
    assert (tp.kind, tp.number, tp.verses, tp.title) == ("front_matter", None, [], "Title Page")


def test_jst_appendix_page_has_no_verses():
    page = parse("/scriptures/jst/jst-gen/9")
    assert page.kind == "jst_appendix" and page.verses == [] and page.number is None
    assert page.title == "JST, Genesis 9"


# -- Jude 1 (single-chapter book) and short refs --------------------------------

def test_jude_short_ref_resolved_from_href():
    page = parse("/scriptures/nt/jude/1")
    note = next(f for f in page.footnotes if f.note_key == "note3_b")
    short = [r for r in note.refs if r.label == "26:33"]
    assert short and short[0].target.target_uri == "/scriptures/bofm/2-ne/26"
    assert (short[0].target.chapter, short[0].verse_start) == (26, 33)


# -- footnote categories (inline) -------------------------------------------------

def test_jst_footnote_rules():
    # hrefless jst span: one 'jst' ref holding the span text; the JST item parses the target from it
    n = sp.parse_footnote("note6_a", {
        "marker": "6a", "pid": "1", "context": "repented",
        "text": '<p><span data-note-category="jst">JST Gen. 8:13 And it repented…</span></p>'})
    assert [(r.category, r.ref_type, r.href) for r in n.refs] == [("jst", "jst-note", None)]
    assert n.refs[0].label.startswith("JST Gen. 8:13")
    # appendix link: the link is the jst target, one ref per JST verse of its range
    n = sp.parse_footnote("note4_a", {
        "marker": "4a", "pid": "1", "context": "x",
        "text": '<p><span data-note-category="jst"><a class="scripture-ref" '
                'href="/study/scriptures/jst/jst-gen/9?lang=eng&amp;id=p4-p6#p4">JST Gen. 9:4–6 (Appendix)</a></span></p>'})
    assert [(r.category, r.target.target_uri, r.verse_start, r.verse_end) for r in n.refs] == [
        ("jst", "/scriptures/jst/jst-gen/9", v, v) for v in (4, 5, 6)]
    assert [r.seq for r in n.refs] == [0, 1, 2]
    # an ordinary link inside a jst span is a cross-ref, next to the hrefless jst ref
    n = sp.parse_footnote("note1_a", {
        "marker": "1a", "pid": "1", "context": "x",
        "text": '<p><span data-note-category="jst">JST Rev. 2:1 (vv. <a class="scripture-ref" '
                'href="/study/scriptures/nt/rev/2?lang=eng&amp;id=p1#p1">1</a>)</span></p>'})
    assert [r.category for r in n.refs] == ["jst", "cross-ref"]
    # a cross-ref span linking into the JST appendix stays cross-ref, and its range is not expanded
    n = sp.parse_footnote("note30_a", {
        "marker": "30a", "pid": "1", "context": "x",
        "text": '<p><span data-note-category="cross-ref"><a class="scripture-ref" '
                'href="/study/scriptures/jst/jst-ex/33?lang=eng&amp;id=p20-p23#p20">JST Ex. 33:20–23</a></span></p>'})
    assert [(r.category, r.verse_start, r.verse_end) for r in n.refs] == [("cross-ref", 20, 23)]


@pytest.mark.parametrize("key,text,href", [
    # the <h1> book-title notes (song/1, matt/1, mark/1, luke/1, john/1)
    ("note", "JST entitles this book “The Testimony of St. Matthew.”", None),
    ("note", "The JST manuscript states that “the Songs of Solomon are not inspired writings.”", None),
    # the two JS—M notes: a Pearl of Great Price link, no JST verse
    ("note3_b", "JS—M 1:4 adds “or the destruction of the wicked.”", "/study/scriptures/pgp/js-m/1?lang=eng&amp;id=p4#p4"),
    ("note1_a", "The text of JST Mark 13 is the same as JST Matthew 24. See Pearl of Great Price, JS—M.",
     "/study/scriptures/pgp/js-m/1?lang=eng"),
])
def test_jst_span_naming_no_jst_verse_gets_no_jst_ref(key, text, href):
    body = f'<a class="scripture-ref" href="{href}">{text}</a>' if href else text
    n = sp.parse_footnote(key, {"marker": "", "pid": "7", "context": "",
                                "text": f'<p><span data-note-category="jst">{body}</span></p>'})
    assert n.text and n.pid == "7"
    assert [r.category for r in n.refs] == (["cross-ref"] if href else [])


@pytest.mark.parametrize("text,named", [
    ("JST Gen. 8:13 And it repented…", True),
    ("JST 1 Cor. 14:2 For he that speaketh", True),
    ("JST Matt. 5:24 Therefore", True),
    ("JST entitles this book “The Testimony of St. John.”", False),
    ("JS—M 1:4 adds", False),
])
def test_names_jst_verse(text, named):
    assert sp.names_jst_verse(text) is named


def test_verse_less_footnote_keys():
    n = sp.parse_footnote("note_asterisk", {"marker": "*", "pid": "9", "context": "", "text": "<p>IE The end.</p>"})
    assert (n.letter, n.refs, n.text) == (None, [], "IE The end.")


# -- TOC ---------------------------------------------------------------------------

def test_book_of_mormon_toc():
    toc = sp.parse_toc(load("/scriptures/bofm"))
    assert toc.title == "The Book of Mormon"
    names = {b.uri: b.name for b in toc.books}
    assert names["/scriptures/bofm/1-ne"] == "1 Nephi"
    assert "/scriptures/bofm/enos" in names and "/scriptures/bofm/moro" in names
    assert len(toc.books) == 15
    by_uri = {i.uri: i for i in toc.items}
    assert len(by_uri) == len(toc.items) == 259
    assert by_uri["/scriptures/bofm/title-page"].book_uri is None
    assert by_uri["/scriptures/bofm/pronunciation"].book_uri is None
    assert by_uri["/scriptures/bofm/alma/32"].book_uri == "/scriptures/bofm/alma"
    assert by_uri["/scriptures/bofm/alma/_contents"].book_uri == "/scriptures/bofm/alma"
    # the volume comes from the caller when given
    assert sp.parse_toc({**load("/scriptures/bofm"), "uri": ""}, "bofm").books[0].volume == "bofm"


def test_book_contents_links_and_the_facsimiles_book():
    links = sp.parse_book_contents(load("/scriptures/ot/gen/_contents"))
    assert links == [f"/scriptures/ot/gen/{n}" for n in range(1, 51)]
    assert sp.contents_link_book("/scriptures/ot/gen/7", "/scriptures/ot/gen") == "/scriptures/ot/gen"
    assert sp.contents_link_book("/scriptures/pgp/abr/5", "/scriptures/pgp/abr") == "/scriptures/pgp/abr"
    assert sp.contents_link_book("/scriptures/pgp/abr/fac-2", "/scriptures/pgp/abr") == "/scriptures/pgp/abr/fac"
