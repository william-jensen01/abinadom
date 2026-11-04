"""scripts/build_scriptures.py on a small raw store made from recorded pages (no network).

Six tiny volume TOCs link to a handful of fixture pages (Alma 32, D&C 45, OD 1, Abraham fac-1, the
BoM title page, a JST appendix chapter), plus a made-up Abraham 1 and Abraham `_contents` page.
"""
import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "scriptures"

spec = importlib.util.spec_from_file_location("build_scriptures", ROOT / "scripts" / "build_scriptures.py")
build_scriptures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_scriptures)

RAW_DDL = (ROOT / "db" / "scripture_schema.sql").read_text().split("-- ==== normalized layer ====")[0]

PAGES = [
    "/scriptures/bofm/title-page",
    "/scriptures/bofm/alma/32",
    "/scriptures/dc-testament/dc/45",
    "/scriptures/dc-testament/od/1",
    "/scriptures/pgp/abr/fac-1",
    "/scriptures/jst/jst-gen/9",
]


def toc(title: str, uri: str, groups: str) -> dict:
    body = f'<header><h1 class="title">{title}</h1></header><nav class="manifest"><ul class="doc-map">{groups}</ul></nav>'
    return {"meta": {"title": title}, "content": {"body": body, "footnotes": {}}, "uri": uri}


def link(uri: str, title: str) -> str:
    return (f'<li data-content-type="chapter"><a href="/study{uri}?lang=eng" class="list-tile">'
            f'<p class="title">{title}</p></a></li>')


def group(name: str, items: str, kind: str = "book") -> str:
    return (f'<li data-content-type="{kind}"><h2 class="label"><p class="title">{name}</p></h2>'
            f'<ul class="doc-map">{items}</ul></li>')


def contents(*uris: str) -> dict:
    """A book `_contents` page (a plain list of links, as the API serves it)."""
    items = "".join(f'<li><a href="/study{u}?lang=eng" class="list-tile"><p class="title">{u}</p></a></li>' for u in uris)
    return {"meta": {"title": "Contents"}, "content": {"body": f'<nav class="toc"><ul>{items}</ul></nav>', "footnotes": {}}}


ABR_1 = {"meta": {"title": "Abraham 1"}, "content": {"footnotes": {}, "body": (
    '<p class="verse" data-aid="900001" id="p1"><span class="verse-number">1 </span>In the land of the Chaldeans.</p>'
    '<p class="verse" data-aid="900002" id="p2"><span class="verse-number">2 </span>And, finding there was greater happiness.</p>')}}

# Abraham's _contents lists its chapters and the facsimiles, which count toward the Facsimiles book;
# abr/2 is listed there but in no volume TOC, so it is reported and not counted
SYNTHETIC = {
    "/scriptures/pgp/abr/1": ABR_1,
    "/scriptures/pgp/abr/_contents": contents("/scriptures/pgp/abr/1", "/scriptures/pgp/abr/2",
                                              "/scriptures/pgp/abr/fac-1"),
}


TOCS = {
    "/scriptures/ot": toc("Old Testament", "/scriptures/ot", ""),
    "/scriptures/nt": toc("New Testament", "/scriptures/nt", ""),
    "/scriptures/bofm": toc("The Book of Mormon", "/scriptures/bofm",
                            group("Introduction and Witnesses", link("/scriptures/bofm/title-page", "Title Page"), "x")
                            + group("Alma", link("/scriptures/bofm/alma/32", "Alma 32"))),
    "/scriptures/dc-testament": toc("Doctrine and Covenants", "/scriptures/dc-testament",
                                    group("Sections", link("/scriptures/dc-testament/dc/45", "Section 45"))
                                    + group("Official Declarations", link("/scriptures/dc-testament/od/1", "OD 1"))),
    "/scriptures/pgp": toc("Pearl of Great Price", "/scriptures/pgp",
                           group("Abraham", link("/scriptures/pgp/abr/_contents", "Contents")
                                 + link("/scriptures/pgp/abr/1", "Abraham 1")
                                 + group("Facsimiles", link("/scriptures/pgp/abr/fac-1", "Facsimile 1"), "x"))),
    "/scriptures/jst": toc("Joseph Smith Translation Appendix", "/scriptures/jst",
                           group("JST, Genesis", link("/scriptures/jst/jst-gen/9", "JST, Genesis 9"))),
}


def make_raw_db(path: Path, drop: str = None, replace: dict = None) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(RAW_DDL)
    docs = dict(TOCS)
    docs.update(SYNTHETIC)
    for uri in PAGES:
        docs[uri] = json.loads((FIXTURES / (uri.strip("/").replace("/", "__") + ".json")).read_text())
    docs.update(replace or {})
    for uri, doc in docs.items():
        if uri == drop:
            continue
        conn.execute("INSERT INTO raw_page VALUES (?,?,?,?,?,?)",
                     (uri, "eng", "2026-11-02T00:00:00Z", f"hash-{uri}", 200, json.dumps(doc)))
    conn.commit()
    conn.close()
    return path


