"""get_verse / get_chapter_overview (tools/scripture_tools.py) and the book resolver, on the fixture store built
from the recorded Church API pages. Pure SQLite reads: no Weaviate, no embedder."""
import json

import pytest

from db.scripture import open_scripture_db
from tests.scripture_world import FULL_DB, need_full_db
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
    assert [j["reference"] for j in gen["jst"]] == ["JST Gen. 9:10–15"]      # one entry per appendix passage
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


# ---------------------------------------------------------------------------
# The same tools through the MCP server (embedded Weaviate, fake embedder, scripture.db copy)
# ---------------------------------------------------------------------------

from tests.scripture_world import blob, call_tools, find_verse  # noqa: E402
from tests.test_scripture_build import ALMA_32_21, NEPHI_3_7  # noqa: E402


def gv(**kw):
    return ("get_verse", kw)


def test_server_get_verse_basics_and_footnotes(loaded):
    _, _, env = loaded
    r, rng, nofn = call_tools(env, [
        gv(book="Alma", chapter=32, verse_start=21),
        gv(book="Alma", chapter=32, verse_start=20, verse_end=22),
        gv(book="Alma", chapter=32, verse_start=21, include_footnotes=False),
    ])
    assert isinstance(r, dict), f"get_verse must return JSON, got {str(r)[:300]}"
    assert r["reference"] == "Alma 32:21", r.get("reference")
    assert r["chapter_summary"].startswith("Alma teaches the poor")
    v = find_verse(r, 21)
    assert v and v["text"] == ALMA_32_21 and v["reference"] == "Alma 32:21"
    fns = {f["marker"]: f for f in v["footnotes"]}
    assert set(fns) == {"21a", "21b", "21c"} and fns["21a"]["context"] == "faith", f"footnotes {list(fns)}"
    labels = [x["label"] for x in fns["21a"]["refs"]]
    assert any("John 20:29" in l for l in labels) and any(x.get("target") for x in fns["21a"]["refs"]), fns["21a"]
    assert [x["verse"] for x in rng["verses"]] == [20, 21, 22], "a range returns its verses in order"
    assert not find_verse(nofn, 21).get("footnotes"), "include_footnotes=False must leave footnotes out"


def test_server_book_resolver_inputs(loaded):
    _, _, env = loaded
    calls = [gv(book=b, chapter=3, verse_start=7) for b in ("1 Nephi", "First Nephi", "1 Ne.", "1 ne", "1 NEPHI")]
    calls += [gv(book=b, chapter=45, verse_start=32) for b in ("D&C", "Doctrine and Covenants", "d&c")]
    calls += [gv(book="Jude", chapter=3), gv(book="Enos", chapter=3), gv(book="Psalms", chapter=23)]
    out = call_tools(env, calls)
    for r in out[:5]:
        assert isinstance(r, dict) and r["reference"] == "1 Ne. 3:7" and find_verse(r, 7)["text"] == NEPHI_3_7, blob(r)[:300]
    for r in out[5:8]:
        assert isinstance(r, dict) and r["reference"] == "D&C 45:32", blob(r)[:300]
        assert find_verse(r, 32)["text"].startswith("But my disciples shall stand in holy places")
    jude, enos, ps = out[8:]
    assert jude["reference"] == "Jude 1:3" and find_verse(jude, 3)["text"].startswith("Beloved, when I gave all diligence"), \
        "single-chapter shorthand: ('Jude', 3) is Jude 1:3"
    assert enos["reference"] == "Enos 1:3"
    assert [v["verse"] for v in ps["verses"]] == list(range(1, 7)), "Psalms 23 (no verses given) returns the whole chapter"


def test_server_include_jst_and_jst_numbering(loaded):
    _, _, env = loaded
    ex, appx, jgen, plain = call_tools(env, [
        gv(book="Exodus", chapter=7, verse_start=3, include_jst=True),
        gv(book="Genesis", chapter=9, verse_start=5, include_jst=True),
        gv(book="JST Genesis", chapter=8, verse_start=19),
        gv(book="Exodus", chapter=7, verse_start=3),
    ])
    j = find_verse(ex, 3).get("jst") or []
    assert any("JST Ex. 7:3" in x["reference"] for x in j), f"include_jst on Ex 7:3: {j}"
    jt = next(x for x in j if "7:3" in x["reference"])["text"]
    assert "harden his heart" in jt and "…" not in jt, "JST text is core.db's full verse, not the footnote's excerpt"
    ja = find_verse(appx, 5).get("jst") or []
    assert ja and all(x["reference"].startswith("JST Gen. 9:") for x in ja), \
        f"KJV Gen 9:5 is linked only by the appendix passage 'JST Gen 9:10–15 compare Gen 9:4–9': {ja}"
    assert isinstance(jgen, dict) and jgen["reference"] == "JST Gen. 8:19" and "ark" in find_verse(jgen, 19)["text"].lower(), \
        f"JST numbering input: {blob(jgen)[:300]}"
    assert not find_verse(plain, 3).get("jst"), "include_jst defaults to False"


def test_server_get_verse_works_without_embedder_and_rejects_nonsense(loaded):
    _, _, env = loaded
    r, bad = call_tools(dict(env, EMBEDDING_URL="http://127.0.0.1:9"), [
        gv(book="John", chapter=3, verse_start=16), gv(book="Hezekiah", chapter=1)])
    assert isinstance(r, dict) and find_verse(r, 16)["text"].startswith("For God so loved the world"), \
        "get_verse reads scripture.db and must work with the embedder down"
    assert not (isinstance(bad, dict) and bad.get("verses")) and "TOOL ERROR" not in blob(bad)[:12], \
        f"an unknown book returns a clear message, not verses or a crash: {blob(bad)[:200]}"


