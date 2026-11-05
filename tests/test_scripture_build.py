"""build_scriptures.py on the fixture raw store: parsing, normalizing and the build checks.

Golden values below were read off the recorded API pages in tests/fixtures/scriptures/.
"""
import json
import re
import shutil
import sqlite3

from tests.scripture_world import API_DIR, VOLUMES, WORLD_PAGES, need_core_db, q, q1, run_script

ALMA_32_21 = ("And now as I said concerning faith—faith is not to have a perfect knowledge of things; "
              "therefore if ye have faith ye hope for things which are not seen, which are true.")
NEPHI_3_7 = ("And it came to pass that I, Nephi, said unto my father: I will go and do the things which the "
             "Lord hath commanded, for I know that the Lord giveth no commandments unto the children of men, "
             "save he shall prepare a way for them that they may accomplish the thing which he commandeth them.")


def verses_of(db, page_uri):
    return q(db, """SELECT v.verse, v.text, v.text_html, v.aid, v.pid_html_id, v.verse_id
                    FROM verse v JOIN chapter c ON c.chapter_id = v.chapter_id
                    JOIN page p ON p.page_id = c.page_id WHERE p.uri = ? ORDER BY v.verse""", (page_uri,))


def chapter_of(db, page_uri):
    rows = q(db, """SELECT c.number, c.title, c.summary, c.intro FROM chapter c JOIN page p ON p.page_id=c.page_id
                    WHERE p.uri=?""", (page_uri,))
    assert rows, f"no chapter row for {page_uri}"
    return rows[0]


def refs_of(db, page_uri, note_key):
    return q(db, """SELECT r.category, r.href, r.label, r.target_book_id, r.target_chapter, r.target_verse_start,
                           r.target_verse_end, r.target_help, b.uri, r.target_uri
                    FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id
                    JOIN verse v ON v.verse_id = f.verse_id JOIN chapter c ON c.chapter_id = v.chapter_id
                    JOIN page p ON p.page_id = c.page_id LEFT JOIN book b ON b.book_id = r.target_book_id
                    WHERE p.uri = ? AND f.note_key = ? ORDER BY r.seq""", (page_uri, note_key))


CANON_PAGES = [f"/scriptures/{v}/{p}" for v in VOLUMES for p in WORLD_PAGES[v]]


def _raw(uri):
    return json.loads((API_DIR / (uri.strip("/").replace("/", "__") + ".json")).read_text())


def test_verses_match_the_page_html(built_db):
    for uri in CANON_PAGES:
        body = _raw(uri)["content"]["body"]
        expected = [int(n) for n in re.findall(r'<p class="verse[" ][^>]*id="p(\d+)"', body)]
        got = [r[0] for r in verses_of(built_db, uri)]
        assert got == expected, f"{uri}: verses {got[:5]}…({len(got)}) != page's {len(expected)} <p class=verse>"
    assert [r[0] for r in verses_of(built_db, "/scriptures/bofm/alma/32")] == list(range(1, 44))


def test_verse_text_is_clean_and_html_is_kept(built_db):
    v = {r[0]: r for r in verses_of(built_db, "/scriptures/bofm/alma/32")}
    assert v[21][1] == ALMA_32_21, f"Alma 32:21 text was {v[21][1]!r}"
    assert "study-note-ref" in v[21][2] or "<" in v[21][2], "text_html must keep the markup"
    assert v[21][3] == "128351643" and v[21][4] == "p21", "aid = data-aid, pid_html_id = html id"
    n = {r[0]: r for r in verses_of(built_db, "/scriptures/bofm/1-ne/3")}
    assert n[7][1] == NEPHI_3_7
    bad = q(built_db, "SELECT verse_id, text FROM verse WHERE text LIKE '%<%' OR text LIKE '%>%' "
                      "OR text GLOB '[0-9]*' OR text = '' LIMIT 5")
    assert not bad, f"verse.text must be plain (no HTML, verse numbers, markers): {bad}"


