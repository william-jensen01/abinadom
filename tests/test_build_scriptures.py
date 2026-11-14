"""scripts/build_scriptures.py on a small raw store of recorded pages, with core.db's JST rows faked (no network).

Six tiny volume TOCs link to fixture pages (Alma 32, D&C 45, OD 1, Abraham fac-1, the BoM title page, JST Genesis 9)
and to made-up pages: Exodus 7 with JST footnotes, Abraham 1, and Abraham's `_contents`.
"""
import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from extractors import scripture_jst

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "scriptures"
spec = importlib.util.spec_from_file_location("build_scriptures", ROOT / "scripts" / "build_scriptures.py")
build_scriptures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_scriptures)
READ_CORE_JST = scripture_jst.read_core_jst
RAW_DDL = (ROOT / "db" / "scripture_schema.sql").read_text().split("-- ==== normalized layer ====")[0]

GEN, EX = 101, 102
CORE = [{"ID": i, "BookID": b, "Chapter": c, "Verse": v, "Flag": f, "Text": f"{b} {c}:{v}".encode()}
        for i, (b, c, v, f) in enumerate([(EX, 7, 1, "F"), (EX, 7, 2, "J"), (EX, 7, 3, "F")]
                                         + [(GEN, 9, v, "F") for v in range(1, 30)], 1)]


def toc(title, *groups):
    return {"meta": {"title": title}, "content": {"body": f'<nav><ul class="doc-map">{"".join(groups)}</ul></nav>'}}


def link(uri):
    return f'<li><a href="/study{uri}?lang=eng"><p class="title">{uri}</p></a></li>'


def group(name, *items):
    return f'<li><h2 class="label"><p class="title">{name}</p></h2><ul class="doc-map">{"".join(items)}</ul></li>'


def contents(*uris):
    return {"meta": {"title": "Contents"}, "content": {"body": "<ul>" + "".join(link(u) for u in uris) + "</ul>"}}


def chapter(title, verses, footnotes=None):
    body = "".join(f'<p class="verse" data-aid="{aid}" id="p{n}"><span class="verse-number">{n} </span>{text}</p>'
                   for n, aid, text in verses)
    return {"meta": {"title": title}, "content": {"body": body, "footnotes": footnotes or {}}}


def jst_note(key, pid, inner):
    return {key: {"marker": key[4:].replace("_", ""), "pid": pid, "context": "x",
                  "text": f'<p><span data-note-category="jst">{inner}</span></p>'}}


EX_7 = chapter("Exodus 7", [
    (1, "701", 'And the Lord said <a class="study-note-ref" href="#note1_a"><sup class="marker"></sup>see</a>.'),
    (2, "702", 'Thou shalt <a class="study-note-ref" href="#note2_a"><sup class="marker"></sup>speak</a>.'),
    (3, "703", 'And I will <a class="study-note-ref" href="#note3_a"><sup class="marker"></sup>harden</a>.')],
    {**jst_note("note1_a", "701", "JST Ex. 7:1 … a prophet …"),
     **jst_note("note2_a", "702", '<a href="/study/scriptures/jst/jst-gen/9?lang=eng&amp;id=p4-p6#p4">JST Gen. 9:4–6</a>'),
     **jst_note("note3_a", "703", "JST Ex. 7:3 And Pharaoh will harden his heart …")})

PAGES = {u: json.loads((FIXTURES / (u.strip("/").replace("/", "__") + ".json")).read_text()) for u in [
    "/scriptures/bofm/title-page", "/scriptures/bofm/alma/32", "/scriptures/dc-testament/dc/45",
    "/scriptures/dc-testament/od/1", "/scriptures/pgp/abr/fac-1", "/scriptures/jst/jst-gen/9"]}
PAGES.update({
    "/scriptures/ot/ex/7": EX_7,
    "/scriptures/pgp/abr/1": chapter("Abraham 1", [(1, "901", "In the land of the Chaldeans.")]),
    # abr/2 is on _contents but in no volume TOC: reported, not counted; fac-1 counts toward the Facsimiles
    "/scriptures/pgp/abr/_contents": contents("/scriptures/pgp/abr/1", "/scriptures/pgp/abr/2",
                                              "/scriptures/pgp/abr/fac-1"),
    "/scriptures/ot": toc("Old Testament", group("Exodus", link("/scriptures/ot/ex/7"))),
    "/scriptures/nt": toc("New Testament"),
    "/scriptures/bofm": toc("The Book of Mormon", group("Introduction", link("/scriptures/bofm/title-page")),
                            group("Alma", link("/scriptures/bofm/alma/32"))),
    "/scriptures/dc-testament": toc("Doctrine and Covenants", group("Sections", link("/scriptures/dc-testament/dc/45")),
                                    group("Official Declarations", link("/scriptures/dc-testament/od/1"))),
    "/scriptures/pgp": toc("Pearl of Great Price", group(
        "Abraham", link("/scriptures/pgp/abr/_contents"), link("/scriptures/pgp/abr/1"),
        group("Facsimiles", link("/scriptures/pgp/abr/fac-1")))),
    "/scriptures/jst": toc("JST Appendix", group("JST, Genesis", link("/scriptures/jst/jst-gen/9"))),
})


