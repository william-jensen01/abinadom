"""JST import from core.db and the Church's own JST links, on the fixture store.

Needs the user-built core db (db/core.<SCI_DB_VERSION>.db); read only through db.Database.
"""

from tests.scripture_world import core_scalar, core_select, need_core_db, q, q1


def _core_book_id(name):
    rows = core_select("SELECT ID FROM book WHERE FullName = ?", (name,))
    assert rows, f"core.db book {name!r} not found"
    return rows[0]["ID"]


def _jst_targets(db, page_uri, note_key):
    """(jst chapter, jst verse, source_flag, core_id, text) for every jst-category ref of one footnote."""
    return q(db, """SELECT j.chapter, j.verse, j.source_flag, j.core_id, j.text
                    FROM footnote_ref r JOIN footnote f ON f.footnote_id=r.footnote_id
                    JOIN verse v ON v.verse_id=f.verse_id JOIN chapter c ON c.chapter_id=v.chapter_id
                    JOIN page p ON p.page_id=c.page_id JOIN jst_verse j ON j.jst_verse_id=r.target_jst_verse_id
                    WHERE p.uri=? AND f.note_key=? AND r.category='jst' ORDER BY j.chapter, j.verse""",
             (page_uri, note_key))


def _core_text(core_id):
    rows = core_select("SELECT Text FROM scripture WHERE ID = ?", (core_id,))
    t = rows[0]["Text"]
    return (t.decode("utf-8") if isinstance(t, (bytes, bytearray)) else t).strip()


def test_every_jf_row_is_imported(built_db):
    need_core_db()
    jf = core_scalar("SELECT COUNT(*) FROM scripture WHERE Flag IN ('J','F')")
    f = core_scalar("SELECT COUNT(*) FROM scripture WHERE Flag = 'F'")
    got = q1(built_db, "SELECT COUNT(*) FROM jst_verse")
    got_f = q1(built_db, "SELECT COUNT(*) FROM jst_verse WHERE source_flag='F'")
    assert (got, got_f) == (jf, f), f"jst_verse rows (all, F) = {(got, got_f)}, core.db J+F = {(jf, f)}"
    assert q1(built_db, "SELECT COUNT(DISTINCT core_id) FROM jst_verse") == jf, "core_id must be unique per JST row"


def test_jst_numbering_is_kept(built_db):
    gen = _core_book_id("Genesis")
    core = core_select("SELECT ID, Text FROM scripture WHERE BookID=? AND Chapter=8 AND Verse=19 AND Flag IN ('J','F')", (gen,))
    assert core, "core.db has no JST Genesis 8:19"
    row = q(built_db, "SELECT chapter, verse, text FROM jst_verse WHERE core_id=?", (core[0]["ID"],))
    assert row and row[0][:2] == (8, 19), f"JST Gen 8:19 must stay 8:19 in JST numbering, got {row}"
    assert row[0][2].strip() == _core_text(core[0]["ID"]), "jst_verse.text must be core.db's text, decoded, unchanged"
    assert "ark" in row[0][2].lower(), "JST Gen 8:19 is the ark verse (KJV Gen 6:14)"


def test_church_jst_footnotes_link_kjv_to_jst(built_db):
    need_core_db()
    ex, gen = _core_book_id("Exodus"), _core_book_id("Genesis")
    t = _jst_targets(built_db, "/scriptures/ot/ex/7", "note3_a")
    assert [x[:3] for x in t] == [(7, 3, "F")], f"KJV Ex 7:3 note3_a → {[x[:3] for x in t]}, expected JST Ex 7:3 (F)"
    assert core_select("SELECT BookID FROM scripture WHERE ID=?", (t[0][3],))[0]["BookID"] == ex
    assert "harden his heart" in t[0][4], "JST Ex 7:3 full text comes from core.db (the footnote is abbreviated with …)"

    # numbering differs: KJV Gen 6:6 → JST Gen 8:13
    t = _jst_targets(built_db, "/scriptures/ot/gen/6", "note6_a")
    assert [x[:2] for x in t] == [(8, 13)], f"KJV Gen 6:6 → {[x[:2] for x in t]}, expected JST Gen 8:13"
    assert core_select("SELECT BookID FROM scripture WHERE ID=?", (t[0][3],))[0]["BookID"] == gen

    # ranges: KJV Gen 6:18 → JST Gen 8:23–24; "(Appendix)" notes resolve too: KJV Gen 9:4 → JST Gen 9:10–15
    assert [x[:2] for x in _jst_targets(built_db, "/scriptures/ot/gen/6", "note18_a")] == [(8, 23), (8, 24)]
    assert [x[:2] for x in _jst_targets(built_db, "/scriptures/ot/gen/9", "note4_a")] == [(9, v) for v in range(10, 16)]

    # NT too: John 3:18 → JST John 3:18
    assert [x[:2] for x in _jst_targets(built_db, "/scriptures/nt/john/3", "note18_c")] == [(3, 18)]

    unresolved = q1(built_db, "SELECT COUNT(*) FROM footnote_ref WHERE category='jst' AND target_jst_verse_id IS NULL")
    total = q1(built_db, "SELECT COUNT(*) FROM footnote_ref WHERE category='jst'")
    assert total >= 20, f"only {total} jst-category refs in the fixture store"
    assert unresolved == 0, f"{unresolved}/{total} jst refs did not resolve to a jst_verse"


def test_appendix_pages_are_fetched_and_parsed(built_db):
    for u in ["/scriptures/jst", "/scriptures/jst/jst-ex/4", "/scriptures/jst/jst-gen/9"]:
        assert q1(built_db, "SELECT COUNT(*) FROM raw_latest WHERE uri=? AND status=200", (u,)), \
            f"{u} not fetched — fetch_scriptures.py must also walk the JST appendix TOC"
    assert q1(built_db, "SELECT COUNT(*) FROM page WHERE uri='/scriptures/jst/jst-gen/9'") == 1, "appendix page not parsed into page"
    # appendix verses are JST text, not canonical verses: KJV verse totals must not include them
    assert q1(built_db, """SELECT COUNT(*) FROM verse v JOIN chapter c ON c.chapter_id=v.chapter_id
                           JOIN page p ON p.page_id=c.page_id WHERE p.uri LIKE '/scriptures/jst/%'""") == 0, \
        "JST appendix passages must not become canonical verse rows"