def test_footnotes_match_and_resolve(built_db):
    for uri in CANON_PAGES:
        fn = _raw(uri)["content"].get("footnotes") or {}
        got = q1(built_db, """SELECT COUNT(*) FROM footnote f JOIN verse v ON v.verse_id=f.verse_id
                              JOIN chapter c ON c.chapter_id=v.chapter_id JOIN page p ON p.page_id=c.page_id
                              WHERE p.uri=?""", (uri,))
        assert got == len(fn), f"{uri}: {got} footnotes stored, page has {len(fn)}"
    orphans = q1(built_db, "SELECT COUNT(*) FROM footnote WHERE verse_id NOT IN (SELECT verse_id FROM verse)")
    assert orphans == 0, f"{orphans} footnotes whose verse_id does not resolve"
    row = q(built_db, """SELECT f.marker, f.letter, f.context FROM footnote f JOIN verse v ON v.verse_id=f.verse_id
                         JOIN chapter c ON c.chapter_id=v.chapter_id JOIN page p ON p.page_id=c.page_id
                         WHERE p.uri='/scriptures/bofm/alma/32' AND f.note_key='note21_a'""")
    assert row and row[0] == ("21a", "a", "faith"), f"Alma 32 note21_a stored as {row}"


def test_footnote_refs_come_from_href(built_db):
    r = refs_of(built_db, "/scriptures/bofm/alma/32", "note21_a")
    assert len(r) == 2, f"note21_a should have 2 refs (John 20:29, Heb. 11:1–40), got {r}"
    assert r[0][4:7] == (20, 29, 29) and "john" in (r[0][8] or ""), f"John 20:29 ref resolved as {r[0]}"
    # Hebrews is not in the fixture TOC, so no book row — chapter/verses still come from the href
    # (id=p1-p40#p1: storing the range 1–40 or the focus verse 1 are both acceptable)
    assert r[1][4:6] == (11, 1) and r[1][6] in (1, 40) and "/nt/heb/11" in (r[1][9] or ""), \
        f"Heb 11:1 (1–40) ref resolved as {r[1]}"
    tg = refs_of(built_db, "/scriptures/bofm/alma/32", "note21_b")
    assert tg and tg[0][7] == "tg/hope" and tg[0][3] is None, f"TG Hope should be target_help='tg/hope': {tg}"
    # short refs ("6:49") inherit their book from the previous ref — resolved via href, never the label
    m = [x for x in refs_of(built_db, "/scriptures/pgp/moses/1", "note12_b") if x[2] == "6:49"]
    assert m and "moses" in (m[0][8] or "") and m[0][4:6] == (6, 49), f"Moses 1 note12_b '6:49' resolved as {m}"
    j = [x for x in refs_of(built_db, "/scriptures/nt/jude/1", "note3_b") if x[2] == "26:33"]
    assert j and "/bofm/2-ne/26" in (j[0][9] or "") and j[0][4:6] == (26, 33), f"Jude note3_b '26:33' resolved as {j}"
    in_world = {(v, p.split("/")[0]) for v in VOLUMES for p in WORLD_PAGES[v]}
    rows = q(built_db, """SELECT href FROM footnote_ref WHERE href LIKE '%/scriptures/%'
                          AND target_book_id IS NULL AND target_help IS NULL""")
    unresolved = []
    for (href,) in rows:
        m2 = re.search(r"/scriptures/([^/?]+)/([^/?#]+)", href)
        if m2 and (m2.group(1), m2.group(2)) in in_world:
            unresolved.append(href)
    assert not unresolved, f"{len(unresolved)} refs into books that exist but resolved to no book: {unresolved[:5]}"


def test_headings_summaries_and_kinds(built_db):
    num, title, summary, intro = chapter_of(built_db, "/scriptures/bofm/alma/32")
    assert num == 32
    assert summary.startswith("Alma teaches the poor whose afflictions had humbled them") and summary.endswith("About 74 B.C."), summary
    _, _, _, intro45 = chapter_of(built_db, "/scriptures/dc-testament/dc/45")
    assert intro45 and intro45.startswith("Revelation given through Joseph Smith the Prophet to the Church, at Kirtland, Ohio, March 7, 1831."), intro45
    assert "<" not in intro45 and "<" not in summary
    kinds = dict(q(built_db, "SELECT uri, kind FROM page"))
    expect = {"/scriptures/bofm/alma/32": "chapter", "/scriptures/dc-testament/dc/45": "section",
              "/scriptures/dc-testament/od/1": "declaration", "/scriptures/pgp/abr/fac-1": "facsimile",
              "/scriptures/bofm/title-page": "front_matter"}
    wrong = {u: (kinds.get(u), k) for u, k in expect.items() if kinds.get(u) != k}
    assert not wrong, f"page.kind (got, expected): {wrong}"
    assert not verses_of(built_db, "/scriptures/dc-testament/od/1"), "OD 1 has no verses"