def rows(db, sql, params=()):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    db = make_raw_db(tmp_path_factory.mktemp("raw") / "scripture.db")
    assert build_scriptures.build(str(db)) == 0
    return db


def test_structure_and_kinds(built):
    assert dict(rows(built, "SELECT uri, kind FROM page")) == {
        "/scriptures/ot": "volume_toc", "/scriptures/nt": "volume_toc", "/scriptures/bofm": "volume_toc",
        "/scriptures/dc-testament": "volume_toc", "/scriptures/pgp": "volume_toc", "/scriptures/jst": "volume_toc",
        "/scriptures/bofm/title-page": "front_matter", "/scriptures/bofm/alma/32": "chapter",
        "/scriptures/dc-testament/dc/45": "section", "/scriptures/dc-testament/od/1": "declaration",
        "/scriptures/pgp/abr/fac-1": "facsimile", "/scriptures/jst/jst-gen/9": "jst_appendix",
        "/scriptures/pgp/abr/_contents": "book_toc", "/scriptures/pgp/abr/1": "chapter",
    }
    # chapter rows only for document kinds; appendix and TOC pages have a page row only
    assert rows(built, "SELECT COUNT(*) FROM chapter")[0][0] == 6
    assert rows(built, "SELECT COUNT(*) FROM chapter c JOIN page p USING(page_id) WHERE p.uri LIKE '/scriptures/jst/%'")[0][0] == 0
    assert rows(built, "SELECT COUNT(*) FROM verse v JOIN chapter c USING(chapter_id) JOIN page p USING(page_id) "
                       "WHERE p.uri LIKE '/scriptures/jst/%'")[0][0] == 0
    books = {u: (n, a, c, k) for u, n, a, c, k in rows(
        built, "SELECT uri, num_chapters, cite_abbr, core_book_id, volume_id FROM book")}
    assert books["/scriptures/bofm/alma"][:3] == (1, "Alma", 213)
    assert books["/scriptures/pgp/abr/fac"][:3] == (1, "Fac.", 403)
    assert books["/scriptures/pgp/abr"][:3] == (1, "Abr.", 402)
    assert books["/scriptures/dc-testament/dc"][0] == 1 and books["/scriptures/dc-testament/od"][0] == 1
    assert rows(built, "SELECT book_id FROM page WHERE uri = '/scriptures/bofm/title-page'")[0][0] is None
    assert [r[0] for r in rows(built, "SELECT uri FROM volume ORDER BY sort")] == [
        "/scriptures/ot", "/scriptures/nt", "/scriptures/bofm", "/scriptures/dc-testament", "/scriptures/pgp"]


def test_content_rows(built):
    assert rows(built, "SELECT COUNT(*) FROM verse")[0][0] == 43 + 75 + 2
    n = rows(built, "SELECT COUNT(*) FROM footnote")[0][0]
    assert n == len(json.loads((FIXTURES / "scriptures__bofm__alma__32.json").read_text())["content"]["footnotes"]) \
        + len(json.loads((FIXTURES / "scriptures__dc-testament__dc__45.json").read_text())["content"]["footnotes"])
    assert rows(built, "SELECT COUNT(*) FROM footnote WHERE verse_id IS NULL")[0][0] == 0
    ref = rows(built, "SELECT r.target_help, r.target_book_id FROM footnote_ref r JOIN footnote f USING(footnote_id) "
                      "WHERE f.note_key = 'note21_b' AND r.category = 'tg'")
    assert ref == [("tg/hope", None)]
    # every footnote keeps the API's pid as anchor_aid; on a verse note it is the verse's aid
    assert rows(built, "SELECT COUNT(*) FROM footnote WHERE anchor_aid IS NULL")[0][0] == 0
    assert rows(built, "SELECT COUNT(*) FROM footnote f JOIN verse v USING(verse_id) WHERE f.anchor_aid != v.aid")[0][0] == 0
    assert rows(built, "SELECT f.anchor_aid FROM footnote f WHERE f.note_key = 'note21_a' AND f.page_id = "
                       "(SELECT page_id FROM page WHERE uri = '/scriptures/bofm/alma/32')") == [("128351643",)]


def test_num_chapters_comes_from_the_contents_page(tmp_path, capsys):
    db = make_raw_db(tmp_path / "report.db")
    assert build_scriptures.build(str(db)) == 0
    out = capsys.readouterr().out
    assert "/scriptures/pgp/abr/2" in out and "not counted" in out   # listed on _contents only: reported
    assert rows(db, "SELECT uri, num_chapters FROM book WHERE uri LIKE '/scriptures/pgp/%' ORDER BY uri") == [
        ("/scriptures/pgp/abr", 1), ("/scriptures/pgp/abr/fac", 1)]


