"""Loading the built scripture.db into Weaviate: transforms (pure), then ScriptureLoader and
scripts/run_scripture_pipeline.py against embedded Weaviate with a fake embedder (no network, no real Weaviate)."""
import os
import shutil
import sqlite3

import pytest

from loaders.shared_transforms import prepare_chapter_records, prepare_verse_records
from tests import scripture_world
from tests.scripture_world import EmbedHandler as _Embed, FakeAPI, build_world, q1
from tests.test_scripture_build import ALMA_32_21

VERSES, CHAPTERS, META = "ScriptureVerses", "ScriptureChapters", "ScriptureMeta"
BUILD_ID = "SELECT value FROM build_meta WHERE key='build_id'"


# ---------------------------------------------------------------------------
# Pure transforms
# ---------------------------------------------------------------------------

def _verse(n, chapter=1):
    return dict(book="Enos", book_uri="/scriptures/bofm/enos", cite_abbr="Enos", volume="The Book of Mormon",
                chapter=chapter, verse=n, text=f"text {n}", aid=str(n), footnote_count=0)


def test_window_is_chapter_bounded_and_skip_does_not_shift_it():
    verses = [_verse(n) for n in (1, 2, 3)] + [_verse(1, chapter=2)]
    recs = {r[2]: r[0] for r in prepare_verse_records(verses, [], radius=1)}
    assert recs["verse_/scriptures/bofm/enos_1_1"] == "Enos 1:1\ntext 1\ntext 2"
    assert recs["verse_/scriptures/bofm/enos_1_2"] == "Enos 1:2\ntext 1\ntext 2\ntext 3"
    assert recs["verse_/scriptures/bofm/enos_2_1"] == "Enos 2:1\ntext 1"
    only = prepare_verse_records(verses, [], radius=1, skip=lambda d: not d.endswith("_1_2"))
    assert [(r[2], r[0]) for r in only] == [("verse_/scriptures/bofm/enos_1_2", recs["verse_/scriptures/bofm/enos_1_2"])]
    assert prepare_verse_records(verses, [], radius=0)[1][0] == "Enos 1:2\ntext 2"


def test_jst_verse_is_embedded_alone_and_skipped_records_are_not_embedded():
    jst = [dict(book="Genesis", book_uri="/scriptures/ot/gen", cite_abbr="Gen.", volume="Old Testament", chapter=8,
                verse=13, text="jst text", kjv_refs=["Gen. 6:6"])]
    seen = []
    recs = prepare_verse_records([_verse(1)], jst, embed_fn=lambda t: seen.extend(t) or [[0.0]] * len(t),
                                 skip=lambda d: d.startswith("verse_"))
    assert seen == ["JST Genesis 8:13\njst text"] and len(recs) == 1
    _, meta, doc_id, _ = recs[0]
    assert meta["variant"] == "jst" and meta["reference"] == "JST Gen. 8:13" and meta["kjv_refs"] == ["Gen. 6:6"]
    assert doc_id == "jst_/scriptures/ot/gen_8_13"


def test_chapter_records():
    rows = [dict(page_uri="/scriptures/bofm/alma/32", kind="chapter", number=32, cite_abbr="Alma", book="Alma",
                 volume="The Book of Mormon", title="Alma 32", summary="S", intro=None, verse_count=43),
            dict(page_uri="/scriptures/bofm/title-page", kind="front_matter", number=None, cite_abbr=None, book=None,
                 volume="The Book of Mormon", title="Title Page", summary=None, intro=None, verse_count=0)]
    a, t = prepare_chapter_records(rows)
    assert a[:3] == ("Alma 32: Alma 32\n\nS", a[1], "chapter_/scriptures/bofm/alma/32") and a[1]["reference"] == "Alma 32"
    assert t[1]["reference"] == "Title Page" and "book" not in t[1] and t[1]["verse_count"] == 0