@pytest.fixture(autouse=True)
def fake_core(monkeypatch):
    monkeypatch.setattr(scripture_jst, "read_core_jst", lambda: (CORE, len(CORE)))


def make_raw_db(path, drop=None, replace=None):
    conn = sqlite3.connect(path)
    conn.executescript(RAW_DDL)
    for uri, doc in {**PAGES, **(replace or {})}.items():
        if uri != drop:
            conn.execute("INSERT INTO raw_page VALUES (?,?,?,?,?,?)",
                         (uri, "eng", "2026-11-02T00:00:00Z", f"hash-{uri}", 200, json.dumps(doc)))
    conn.commit()
    conn.close()
    return path


def rows(db, sql):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(scripture_jst, "read_core_jst", lambda: (CORE, len(CORE)))
        db = make_raw_db(tmp_path_factory.mktemp("raw") / "scripture.db")
        assert build_scriptures.build(str(db)) == 0
    return db


def test_pages_books_and_chapters(built):
    kinds = dict(rows(built, "SELECT uri, kind FROM page"))
    assert len(kinds) == len(PAGES) and kinds["/scriptures/pgp/abr/_contents"] == "book_toc"
    assert kinds["/scriptures/jst/jst-gen/9"] == "jst_appendix" and kinds["/scriptures/ot"] == "volume_toc"
    assert rows(built, "SELECT COUNT(*) FROM chapter")[0][0] == 7       # document pages only
    books = {r[0]: r[1:] for r in rows(built, "SELECT uri, name, abbr, cite_abbr, core_book_id, num_chapters FROM book")}
    assert books == {
        "/scriptures/ot/ex": ("Exodus", "ex", "Ex.", EX, 1),
        "/scriptures/bofm/alma": ("Alma", "alma", "Alma", 213, 1),
        "/scriptures/dc-testament/dc": ("Sections", "dc", "D&C", 302, 1),
        "/scriptures/dc-testament/od": ("Official Declarations", "od", "O.D.", 303, 1),
        "/scriptures/pgp/abr": ("Abraham", "abr", "Abr.", 402, 1),
        "/scriptures/pgp/abr/fac": ("Facsimiles", "fac", "Fac.", 403, 1)}
    assert rows(built, "SELECT book_id FROM page WHERE uri = '/scriptures/bofm/title-page'") == [(None,)]


def test_verses_and_footnotes(built):
    assert rows(built, "SELECT COUNT(*) FROM verse")[0][0] == 3 + 43 + 75 + 1
    fixture_notes = sum(len(page["content"].get("footnotes") or {}) for page in PAGES.values())
    assert rows(built, "SELECT COUNT(*), COUNT(verse_id), COUNT(anchor_aid) FROM footnote")[0] == (fixture_notes,) * 3
    assert rows(built, "SELECT COUNT(*) FROM footnote f JOIN verse v USING (verse_id) WHERE f.anchor_aid != v.aid") \
        == [(0,)]
    assert rows(built, "SELECT r.target_help, r.target_book_id FROM footnote_ref r JOIN footnote f USING (footnote_id) "
                       "WHERE f.note_key = 'note21_b' AND r.category = 'tg'") == [("tg/hope", None)]


def test_jst_verses_footnotes_and_passages(built):
    assert rows(built, "SELECT core_id, book_id IS NOT NULL, chapter, verse, source_flag, text FROM jst_verse "
                       "WHERE core_id = 3") == [(3, 1, 7, 3, "F", "102 7:3")]
    links = rows(built, "SELECT v.verse, j.chapter, j.verse, r.target_book_id FROM footnote_ref r "
                        "JOIN footnote f USING (footnote_id) JOIN verse v USING (verse_id) "
                        "JOIN jst_verse j ON j.jst_verse_id = r.target_jst_verse_id WHERE r.category = 'jst' "
                        "ORDER BY v.verse, j.verse")
    assert links == [(1, 7, 1, None), (2, 9, 4, None), (2, 9, 5, None), (2, 9, 6, None), (3, 7, 3, None)]
    passages = rows(built, "SELECT title, chapter_start, verse_start, verse_end, core_book_id, "
                           "(SELECT COUNT(*) FROM jst_passage_verse pv WHERE pv.passage_id = p.passage_id) "
                           "FROM jst_passage p ORDER BY seq")
    assert passages[0] == ("JST, Genesis 9:4–6.", 9, 4, 6, GEN, 3)
    assert rows(built, "SELECT rel, target_uri, target_chapter, target_verse_start, target_verse_end "
                       "FROM jst_passage_ref ORDER BY passage_id, seq")[0] == ("compare", "/scriptures/ot/gen/8", 8, 20, 22)


