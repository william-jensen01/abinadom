"""get_verse / get_chapter_overview (tools/scripture_tools.py) and the book resolver, on the fixture store built
from the recorded Church API pages. Pure SQLite reads: no Weaviate, no embedder."""
import json

import pytest

from db.scripture import open_scripture_db
from tools.scripture_tools import ScriptureStore, get_chapter_overview, get_verse


@pytest.fixture(scope="module")
def store(built_db):
    db = open_scripture_db(str(built_db))
    assert db is not None
    return ScriptureStore.open(db)


def test_resolver_inputs(store):
    def uri(text):
        found = store.resolver.resolve(text)
        return found and (found[0]["uri"], found[1])

    for text in ("1 Nephi", "First Nephi", "1 Ne.", "1 ne", "1 NEPHI", "i nephi", "1st Nephi", "1ne"):
        assert uri(text) == ("/scriptures/bofm/1-ne", False), text
    for text in ("D&C", "d&c", "Doctrine and Covenants", "doctrine & covenants", "Sections"):
        b, _ = store.resolver.resolve(text)
        assert b["uri"] == "/scriptures/dc-testament/dc" and b["cite_abbr"] == "D&C" and b["core_book_id"] == 302, text
        assert b["display_name"] == "Doctrine and Covenants" and b["name"] == "Sections"
    assert uri("Psalm") == ("/scriptures/ot/ps", False)
    assert uri("Joseph Smith History") == uri("JS-H") == ("/scriptures/pgp/js-h", False)
    for text in ("JST Genesis", "jst gen.", "Joseph Smith Translation Genesis", "JST Gen"):
        assert uri(text) == ("/scriptures/ot/gen", True), text
    assert uri("Hezekiah") is None and uri("") is None


def test_missing_or_bad_file_is_none(tmp_path):
    assert open_scripture_db(str(tmp_path / "nope.db")) is None
    (tmp_path / "empty.db").write_bytes(b"")
    assert open_scripture_db(str(tmp_path / "empty.db")) is None
    (tmp_path / "junk.db").write_bytes(b"not sqlite" * 100)
    assert open_scripture_db(str(tmp_path / "junk.db")) is None


def test_verse_range_footnotes_and_shorthand(store):
    r = get_verse(store, "Alma", 32, 20, 22)
    assert r["reference"] == "Alma 32:20–22" and [v["verse"] for v in r["verses"]] == [20, 21, 22]
    notes = {f["marker"]: f for f in r["verses"][1]["footnotes"]}
    assert [x["target"] for x in notes["21a"]["refs"]] == ["John 20:29", "Heb. 11:1–40"]
    assert notes["21b"]["refs"][0]["target"] == "tg/hope"
    assert "footnotes" not in get_verse(store, "Alma", 32, 21, include_footnotes=False)["verses"][0]
    jude = get_verse(store, "Jude", 3)
    assert jude["reference"] == "Jude 1:3" and [v["verse"] for v in jude["verses"]] == [3]
    assert get_verse(store, "Jude", 1)["reference"] == "Jude 1"
    json.dumps(r)


def test_messages(store):
    assert "Unknown book" in get_verse(store, "Hezekiah", 1)
    assert "No chapter 99" in get_verse(store, "Alma", 99, 1)
    assert "No verses" in get_verse(store, "Alma", 32, 500)
    assert "before" in get_verse(store, "Alma", 32, 5, 3)
    assert "Unknown book" in get_chapter_overview(store, "Hezekiah", 1)
    assert "No chapter" in get_chapter_overview(store, "Alma", 99)


def test_jst_by_footnote_appendix_and_numbering(store):
    ex = get_verse(store, "Exodus", 7, 3, include_jst=True)["verses"][0]
    assert "JST Ex. 7:3" in [j["reference"] for j in ex["jst"]]
    gen = get_verse(store, "Genesis", 9, 5, include_jst=True)["verses"][0]
    assert [j["reference"] for j in gen["jst"]] == [f"JST Gen. 9:{n}" for n in range(10, 16)]
    assert "jst" not in get_verse(store, "Genesis", 9, 5)["verses"][0]
    j = get_verse(store, "JST Genesis", 8, 19)
    assert j["reference"] == "JST Gen. 8:19" and j["verses"][0]["reference"] == "JST Gen. 8:19"
    assert get_verse(store, "Genesis", 8, 19, numbering="jst")["reference"] == "JST Gen. 8:19"
    assert "No JST verses" in get_verse(store, "JST Alma", 32, 21)


def test_chapter_overview(store):
    a = get_chapter_overview(store, "Alma", 32)
    assert a["reference"] == "Alma 32" and a["verse_count"] == 43 and a["summary"].startswith("Alma teaches")
    counts = [t["count"] for t in a["top_cross_references"]]
    assert counts and counts == sorted(counts, reverse=True) and len(counts) <= 10
    assert all(isinstance(t["reference"], str) for t in a["top_cross_references"])
    d = get_chapter_overview(store, "Doctrine and Covenants", 45)
    assert d["reference"] == "D&C 45" and "Revelation given through Joseph Smith" in d["intro"]