def test_jst_rows_of_an_unknown_book_fail_loudly(tmp_path, built_db):
    from scripts.run_scripture_pipeline import read_store
    db = tmp_path / "orphan.db"
    shutil.copy(built_db, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE jst_verse SET book_id = NULL, core_book_id = 999 WHERE jst_verse_id = 1")
    with pytest.raises(SystemExit, match=r"CORE_BOOKS: \[999\]"):
        read_store(str(db))


# ---------------------------------------------------------------------------
# Embedded Weaviate + fake embedder
# ---------------------------------------------------------------------------

def run_script(env, script, *args):
    """scripture_world.run_script with the embedded Weaviate and fake embedder in the environment."""
    old = dict(os.environ)
    os.environ.update(env)
    try:
        return scripture_world.run_script(script, *args)
    finally:
        os.environ.clear()
        os.environ.update(old)


def objects(client, name):
    return list(client.collections.use(name).iterator(include_vector=True))


def by_ref(client):
    return {o.properties["reference"]: o.properties for o in objects(client, VERSES)}


def drop(client):
    for n in (VERSES, CHAPTERS, META):
        if client.collections.exists(n):
            client.collections.delete(n)


@pytest.fixture
def fresh(tmp_path, built_db, weaviate_env):
    """(db copy, client, env) with the scripture collections dropped before and after."""
    client, env = weaviate_env
    drop(client)
    db = tmp_path / "s.db"
    shutil.copy(built_db, db)
    yield db, client, env
    drop(client)


@pytest.fixture(scope="module")
def loaded(tmp_path_factory, built_db, weaviate_env):
    client, env = weaviate_env
    drop(client)
    db = tmp_path_factory.mktemp("loaded") / "scripture.db"
    shutil.copy(built_db, db)
    code, out = run_script(env, "run_scripture_pipeline.py", "--db", db)
    assert code == 0, out[-1500:]
    return db, client, env


def _rebuild(db, uri, old, new):
    """Re-fetch and rebuild db with one verse's text changed; returns the new build_id."""
    world = build_world()
    page = world[uri]["content"]
    assert old in page["body"]
    page["body"] = page["body"].replace(old, new, 1)
    old_id = q1(db, BUILD_ID)
    with FakeAPI(world):
        assert scripture_world.run_script("fetch_scriptures.py", "--db", db, "--refresh")[0] == 0
    assert scripture_world.run_script("build_scriptures.py", "--db", db)[0] == 0
    assert q1(db, BUILD_ID) != old_id
    return q1(db, BUILD_ID)


def _full_load_is_fresh(db, client, env, ref, marker):
    code, out = run_script(env, "run_scripture_pipeline.py", "--db", db)
    assert code == 0, out[-1500:]
    refs = by_ref(client)
    assert marker in refs[ref]["text"], "a resume kept an object from the old build"
    assert len([p for p in refs.values() if p["variant"] == "standard"]) == q1(db, "SELECT COUNT(*) FROM verse")
    meta = [o.properties for o in objects(client, META)]
    assert len(meta) == 1 and meta[0]["build_id"] == q1(db, BUILD_ID)


def test_slice_writes_no_build_id_and_force_replaces_it(fresh):
    db, client, env = fresh
    assert run_script(env, "run_scripture_pipeline.py", "--db", db, "--book", "Enos")[0] == 0
    std = [o for o in objects(client, VERSES) if o.properties["variant"] == "standard"]
    assert len(std) == 27 and {o.properties["chapter"] for o in std} == {1}
    meta = [o.properties for o in objects(client, META)]
    assert len(meta) == 1 and not meta[0].get("build_id") and meta[0]["loading_build_id"] == q1(db, BUILD_ID)
    n = len(objects(client, VERSES)) + len(objects(client, CHAPTERS))
    _Embed.calls = 0
    assert run_script(env, "run_scripture_pipeline.py", "--db", db, "--book", "Enos", "--force")[0] == 0
    assert _Embed.calls == n and len(objects(client, VERSES)) + len(objects(client, CHAPTERS)) == n


def test_interrupted_load_then_rebuild_reloads(fresh):
    db, client, env = fresh
    # Genesis is the first book: let all its records embed, then fail in the next book
    n_gen = q1(db, "SELECT (SELECT COUNT(*) FROM verse WHERE book_id = b.book_id) + (SELECT COUNT(*) FROM jst_verse "
                   "WHERE book_id = b.book_id AND source_flag = 'F') + (SELECT COUNT(*) FROM chapter WHERE book_id = "
                   "b.book_id) FROM book b WHERE uri = '/scriptures/ot/gen'")
    _Embed.calls, _Embed.fail_after = 0, n_gen + 1
    try:
        assert run_script(env, "run_scripture_pipeline.py", "--db", db)[0] != 0
    finally:
        _Embed.fail_after = None
    assert "Gen. 1:1" in by_ref(client) and not any(o.properties.get("build_id") for o in objects(client, META))
    _rebuild(db, "/scriptures/ot/gen/1", '<span class="verse-number">1 </span>In the ',
             '<span class="verse-number">1 </span>In the (stale test) ')
    _full_load_is_fresh(db, client, env, "Gen. 1:1", "(stale test)")


def test_slice_then_rebuild_then_full_load_reloads(fresh):
    db, client, env = fresh
    assert run_script(env, "run_scripture_pipeline.py", "--db", db, "--book", "Enos")[0] == 0
    assert "Enos 1:1" in by_ref(client)
    _rebuild(db, "/scriptures/bofm/enos/1", "Behold, it came to pass", "Behold, it came to pass (stale test)")
    _full_load_is_fresh(db, client, env, "Enos 1:1", "(stale test)")


def test_counts_properties_and_windows(loaded):
    from weaviate.classes.query import Filter
    db, client, _ = loaded
    variants = [o.properties["variant"] for o in objects(client, VERSES)]
    assert variants.count("standard") == q1(db, "SELECT COUNT(*) FROM verse")
    assert variants.count("jst") == q1(db, "SELECT COUNT(*) FROM jst_verse WHERE source_flag='F'")
    refs = by_ref(client)
    a = refs["Alma 32:21"]
    assert a["text"] == ALMA_32_21 and a["footnote_count"] == 3 and a["has_jst"] is False and a["aid"] == "128351643"
    assert a["context_window"] == f"Alma 32:21\n{refs['Alma 32:20']['text']}\n{ALMA_32_21}\n{refs['Alma 32:22']['text']}"
    assert refs["Alma 32:1"]["context_window"].count("\n") == 2
    assert all(o.vector["default"] for o in objects(client, VERSES))
    assert {"1 Ne. 3:7", "D&C 45:32", "Jude 1:3", "Enos 1:3", "John 3:16"} <= set(refs)
    # The verify script filters `context_window == ""`; with word tokenization Weaviate rejects that as a stopwords-only term
    empty = Filter.by_property("context_window").equal("")
    assert client.collections.use(VERSES).aggregate.over_all(total_count=True, filters=empty).total_count == 0


def test_jst_links_chapters_and_meta(loaded):
    db, client, _ = loaded
    refs = by_ref(client)
    assert refs["Ex. 7:3"]["has_jst"] is True and "JST Ex. 7:3" in refs["Ex. 7:3"]["jst_refs"]
    j = refs["JST Gen. 8:13"]
    assert j["variant"] == "jst" and "Gen. 6:6" in j["kjv_refs"] and j["context_window"].count("\n") == 1
    ch = {o.properties["reference"]: o.properties for o in objects(client, CHAPTERS)}
    assert ch["Alma 32"]["verse_count"] == 43 and {"D&C 45", "Gen. 1"} <= set(ch)
    assert {"declaration", "front_matter"} <= {p["kind"] for p in ch.values()}
    assert len(ch) == q1(db, "SELECT COUNT(*) FROM chapter")
    meta = objects(client, META)
    assert len(meta) == 1 and meta[0].properties["build_id"] == q1(db, BUILD_ID)


def test_verify_script_passes_on_a_full_load(loaded):
    db, _, env = loaded
    code, out = run_script(env, "verify_weaviate_scripture.py", "--db", db)
    assert code == 0 and "ALL PASS" in out and "FAIL " not in out, out[-3000:]
    for name in ("verse count", "chapter count", "volume counts", "has_jst Ex. 7:3", "variant counts", "has_jst count",
                 "vectors verses", "vectors chapters", "search semantic", "meta build_id"):
        assert f"PASS {name}:" in out, name


def test_verify_script_fails_when_counts_differ_from_the_db(loaded, tmp_path):
    """One chapter row and one has_jst verse fewer in the db than were loaded: equality, not >=, must catch both."""
    db, _, env = loaded
    other = tmp_path / "other.db"
    shutil.copy(db, other)
    with sqlite3.connect(other) as conn:
        conn.execute("DELETE FROM chapter WHERE chapter_id = (SELECT MIN(chapter_id) FROM chapter "
                     "WHERE chapter_id NOT IN (SELECT chapter_id FROM verse))")
        conn.execute("DELETE FROM footnote_ref WHERE category = 'jst' AND footnote_id IN (SELECT footnote_id FROM "
                     "footnote WHERE verse_id = (SELECT verse_id FROM verse v JOIN book b USING (book_id) "
                     "WHERE b.uri = '/scriptures/ot/ex' AND v.chapter = 7 AND v.verse = 3))")
    code, out = run_script(env, "verify_weaviate_scripture.py", "--db", other)
    assert code == 1, out[-3000:]
    assert "FAIL chapter count:" in out and "FAIL has_jst count:" in out and "PASS verse count:" in out, out[-3000:]
    assert "FAILED: " in out


def test_resume_skips_and_a_changed_build_reloads(loaded):
    db, client, env = loaded
    before = len(objects(client, VERSES))
    _Embed.calls = 0
    assert run_script(env, "run_scripture_pipeline.py", "--db", db)[0] == 0
    assert len(objects(client, VERSES)) == before and _Embed.calls == 0
    new_id = _rebuild(db, "/scriptures/nt/jude/1", "Beloved, when I gave", "Beloved (edition test), when I gave")
    assert run_script(env, "run_scripture_pipeline.py", "--db", db)[0] == 0
    assert "(edition test)" in by_ref(client)["Jude 1:3"]["text"]
    assert objects(client, META)[0].properties["build_id"] == new_id and len(objects(client, VERSES)) == before


# ---------------------------------------------------------------------------
# Further properties of the loaded objects (the parts the tests above do not pin down)
# ---------------------------------------------------------------------------

def test_object_properties_and_chapter_bounded_window(loaded):
    _, client, _ = loaded
    refs = by_ref(client)
    p = refs["Alma 32:21"]
    assert p["chapter"] == 32 and p["verse"] == 21 and p["has_jst"] is False
    assert p["volume"] and p["book"] and p["cite_abbr"]
    cw = p["context_window"]
    assert cw.startswith("Alma 32:21") and cw.index(refs["Alma 32:20"]["text"]) < cw.index(ALMA_32_21) \
        < cw.index(refs["Alma 32:22"]["text"])
    first = refs["Alma 32:1"]["context_window"]
    assert first.startswith("Alma 32:1") and refs["Alma 32:1"]["text"] in first and refs["Alma 32:2"]["text"] in first \
        and refs["Alma 32:3"]["text"] not in first, "window is chapter-bounded with radius 1: 32:1 holds only 32:1 and 32:2"


def test_jst_objects_are_embedded_alone_and_flag_their_kjv_verses(loaded):
    db, client, _ = loaded
    refs = by_ref(client)
    jp = refs["JST Gen. 8:13"]
    assert jp["variant"] == "jst" and jp["chapter"] == 8 and jp["verse"] == 13
    assert jp["context_window"].startswith("JST ") and jp["context_window"].rstrip().endswith(jp["text"].strip()) \
        and jp["context_window"].count("\n") == 1, "JST objects are embedded alone: 'JST {book} {c}:{v}\\n{text}'"
    std_with_jst = q1(db, "SELECT COUNT(DISTINCT f.verse_id) FROM footnote_ref r JOIN footnote f ON f.footnote_id=r.footnote_id "
                          "WHERE r.category='jst'")
    has = sum(1 for p in refs.values() if p.get("has_jst"))
    assert has >= std_with_jst, f"{has} has_jst objects < {std_with_jst} verses carrying jst footnotes"


def test_chapter_summary_and_declaration_kind(loaded):
    _, client, _ = loaded
    ch = {o.properties["reference"]: o.properties for o in objects(client, CHAPTERS)}
    assert ch["Alma 32"]["summary"].startswith("Alma teaches the poor")
    assert any(p.get("kind") == "declaration" for p in ch.values()), "OD 1 belongs in ScriptureChapters"