def test_report_and_determinism(built, tmp_path, capsys):
    again = shutil.copy(built, tmp_path / "again.db")
    assert build_scriptures.build(str(again)) == 0
    assert "/scriptures/pgp/abr/2" in capsys.readouterr().out
    build_id = "SELECT value FROM build_meta WHERE key = 'build_id'"
    assert rows(again, build_id) == rows(built, build_id)
    assert rows(again, "SELECT uri, content_hash, json FROM raw_page ORDER BY 1") == \
        rows(built, "SELECT uri, content_hash, json FROM raw_page ORDER BY 1")


def test_missing_page_fails_and_names_it(tmp_path, capsys):
    db = make_raw_db(tmp_path / "missing.db", drop="/scriptures/bofm/alma/32")
    assert build_scriptures.build(str(db)) == 1
    assert "/scriptures/bofm/alma/32" in capsys.readouterr().err
    assert not rows(db, "SELECT name FROM sqlite_master WHERE name = 'verse'")


def test_contents_that_disagree_with_the_chapter_rows_fail(tmp_path, capsys):
    db = make_raw_db(tmp_path / "short.db", replace={"/scriptures/pgp/abr/_contents": contents("/scriptures/pgp/abr/fac-1")})
    assert build_scriptures.build(str(db)) == 1
    assert "num_chapters" in capsys.readouterr().err


def test_failed_check_rolls_back_to_the_previous_build(built, tmp_path, capsys):
    db = shutil.copy(built, tmp_path / "keep.db")
    gap = chapter("Exodus 7", [(1, "701", "a"), (3, "703", "c")])     # verses 1, 3: not 1..N
    conn = sqlite3.connect(db)
    conn.execute("UPDATE raw_page SET json = ? WHERE uri = '/scriptures/ot/ex/7'", (json.dumps(gap),))
    conn.commit()
    conn.close()
    assert build_scriptures.build(str(db)) == 1
    assert "1..N" in capsys.readouterr().err
    assert rows(db, "SELECT COUNT(*), (SELECT value FROM build_meta WHERE key = 'build_id') FROM verse") == \
        rows(built, "SELECT COUNT(*), (SELECT value FROM build_meta WHERE key = 'build_id') FROM verse")


def test_missing_core_db_is_a_prerequisite(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(scripture_jst, "read_core_jst", lambda: READ_CORE_JST(str(tmp_path / "core.db")))
    assert build_scriptures.build(str(make_raw_db(tmp_path / "nocore.db"))) == 1
    assert "PREREQUISITE" in capsys.readouterr().err


def test_db_without_a_raw_layer_fails_cleanly(tmp_path, capsys):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    assert build_scriptures.build(str(db)) == 1
    assert f"{db} has no raw layer; run scripts/fetch_scriptures.py first" in capsys.readouterr().err


def test_report_counts_passages_with_no_compare_link_or_missing_heading_verses(tmp_path, monkeypatch, capsys):
    core = [r for r in CORE if (r["BookID"], r["Chapter"], r["Verse"]) != (GEN, 9, 5)]   # inside "Genesis 9:4–6"
    monkeypatch.setattr(scripture_jst, "read_core_jst", lambda: (core, len(core)))
    gen9 = json.loads(json.dumps(PAGES["/scriptures/jst/jst-gen/9"]).replace("Compare", "See also", 1))
    db = make_raw_db(tmp_path / "report.db", replace={"/scriptures/jst/jst-gen/9": gen9})
    assert build_scriptures.build(str(db)) == 0
    out = capsys.readouterr().out
    assert "no Compare link: 1;" in out
    assert "heading verses not in jst_verse: 1 (JST, Genesis 9:4–6.);" in out


@pytest.mark.parametrize("pgp", [
    toc("Pearl of Great Price", group("Abraham", link("/scriptures/pgp/abr/_contents"), link("/scriptures/pgp/abr/1"),
                                      link("/scriptures/pgp/abr/fac-1"))),
    toc("Pearl of Great Price", group("Abraham", link("/scriptures/pgp/abr/_contents"), link("/scriptures/pgp/abr/1")),
        link("/scriptures/pgp/abr/fac-1"))], ids=["inside-abraham", "ungrouped"])
def test_facsimiles_without_their_own_toc_group_are_still_named(tmp_path, pgp):
    db = make_raw_db(tmp_path / "nofacgroup.db", replace={"/scriptures/pgp": pgp})
    assert build_scriptures.build(str(db)) == 0
    assert rows(db, "SELECT uri, name, cite_abbr FROM book WHERE uri LIKE '/scriptures/pgp/%' ORDER BY sort") == [
        ("/scriptures/pgp/abr", "Abraham", "Abr."), ("/scriptures/pgp/abr/fac", "Facsimiles", "Fac.")]
