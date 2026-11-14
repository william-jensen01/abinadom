"""get_verse(include_citing_talks=True) counts and get_citing_talks on the fixture scripture store and a small synthetic core.db."""
import sqlite3

import pytest

import db as db_pkg
from db import Database
from db.scripture import open_scripture_db
from tests.scripture_world import core_select, need_core_db
from tools.scripture_tools import ScriptureStore, get_citing_talks, get_verse


@pytest.fixture(scope="module")
def store(built_db):
    return ScriptureStore.open(open_scripture_db(str(built_db)))


@pytest.fixture()
def core(tmp_path, store, monkeypatch):
    """A core.db with citations of Alma 32:21 (a titled conference talk, a titled non-conference talk, two untitled
    ones) and of Ex. 7:3, both as a KJV citation and as a JST citation (Flag='J') of JST Ex. 7:3, the verse that
    Exodus 7:3's `jst` footnote names. It replaces the shared core_db for the test."""
    jst = get_verse(store, "Exodus", 7, 3, include_jst=True)["verses"][0]["jst"]
    assert "JST Ex. 7:3" in [j["reference"] for j in jst]
    alma = store.resolver.resolve("Alma")[0]["core_book_id"]
    ex = store.resolver.resolve("Exodus")[0]["core_book_id"]
    path = tmp_path / "core.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE talk (ID INTEGER PRIMARY KEY, Corpus TEXT, Title TEXT, Date TEXT);
        CREATE TABLE citation (ID INTEGER PRIMARY KEY, TalkID INT, BookID INT, Chapter INT, Flag TEXT);
        CREATE TABLE citation_verse (CitationID INT, Verse INT);
        CREATE TABLE conference_talk (TalkID INT, SessionID INT, Sequence INT);
        INSERT INTO talk VALUES (1,'G','Conference talk','2001-04-01'), (2,'J','Discourse','1860-01-01'),
                                (3,'T','',NULL), (4,'T',NULL,NULL), (5,'G','Cites JST','2010-10-01');
        INSERT INTO conference_talk VALUES (1,1,1), (5,1,2);
    """)
    c.executemany("INSERT INTO citation VALUES (?,?,?,?,?)",
                  [(1, 1, alma, 32, ""), (2, 2, alma, 32, None), (3, 3, alma, 32, ""), (4, 4, alma, 32, ""),
                   (5, 5, ex, 7, "J"), (6, 1, ex, 7, "")])
    c.executemany("INSERT INTO citation_verse VALUES (?,?)", [(1, 21), (2, 21), (3, 21), (4, 21), (5, 3), (6, 3)])
    c.commit()
    c.close()
    monkeypatch.setattr(db_pkg, "core_db", Database(str(path)))
    return path


def test_get_verse_returns_counts_not_talks(store, core):
    r = get_verse(store, "Alma", 32, 21, include_citing_talks=True)
    assert r["citing_talks_count"] == 2                 # titled talks only: 1 and 2
    assert r["untitled_talks_omitted"] == 2             # empty and NULL titles
    assert "citing_talks" not in r and "citing_talks_by_verse" not in r   # one verse: no breakdown


def test_get_verse_range_counts_per_verse(store, core):
    r = get_verse(store, "Exodus", 7, 3, 4, include_citing_talks=True)
    assert r["citing_talks_count"] == 2                 # talk 1 (KJV) and talk 5 (JST), each once
    assert r["citing_talks_by_verse"] == [{"reference": "Ex. 7:3", "count": 2}, {"reference": "Ex. 7:4", "count": 0}]
    r = get_verse(store, "Alma", 32, 21, 22, include_citing_talks=True)
    assert [v["count"] for v in r["citing_talks_by_verse"]] == [2, 0] and r["citing_talks_count"] == 2


def test_no_untitled_key_when_none_omitted(store, core):
    assert "untitled_talks_omitted" not in get_verse(store, "Exodus", 7, 3, include_citing_talks=True)
    assert "untitled_talks_omitted" not in get_citing_talks(store, "Exodus", 7, 3)


def test_default_has_no_citing_talks(store, core):
    r = get_verse(store, "Alma", 32, 21)
    assert "citing_talks_count" not in r and "citing_talks" not in r


def test_get_citing_talks_newest_first_with_flags_and_untitled_count(store, core):
    r = get_citing_talks(store, "Alma", 32, 21)
    assert r["citing_talks"] == [
        {"talk_id": "talk_1", "title": "Conference talk", "date": "2001-04-01", "cites": ["Alma 32:21"],
         "get_talk_available": True},
        {"talk_id": "talk_2", "title": "Discourse", "date": "1860-01-01", "cites": ["Alma 32:21"],
         "get_talk_available": False},                  # titled, but no conference_talk row
    ]
    assert (r["reference"], r["total"], r["offset"], r["limit"], r["next_offset"]) == ("Alma 32:21", 2, 0, 25, None)
    assert r["untitled_talks_omitted"] == 2
    assert [t["talk_id"] for t in get_citing_talks(store, "Alma", 32, 21, order="oldest")["citing_talks"]] == \
        ["talk_2", "talk_1"]
    assert "order must be" in get_citing_talks(store, "Alma", 32, 21, order="random")


def test_paging_and_limit_cap(store, core):
    first = get_citing_talks(store, "Alma", 32, 21, limit=1)
    assert [t["talk_id"] for t in first["citing_talks"]] == ["talk_1"]
    assert (first["total"], first["next_offset"]) == (2, 1)
    last = get_citing_talks(store, "Alma", 32, 21, limit=1, offset=first["next_offset"])
    assert [t["talk_id"] for t in last["citing_talks"]] == ["talk_2"] and last["next_offset"] is None
    assert get_citing_talks(store, "Alma", 32, 21, limit=5000)["limit"] == 100
    past = get_citing_talks(store, "Alma", 32, 21, offset=10)
    assert past["citing_talks"] == [] and past["total"] == 2 and past["next_offset"] is None


def test_conference_only(store, core):
    r = get_citing_talks(store, "Alma", 32, 21, conference_only=True)
    assert [t["talk_id"] for t in r["citing_talks"]] == ["talk_1"] and r["total"] == 1


def test_kjv_verse_matches_flag_j_through_its_jst_footnote(store, core):
    # talk 1 cites Ex. 7:3 itself; talk 5 cites only JST Ex. 7:3 (same numbers, Flag='J')
    r = get_citing_talks(store, "Exodus", 7, 3, order="oldest")
    assert [(t["talk_id"], t["cites"]) for t in r["citing_talks"]] == \
        [("talk_1", ["Ex. 7:3"]), ("talk_5", ["JST Ex. 7:3"])]
    # JST numbering input matches Flag='J' citations only
    j = get_citing_talks(store, "JST Exodus", 7, 3)
    assert [(t["talk_id"], t["cites"]) for t in j["citing_talks"]] == [("talk_5", ["JST Ex. 7:3"])]
    assert get_verse(store, "JST Exodus", 7, 3, include_citing_talks=True)["citing_talks_count"] == 1


def test_messages_for_unknown_book_and_missing_verse(store, core):
    assert "Unknown book" in get_citing_talks(store, "Hezekiah", 1)
    assert get_citing_talks(store, "Alma", 32, 500).startswith("No verse 500 in")


def test_core_db_unavailable(store, tmp_path, monkeypatch):
    monkeypatch.setattr(db_pkg, "core_db", Database(str(tmp_path / "missing.db")))
    r = get_verse(store, "Alma", 32, 21, include_citing_talks=True)
    assert r["citing_talks_count"] == 0 and "not available" in r["citing_talks_note"]
    assert r["verses"][0]["verse"] == 21                # the verses still come back
    p = get_citing_talks(store, "Alma", 32, 21)
    assert p["citing_talks"] == [] and "not available" in p["citing_talks_note"]


# ---------------------------------------------------------------------------
# Against the real core.db (skipped when it is missing)
# ---------------------------------------------------------------------------

def _all_talks(store, *args, **kw):
    """Every talk get_citing_talks returns for these verses, paging until next_offset is null; (ids, talks, pages)."""
    talks, pages, offset = [], [], 0
    while offset is not None:
        page = get_citing_talks(store, *args, limit=40, offset=offset, **kw)
        pages.append(page)
        talks += page["citing_talks"]
        offset = page["next_offset"]
    return {int(t["talk_id"][5:]) for t in talks}, talks, pages


def test_real_core_kjv_citations_of_a_verse(store):
    need_core_db()
    john = core_select("SELECT ID FROM book WHERE FullName='John'")[0]["ID"]
    exact = {r["TalkID"] for r in core_select(
        """SELECT DISTINCT c.TalkID FROM citation c JOIN citation_verse cv ON cv.CitationID=c.ID
           WHERE c.BookID=? AND c.Chapter=3 AND cv.Verse=16 AND IFNULL(c.Flag,'') != 'J'""", (john,))}
    loose = {r["TalkID"] for r in core_select(
        """SELECT DISTINCT TalkID FROM citation WHERE BookID=? AND Chapter=3 AND MinVerse<=16 AND MaxVerse>=16
           AND IFNULL(Flag,'') != 'J'""", (john,))}
    assert exact, "core.db should have talks citing John 3:16"
    got, talks, pages = _all_talks(store, "John", 3, 16)
    assert exact <= got <= (loose | exact)
    assert len(got) == len(talks), "no talk appears on two pages"
    assert all(t.get("title") for t in talks), "each citing talk carries its title"
    assert all(p["total"] == len(got) for p in pages)
    assert get_verse(store, "John", 3, 16, include_citing_talks=True)["citing_talks_count"] == len(got)
    assert "citing_talks_count" not in get_verse(store, "John", 3, 16), "include_citing_talks defaults to False"


def test_real_core_jst_citations_use_jst_numbering(store):
    need_core_db()
    rows = core_select("""SELECT c.TalkID, c.Chapter, c.MinVerse, b.FullName FROM citation c JOIN book b ON b.ID=c.BookID
                          WHERE c.Flag='J' AND c.MinVerse = c.MaxVerse AND b.FullName IN ('Genesis','John','Exodus')
                          ORDER BY c.ID LIMIT 3""")
    assert rows, "core.db has no single-verse Flag='J' citations in Genesis/Exodus/John"
    for row in rows:
        got, _, _ = _all_talks(store, f"JST {row['FullName']}", row["Chapter"], row["MinVerse"])
        assert row["TalkID"] in got, f"JST {row['FullName']} {row['Chapter']}:{row['MinVerse']} must list talk {row['TalkID']}"


def test_cites_merge_consecutive_verses_into_ranges(store, core):
    alma = store.resolver.resolve("Alma")[0]["core_book_id"]
    c = sqlite3.connect(core)
    c.execute("INSERT INTO citation VALUES (10, 2, ?, 32, '')", (alma,))
    c.executemany("INSERT INTO citation_verse VALUES (10, ?)", [(20,), (21,), (22,), (24,)])
    c.commit()
    c.close()
    r = get_citing_talks(store, "Alma", 32, 20, 24)
    cites = {t["talk_id"]: t["cites"] for t in r["citing_talks"]}
    assert cites["talk_2"] == ["Alma 32:20–22", "Alma 32:24"]      # 23 is not cited: two runs
    assert cites["talk_1"] == ["Alma 32:21"]                         # a single verse stays a single verse


def test_merged_cites_examples_and_standard_never_merged_with_jst():
    from tools.scripture_tools import _merged_cites
    john = {("", 9, 3, v): f"John 3:{v}" for v in range(14, 18)}
    jst = {("J", 1, 14, v): f"JST Gen. 14:{v}" for v in range(17, 41)}
    assert _merged_cites(set(john), john) == ["John 3:14–17"]
    assert _merged_cites(set(jst), jst) == ["JST Gen. 14:17–40"]
    mixed = {("", 1, 14, 17): "Gen. 14:17", ("", 1, 14, 18): "Gen. 14:18", **jst}
    assert _merged_cites(set(mixed), mixed) == ["Gen. 14:17–18", "JST Gen. 14:17–40"]
    other_chapter = {("", 9, 3, 17): "John 3:17", ("", 9, 4, 18): "John 4:18"}
    assert _merged_cites(set(other_chapter), other_chapter) == ["John 3:17", "John 4:18"]