def test_contents_page_that_disagrees_with_the_chapter_rows_fails(tmp_path, capsys):
    # Abraham's _contents lists no chapter: num_chapters 0, but the volume TOC gives Abraham a chapter row
    db = make_raw_db(tmp_path / "short.db", replace={"/scriptures/pgp/abr/_contents": contents("/scriptures/pgp/abr/fac-1")})
    assert build_scriptures.build(str(db)) == 1
    err = capsys.readouterr().err
    assert "num_chapters" in err and "/scriptures/pgp/abr" in err


def test_facsimiles_outside_their_group_fail(tmp_path, capsys):
    # without the Facsimiles group there is no abr/fac book: the fac link on _contents has no book to count toward
    flat = toc("Pearl of Great Price", "/scriptures/pgp",
               group("Abraham", link("/scriptures/pgp/abr/_contents", "Contents") + link("/scriptures/pgp/abr/1", "Abraham 1")
                     + link("/scriptures/pgp/abr/fac-1", "Facsimile 1")))
    db = make_raw_db(tmp_path / "flat.db", replace={"/scriptures/pgp": flat})
    assert build_scriptures.build(str(db)) == 1
    err = capsys.readouterr().err
    assert "/scriptures/pgp/abr/fac" in err


def test_build_meta_and_determinism(built, tmp_path):
    meta = dict(rows(built, "SELECT key, value FROM build_meta"))
    assert len(meta["build_id"]) == 64 and meta["raw_pages"] == "14"
    second = tmp_path / "again.db"
    shutil.copy(built, second)
    assert build_scriptures.build(str(second)) == 0
    assert dict(rows(second, "SELECT key, value FROM build_meta"))["build_id"] == meta["build_id"]


def test_build_id_changes_with_content(built, tmp_path):
    other = tmp_path / "changed.db"
    shutil.copy(built, other)
    conn = sqlite3.connect(other)
    doc = json.loads(conn.execute("SELECT json FROM raw_page WHERE uri='/scriptures/bofm/alma/32'").fetchone()[0])
    doc["content"]["body"] = doc["content"]["body"].replace("entering into their synagogues", "entering into their churches")
    conn.execute("UPDATE raw_page SET json=?, content_hash='new' WHERE uri='/scriptures/bofm/alma/32'", (json.dumps(doc),))
    conn.commit()
    conn.close()
    assert build_scriptures.build(str(other)) == 0
    assert rows(other, "SELECT value FROM build_meta WHERE key='build_id'") != \
        rows(built, "SELECT value FROM build_meta WHERE key='build_id'")


def test_missing_toc_page_fails_and_names_it(tmp_path, capsys):
    db = make_raw_db(tmp_path / "missing.db", drop="/scriptures/bofm/alma/32")
    assert build_scriptures.build(str(db)) == 1
    assert "/scriptures/bofm/alma/32" in capsys.readouterr().err
    assert not rows(db, "SELECT name FROM sqlite_master WHERE name = 'verse'")


def test_failed_validation_rolls_back_and_keeps_the_old_build(built, tmp_path, capsys):
    db = tmp_path / "keep.db"
    shutil.copy(built, db)
    before = rows(db, "SELECT value FROM build_meta WHERE key='build_id'")
    conn = sqlite3.connect(db)
    doc = json.loads(conn.execute("SELECT json FROM raw_page WHERE uri='/scriptures/bofm/alma/32'").fetchone()[0])
    first = doc["content"]["body"].index('<p class="verse"')
    end = doc["content"]["body"].index("</p>", first) + 4
    doc["content"]["body"] = doc["content"]["body"][:first] + doc["content"]["body"][end:]   # verse 1 gone: 2..43
    conn.execute("UPDATE raw_page SET json=?, content_hash='broken' WHERE uri='/scriptures/bofm/alma/32'", (json.dumps(doc),))
    conn.commit()
    conn.close()
    assert build_scriptures.build(str(db)) == 1
    assert "1..N" in capsys.readouterr().err
    assert rows(db, "SELECT value FROM build_meta WHERE key='build_id'") == before
    assert rows(db, "SELECT COUNT(*) FROM verse")[0][0] == 43 + 75 + 2


def test_raw_layer_is_untouched(built, tmp_path):
    db = tmp_path / "raw.db"
    make_raw_db(db)
    before = rows(db, "SELECT uri, content_hash, json FROM raw_page ORDER BY 1")
    assert build_scriptures.build(str(db)) == 0
    assert rows(db, "SELECT uri, content_hash, json FROM raw_page ORDER BY 1") == before
