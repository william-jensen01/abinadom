"""M1 build-full — build_scriptures.py on the real raw store passes every §10 build check.

Runs on a temp copy of db/scripture.db (never the real file); skips when that store or core.db is missing.
Independent reference: published verse totals of the LDS standard works.
"""
import json
import re

import pytest

from tests.scripture_world import q, q1

EXPECTED_VERSES = {"ot": 23145, "nt": 7957, "bofm": 6604, "dc-testament": 3654, "pgp": 635}
SPOT = {  # (page uri, verse): text must start with
    ("/scriptures/nt/john/3", 16): "For God so loved the world, that he gave his only begotten Son",
    ("/scriptures/bofm/alma/32", 21): "And now as I said concerning faith—faith is not to have a perfect knowledge",
    ("/scriptures/bofm/1-ne/3", 7): "And it came to pass that I, Nephi, said unto my father: I will go and do",
    ("/scriptures/dc-testament/dc/45", 32): "But my disciples shall stand in holy places",
}


@pytest.fixture
def full(full_built):
    return full_built


def test_verse_totals_per_volume(full):
    db, _ = full
    rows = q(db, """SELECT p.uri FROM verse v JOIN chapter c ON c.chapter_id=v.chapter_id
                    JOIN page p ON p.page_id=c.page_id""")
    got = {}
    for (u,) in rows:
        vol = u.split("/")[2]
        got[vol] = got.get(vol, 0) + 1
    print("canonical verses per volume:", got)
    assert {k: got.get(k) for k in EXPECTED_VERSES} == EXPECTED_VERSES, f"verses per volume {got} != {EXPECTED_VERSES}"
    assert not (set(got) - set(EXPECTED_VERSES)), f"verse rows outside the five volumes: {set(got) - set(EXPECTED_VERSES)}"


def test_every_chapter_runs_1_to_n_and_matches_its_html(full):
    db, _ = full
    pages = q(db, """SELECT p.uri, r.json FROM page p JOIN raw_latest r ON r.uri=p.uri AND r.lang='eng'
                     WHERE p.uri NOT LIKE '/scriptures/jst/%'""")
    bad = []
    for uri, js in pages:
        body = json.loads(js)["content"]["body"]
        expected = [int(n) for n in re.findall(r'<p class="verse[" ][^>]*id="p(\d+)"', body)]
        got = [r[0] for r in q(db, """SELECT v.verse FROM verse v JOIN chapter c ON c.chapter_id=v.chapter_id
                                      JOIN page p ON p.page_id=c.page_id WHERE p.uri=? ORDER BY v.verse""", (uri,))]
        if got != expected or (got and got != list(range(1, len(got) + 1))):
            bad.append(uri)
    assert not bad, f"{len(bad)} pages whose verses are not the page's 1..N <p class=verse>: {bad[:8]}"


def test_footnotes_are_complete_and_resolve(full):
    db, _ = full
    expected = other = 0
    for (js,) in q(db, "SELECT r.json FROM page p JOIN raw_latest r ON r.uri=p.uri AND r.lang='eng' "
                       "WHERE p.uri NOT LIKE '/scriptures/jst/%'"):
        c = json.loads(js)["content"]
        aids = set(re.findall(r'<p class="verse[^"]*" data-aid="(\d+)"', c["body"]))
        for f in (c.get("footnotes") or {}).values():
            if f.get("pid") in aids:
                expected += 1
            else:
                other += 1
    got = q1(db, "SELECT COUNT(*) FROM footnote WHERE verse_id IS NOT NULL")
    print("verse footnotes:", got, "expected:", expected, "(non-verse footnotes in raw:", other, ")")
    assert got == expected, f"{got} footnotes stored, raw pages have {expected}"
    assert q1(db, "SELECT COUNT(*) FROM footnote WHERE verse_id NOT IN (SELECT verse_id FROM verse)") == 0
    total = q1(db, "SELECT COUNT(*) FROM footnote_ref WHERE href LIKE '%/scriptures/%' AND href NOT LIKE '%/scriptures/jst/%'")
    unresolved = q1(db, """SELECT COUNT(*) FROM footnote_ref WHERE href LIKE '%/scriptures/%'
                           AND href NOT LIKE '%/scriptures/jst/%' AND target_book_id IS NULL AND target_help IS NULL""")
    print(f"scripture refs: {total}, unresolved: {unresolved}")
    assert total > 50000, f"only {total} scripture refs — footnote_ref looks incomplete"
    assert unresolved <= total * 0.001, f"{unresolved}/{total} scripture refs resolve to neither a book nor a study help"


def test_text_is_clean_everywhere(full):
    db, _ = full
    bad = q(db, "SELECT verse_id, substr(text,1,60) FROM verse WHERE text LIKE '%<%' OR text LIKE '%>%' "
                "OR text GLOB '[0-9]*' OR trim(text) = '' LIMIT 5")
    assert not bad, f"verse.text with HTML / verse numbers / empty: {bad}"


def test_spot_checks_and_chapter_counts(full):
    db, _ = full
    for (uri, n), start in SPOT.items():
        t = q1(db, """SELECT v.text FROM verse v JOIN chapter c ON c.chapter_id=v.chapter_id
                      JOIN page p ON p.page_id=c.page_id WHERE p.uri=? AND v.verse=?""", (uri, n))
        assert t and t.startswith(start), f"{uri}:{n} = {t!r}"
    mism = q(db, "SELECT uri, num_chapters, (SELECT COUNT(*) FROM chapter c WHERE c.book_id=b.book_id) n "
                 "FROM book b WHERE num_chapters != n")
    assert not mism, f"books whose chapter rows != TOC num_chapters: {mism[:5]}"
    assert q1(db, "SELECT COUNT(*) FROM chapter WHERE page_id IN (SELECT page_id FROM page WHERE uri='/scriptures/ot/ps/119')") == 1
    assert q1(db, "SELECT value FROM build_meta WHERE key='build_id'"), "build_meta.build_id missing"
