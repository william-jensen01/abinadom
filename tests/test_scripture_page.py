"""Golden-file tests for extractors/scripture_page.py and extractors/scripture_jst.py (pure parsing).

Fixtures are recorded Church API pages under tests/fixtures/scriptures/.
"""
import json
from pathlib import Path

import pytest

from extractors import scripture_jst as jst
from extractors import scripture_page as sp

FIXTURES = Path(__file__).parent / "fixtures" / "scriptures"


def load(uri):
    return json.loads((FIXTURES / (uri.strip("/").replace("/", "__") + ".json")).read_text())


def parse(uri):
    return sp.parse_page(uri, load(uri))


def note(text, key="note1_a"):
    return sp.parse_footnote(key, {"marker": "1a", "pid": "7", "context": "x", "text": f"<p>{text}</p>"})


def refs(n):
    return [(r.category, r.ref_type, r.target_uri, r.chapter, r.verse_start, r.verse_end, r.jst_book) for r in n.refs]


@pytest.mark.parametrize("uri,kind,book", [
    ("/scriptures/bofm", "volume_toc", None),
    ("/scriptures/ot/gen/_contents", "book_toc", "/scriptures/ot/gen"),
    ("/scriptures/bofm/alma/32", "chapter", "/scriptures/bofm/alma"),
    ("/scriptures/dc-testament/dc/45", "section", "/scriptures/dc-testament/dc"),
    ("/scriptures/dc-testament/od/1", "declaration", "/scriptures/dc-testament/od"),
    ("/scriptures/pgp/abr/fac-1", "facsimile", "/scriptures/pgp/abr/fac"),
    ("/scriptures/bofm/title-page", "front_matter", None),
    ("/scriptures/dc-testament/chron-order", "front_matter", None),
    ("/scriptures/jst/jst-gen/9", "jst_appendix", None),
    ("/scriptures/jst/jst-gen/_contents", "book_toc", None),
])
def test_kind_and_book_from_the_uri(uri, kind, book):
    assert (sp.classify(uri), sp.book_uri(uri)) == (kind, book)


def test_resolve_href():
    assert [(r.target_uri, r.book_uri, r.chapter, r.verse_start, r.verse_end, r.help) for r in sp.resolve_href(
        "/study/scriptures/ot/gen/6?lang=eng&id=p18%2Cp20-p21#p18")] == [
        ("/scriptures/ot/gen/6", "/scriptures/ot/gen", 6, 18, 18, None),
        ("/scriptures/ot/gen/6", "/scriptures/ot/gen", 6, 20, 21, None)]
    (tg,) = sp.resolve_href("/study/scriptures/tg/hope?lang=eng")
    assert (tg.help, tg.book_uri, tg.target_uri) == ("tg/hope", None, "/scriptures/tg/hope")
    (fm,) = sp.resolve_href("/study/scriptures/bofm/three?lang=eng")
    assert (fm.target_uri, fm.book_uri, fm.chapter, fm.help) == ("/scriptures/bofm/three", None, None, None)
    assert sp.resolve_href("https://example.com/x")[0].target_uri is None


def test_alma_32():
    page = parse("/scriptures/bofm/alma/32")
    assert (page.kind, page.number, page.title, page.intro) == ("chapter", 32, "Alma 32", None)
    assert [v.verse for v in page.verses] == list(range(1, 44))
    v21 = page.verses[20]
    assert v21.text == ("And now as I said concerning faith—faith is not to have a perfect knowledge of things; "
                        "therefore if ye have faith ye hope for things which are not seen, which are true.")
    assert (v21.aid, v21.html_id) == ("128351643", "p21") and "study-note-ref" in v21.text_html
    assert page.summary.startswith("Alma teaches the poor") and page.summary.endswith("About 74 B.C.")
    assert "<small>" in page.summary_html
    notes = {f.note_key: f for f in page.footnotes}
    assert len(notes) == len(load("/scriptures/bofm/alma/32")["content"]["footnotes"]) == len(page.note_markers)
    a = notes["note21_a"]
    assert (a.marker, a.letter, a.context, a.pid, a.text) == ("21a", "a", "faith", "128351643",
                                                               "John 20:29; Heb. 11:1 (1–40).")
    assert refs(a) == [("cross-ref", "scripture-ref", "/scriptures/nt/john/20", 20, 29, 29, None),
                       ("cross-ref", "scripture-ref", "/scriptures/nt/heb/11", 11, 1, 40, None)]
    tg = notes["note21_b"].refs[0]
    assert (tg.category, tg.help, tg.label) == ("tg", "tg/hope", "TG Hope")