def test_server_chapter_overview(loaded):
    _, _, env = loaded
    a, d = call_tools(env, [("get_chapter_overview", {"book": "Alma", "chapter": 32}),
                            ("get_chapter_overview", {"book": "D&C", "chapter": 45})])
    assert isinstance(a, dict), blob(a)[:300]
    s = blob(a)
    assert a.get("verse_count") == 43 and "Alma teaches the poor" in s, s[:300]
    top = a.get("top_cross_references") or a.get("cross_references") or a.get("most_referenced") or \
        next((v for k, v in a.items() if "ref" in k and isinstance(v, list)), None)
    assert top, f"overview must list the most-referenced cross-ref targets: keys {list(a)}"
    assert "Revelation given through Joseph Smith the Prophet" in blob(d), "D&C overview includes the section intro"


@pytest.fixture(scope="module")
def real_store():
    """The real built store, opened read-only by the tools; skipped when missing or not built."""
    need_full_db()
    db = open_scripture_db(str(FULL_DB))
    if db is None:
        pytest.skip(f"{FULL_DB} is not a built scripture store")
    return ScriptureStore.open(db)


def _jst_count(r):
    return sum(len(v.get("jst", [])) for v in r["verses"])


def _split_full_and_pointers(response):
    """The first entry of each JST reference in a response (in verse order) is the full one; later entries with the
    same reference are pointers. Returns ({reference: {text, holder}}, [pointer entries])."""
    full, pointers = {}, []
    for v in response["verses"]:
        for j in v.get("jst", []):
            if j["reference"] in full:
                pointers.append(j)
            else:
                full[j["reference"]] = {"text": j["text"], "holder": v["reference"]}
    return full, pointers


def test_include_jst_stays_bounded_on_the_real_store(real_store):
    """A big appendix passage (Compare Gen 1:1-6:13 -> 329 JST verses) used to attach to every verse it covers:
    10,199 entries / 2.2 MB for Gen 1."""
    chapter = get_verse(real_store, "Gen", 1, include_jst=True)
    assert _jst_count(chapter) <= 2 * len(chapter["verses"])
    assert len(json.dumps(chapter)) < 200_000
    full, pointers = _split_full_and_pointers(chapter)
    assert pointers, "the big passage covers all of Gen 1, so later verses point back to its first entry"
    for j in pointers:
        f = full[j["reference"]]
        assert j["text"] != f["text"] and len(j["text"]) < 200 and f["holder"] in j["text"]

    one = get_verse(real_store, "Gen", 6, 6, include_jst=True)["verses"][0]["jst"]
    assert len(one) <= 3 and len(json.dumps(one)) < 100_000


def test_include_jst_footnote_targets_first_and_in_full(real_store):
    jst = get_verse(real_store, "Gen", 6, 6, include_jst=True)["verses"][0]["jst"]
    assert jst[0]["reference"] == "JST Gen. 8:13"                    # the Church's own footnote link comes first
    assert jst[0]["text"].startswith("And it repented Noah")
    assert len(jst[0]["text"]) > 50                                    # full text, not a pointer
    assert len(jst) > 1 and jst[1]["reference"] != jst[0]["reference"]   # then the appendix passage, as one entry
    ex = get_verse(real_store, "Exodus", 7, 3, include_jst=True)["verses"][0]["jst"]
    assert ex[0]["reference"] == "JST Ex. 7:3" and len(ex[0]["text"]) > 20


def _jst_refs(response):
    return {v["verse"]: [j["reference"] for j in v.get("jst", [])] for v in response["verses"]}


@pytest.mark.parametrize("book,chapter", [("Ex", 33), ("Ex", 7), ("1 Cor", 7), ("Matt", 4), ("Gen", 9)])
def test_include_jst_chapter_and_single_verse_agree(real_store, book, chapter):
    """A passage with several Compare refs into one chapter reaches the verses under every ref, so a whole-chapter
    response lists, for each verse, the same JST references as that verse asked for alone."""
    whole = _jst_refs(get_verse(real_store, book, chapter, include_jst=True))
    for verse, refs in whole.items():
        assert refs == _jst_refs(get_verse(real_store, book, chapter, verse, include_jst=True))[verse], (book, chapter, verse)


def test_include_jst_passage_with_several_compare_refs(real_store):
    ex = _jst_refs(get_verse(real_store, "Ex", 33, include_jst=True))
    assert "JST Ex. 33:20, 23" in ex[20] and "JST Ex. 33:20, 23" in ex[23]
    cor = _jst_refs(get_verse(real_store, "1 Cor", 7, include_jst=True))
    for v in (1, 5, 26, 29, 38):
        assert "JST 1 Cor. 7:1–2, 5, 26, 29–33, 38" in cor[v], v
    for v in (3, 27):
        assert "JST 1 Cor. 7:1–2, 5, 26, 29–33, 38" not in cor.get(v, []), v
    matt = get_verse(real_store, "Matt", 4, 1, include_jst=True)["verses"][0]["jst"]
    assert "JST Matt. 4:1, 5–6, 8–9" in [j["reference"] for j in matt]    # a gapped passage is cited as printed
