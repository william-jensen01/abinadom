"""get_verse(include_citing_talks=True) on the fixture scripture store and a small synthetic core.db."""
import sqlite3

import pytest

import db as db_pkg
from db import Database
from db.scripture import open_scripture_db
from tools.scripture_tools import ScriptureStore, get_verse


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


def test_flags_order_and_untitled_count(store, core):
    r = get_verse(store, "Alma", 32, 21, include_citing_talks=True)
    assert r["citing_talks"] == [
        {"talk_id": "talk_2", "title": "Discourse", "date": "1860-01-01", "cites": ["Alma 32:21"],
         "get_talk_available": False},                  # titled, but no conference_talk row
        {"talk_id": "talk_1", "title": "Conference talk", "date": "2001-04-01", "cites": ["Alma 32:21"],
         "get_talk_available": True},
    ]                                                   # oldest first
    assert r["untitled_talks_omitted"] == 2             # empty and NULL titles


def test_no_untitled_key_when_none_omitted(store, core):
    assert "untitled_talks_omitted" not in get_verse(store, "Exodus", 7, 3, include_citing_talks=True)


def test_kjv_verse_matches_flag_j_through_its_jst_footnote(store, core):
    # talk 1 cites Ex. 7:3 itself; talk 5 cites only JST Ex. 7:3 (same numbers, Flag='J')
    r = get_verse(store, "Exodus", 7, 3, include_citing_talks=True)
    assert [(t["talk_id"], t["cites"]) for t in r["citing_talks"]] == \
        [("talk_1", ["Ex. 7:3"]), ("talk_5", ["JST Ex. 7:3"])]
    # JST numbering input matches Flag='J' citations only
    j = get_verse(store, "JST Exodus", 7, 3, include_citing_talks=True)
    assert [(t["talk_id"], t["cites"]) for t in j["citing_talks"]] == [("talk_5", ["JST Ex. 7:3"])]


def test_default_has_no_citing_talks(store, core):
    assert "citing_talks" not in get_verse(store, "Alma", 32, 21)


def test_core_db_unavailable(store, tmp_path, monkeypatch):
    monkeypatch.setattr(db_pkg, "core_db", Database(str(tmp_path / "missing.db")))
    r = get_verse(store, "Alma", 32, 21, include_citing_talks=True)
    assert r["citing_talks"] == [] and "not available" in r["citing_talks_note"]
    assert r["verses"][0]["verse"] == 21                # the verses still come back