def test_dc_45_gen_1_and_jude():
    dc = parse("/scriptures/dc-testament/dc/45")
    assert (dc.kind, dc.number, len(dc.verses)) == ("section", 45, 75)
    assert dc.intro.startswith("Revelation given through Joseph Smith the Prophet to the Church, at Kirtland")
    assert dc.summary.startswith("1–5, Christ is our advocate with the Father")
    gen = parse("/scriptures/ot/gen/1")
    assert len(gen.verses) == 31 and all("¶" not in v.text for v in gen.verses)   # pilcrows are not text
    assert any(not f.refs and 'data-note-category="trn"' in f.text_html for f in gen.footnotes)
    # a short ref ("26:33") takes its book from the href, never from the label
    jude = {f.note_key: f for f in parse("/scriptures/nt/jude/1").footnotes}
    (short,) = [r for r in jude["note3_b"].refs if r.label == "26:33"]
    assert (short.target_uri, short.chapter, short.verse_start) == ("/scriptures/bofm/2-ne/26", 26, 33)


def test_pages_without_verses():
    od = parse("/scriptures/dc-testament/od/1")
    assert (od.kind, od.number, od.verses, od.footnotes, od.summary) == ("declaration", 1, [], [], None)
    assert od.intro.startswith("The Bible and the Book of Mormon teach that monogamy")
    assert (parse("/scriptures/pgp/abr/fac-1").number, parse("/scriptures/pgp/abr/fac-1").verses) == (1, [])
    tp = parse("/scriptures/bofm/title-page")
    assert (tp.kind, tp.number, tp.verses, tp.title) == ("front_matter", None, [], "Title Page")
    appendix = parse("/scriptures/jst/jst-gen/9")
    assert (appendix.kind, appendix.verses, appendix.number, appendix.title) == ("jst_appendix", [], None,
                                                                                  "JST, Genesis 9")


def test_jst_footnotes():
    # text only: the JST verse is parsed from the text, one ref per verse
    assert refs(note('<span data-note-category="jst">JST Gen. 8:23–24 … my covenant</span>')) == [
        ("jst", "jst-note", None, 8, v, v, 101) for v in (23, 24)]
    # an appendix link is the target, one ref per verse of its range
    n = note('<span data-note-category="jst"><a href="/study/scriptures/jst/jst-gen/9?lang=eng&amp;id=p4-p6#p4">'
             'JST Gen. 9:4–6 (Appendix)</a></span>')
    assert refs(n) == [("jst", "scripture-ref", "/scriptures/jst/jst-gen/9", 9, v, v, 101) for v in (4, 5, 6)]
    # another link inside a jst span is a cross-ref; the span's JST verse still comes from its text
    n = note('<span data-note-category="jst">JST Rev. 2:1 (vv. <a href="/study/scriptures/nt/rev/2?lang=eng&amp;'
             'id=p1#p1">1</a>)</span>')
    assert [(r.category, r.chapter, r.verse_start) for r in n.refs] == [("jst", 2, 1), ("cross-ref", 2, 1)]
    # a JST link inside a cross-ref span stays a cross-ref, its range not expanded
    n = note('<span data-note-category="cross-ref"><a href="/study/scriptures/jst/jst-ex/33?lang=eng&amp;'
             'id=p20-p23#p20">JST Ex. 33:20–23</a></span>')
    assert [(r.category, r.verse_start, r.verse_end, r.jst_book) for r in n.refs] == [("cross-ref", 20, 23, None)]