def test_books_volumes_and_toc_chapter_counts(built_db):
    vols = {r[0] for r in q(built_db, "SELECT uri FROM volume")}
    assert {f"/scriptures/{v}" for v in VOLUMES} <= vols or set(VOLUMES) <= {u.rsplit('/', 1)[-1] for u in vols}, vols
    # num_chapters is TOC-derived: the fixture TOC lists only Alma 32, so Alma has 1 chapter here
    alma = q(built_db, "SELECT num_chapters, (SELECT COUNT(*) FROM chapter c WHERE c.book_id=b.book_id) FROM book b "
                       "WHERE b.uri LIKE '%/alma' OR b.uri = 'alma' OR b.uri LIKE '%bofm/alma%'")
    assert alma and alma[0] == (1, 1), f"Alma num_chapters/chapters should be (1, 1) from the fixture TOC: {alma}"
    mism = q(built_db, "SELECT uri, num_chapters, (SELECT COUNT(*) FROM chapter c WHERE c.book_id=b.book_id) n "
                       "FROM book b WHERE num_chapters IS NOT NULL AND num_chapters != n")
    assert not mism, f"books whose chapter rows != num_chapters: {mism[:5]}"


def _dump(db):
    conn = sqlite3.connect(db)
    out = {}
    for t in ["volume", "book", "page", "chapter", "verse", "footnote", "footnote_ref"]:
        out[t] = sorted(map(repr, conn.execute(f"SELECT * FROM {t}").fetchall()))
    out["build_id"] = conn.execute("SELECT value FROM build_meta WHERE key='build_id'").fetchone()
    raw = conn.execute("SELECT uri, content_hash FROM raw_page ORDER BY 1, 2").fetchall()
    conn.close()
    return out, raw


def test_build_is_deterministic_and_leaves_raw_alone(tmp_path, built_db, fetched_db):
    first, raw0 = _dump(built_db)
    assert first["build_id"] and first["build_id"][0], "build_meta must hold a build_id"
    db2 = tmp_path / "again.db"
    shutil.copy(built_db, db2)
    code, out = run_script("build_scriptures.py", "--db", db2)
    assert code == 0, out[-1500:]
    second, raw1 = _dump(db2)
    assert raw0 == raw1, "build must not touch raw_page"
    diff = [t for t in first if first[t] != second[t]]
    assert not diff, f"rebuilding the same raw data changed: {diff}"


def test_missing_toc_page_fails_the_build(tmp_path, fetched_db):
    need_core_db()  # without core.db the build fails for another reason
    db = tmp_path / "missing.db"
    shutil.copy(fetched_db, db)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM raw_page WHERE uri='/scriptures/bofm/enos/1'")
    conn.commit()
    conn.close()
    code, out = run_script("build_scriptures.py", "--db", db)
    assert code != 0, "a TOC link with no raw row must fail the build"
    assert "enos/1" in out, "the missing URI must be listed"


def test_jst_build_checks_report_and_ex_7_3(tmp_path, fetched_db):
    """Report F rows nothing reaches; KJV Ex 7:3 must link to JST Ex 7:3 (fatal when missing)."""
    need_core_db()
    db = tmp_path / "jstcheck.db"
    shutil.copy(fetched_db, db)
    code, out = run_script("build_scriptures.py", "--db", db)
    assert code == 0, out[-1500:]
    assert "jst_verse F rows no jst footnote or appendix passage names:" in out, out[-1500:]
    assert "KJV Ex 7:3 -> JST Ex 7:3: linked" in out, out[-1500:]

    # the same check, run on the built store with the Ex 7:3 link removed, must be an error
    import importlib.util
    import sys
    from pathlib import Path
    scripts = str(Path(__file__).parent.parent / "scripts")
    sys.path.insert(0, scripts)
    try:
        spec = importlib.util.spec_from_file_location("build_scriptures_under_test", Path(scripts) / "build_scriptures.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(scripts)
    conn = sqlite3.connect(db)
    b = mod.Builder(conn, {}, [])
    b.jst_checks()
    assert not b.errors, b.errors
    conn.execute("""DELETE FROM footnote_ref WHERE category='jst' AND footnote_id IN (
                    SELECT f.footnote_id FROM footnote f JOIN verse v USING (verse_id)
                    JOIN chapter c ON c.chapter_id=v.chapter_id JOIN page p ON p.page_id=c.page_id
                    WHERE p.uri='/scriptures/ot/ex/7' AND v.verse=3)""")
    b = mod.Builder(conn, {}, [])
    b.jst_checks()
    conn.close()
    assert any("Ex 7:3" in e for e in b.errors), f"a missing Ex 7:3 link must fail the build: {b.errors}"