@pytest.mark.parametrize("text", [
    "JST entitles this book “The Testimony of St. Matthew.”",
    "The JST manuscript states that “the Songs of Solomon are not inspired writings.”",
    '<a href="/study/scriptures/pgp/js-m/1?lang=eng&amp;id=p4#p4">JS—M 1:4 adds “or the destruction …”</a>',
])
def test_jst_span_naming_no_jst_verse_gets_no_jst_ref(text):
    n = note(f'<span data-note-category="jst">{text}</span>', key="note")
    assert n.text and n.letter is None and [r.category for r in n.refs] == (["cross-ref"] if "href" in text else [])


def test_tocs():
    bofm = load("/scriptures/bofm")
    links = sp.toc_links(bofm)
    assert len(links) == len(set(links)) == 259 and links[0] == "/scriptures/bofm/title-page"
    groups = sp.toc_groups(bofm)
    assert groups["/scriptures/bofm/1-ne/1"] == ["1 Nephi"] and groups["/scriptures/bofm/alma/_contents"] == ["Alma"]
    assert sp.contents_links(load("/scriptures/ot/gen/_contents")) == [f"/scriptures/ot/gen/{n}" for n in range(1, 51)]


# -- JST appendix -------------------------------------------------------------------

@pytest.mark.parametrize("spec,expect", [
    ("9:4–6", [(9, 4, 9, 6)]),
    ("4:1, 5–6, 8–9", [(4, 1, 4, 1), (4, 5, 4, 6), (4, 8, 4, 9)]),
    ("1:1–8:18", [(1, 1, 8, 18)]),
    ("19:15, 21.", [(19, 15, 19, 15), (19, 21, 19, 21)]),
    ("", None), ("9:6–4", None), ("9:4, y", None), ("5", None),
])
def test_parse_verse_spec(spec, expect):
    assert jst.parse_verse_spec(spec) == expect


def test_appendix_passages():
    ps = jst.parse_appendix("/scriptures/jst/jst-gen/9", load("/scriptures/jst/jst-gen/9"))
    p = ps[0]
    assert (p.section_id, p.title, p.verse_spec, p.ranges, p.paragraphs) == (
        "sec_gen_9_4_6", "JST, Genesis 9:4–6.", "9:4–6", [(9, 4, 9, 6)], [4, 5, 6])
    assert p.intro.startswith("After the Flood, Noah asks the Lord")
    assert [(rel, r.book_uri, r.chapter, end, r.verse_start, r.verse_end) for rel, r, end in p.refs] == [
        ("compare", "/scriptures/ot/gen", 8, None, 20, 22)]


def test_heading_links_by_relation_and_span():
    def heading(links):
        return {"content": {"body": f'<section id="s"><h2 data-aid="1"><strong>JST, Genesis 9:4–6.</strong> {links}'
                                    '</h2></section>'}}
    (p,) = jst.parse_appendix("/scriptures/jst/jst-gen/9", heading(
        'Compare <a href="/study/scriptures/ot/ex/7?lang=eng&amp;id=p3%2Cp13#p3">7:3, 13</a>; similar changes were '
        'made in <a href="/study/scriptures/nt/luke/4?lang=eng&amp;id=p2#p2">Luke 4:2</a>; see also '
        '<a href="/study/scriptures/jst/jst-luke/12?lang=eng&amp;id=p9-p12#p9">JST, Luke 12:9–12</a>'))
    assert [(rel, r.chapter, r.verse_start) for rel, r, _ in p.refs] == [
        ("compare", 7, 3), ("compare", 7, 13), ("similar", 4, 2), ("see-also", 12, 9)]
    (p,) = jst.parse_appendix("/scriptures/jst/jst-gen/1-8", heading(
        'Compare <a href="/study/scriptures/ot/gen/1?lang=eng&amp;span=1%3A1-6%3A13#p1">Genesis 1:1–6:13</a>'))
    ((_, r, end),) = p.refs
    assert (r.chapter, end, r.verse_start, r.verse_end) == (1, 6, 1, 13)
