"""The real load in the configured Weaviate passes the post-load checks (SCR-01..06).

Opt-in: needs the real Weaviate and embedder from .env (or the environment), so it is skipped unless
SCRIPTURE_LIVE_WEAVIATE=1. It only reads Weaviate; the real scripture.db is read through a temp copy.
Independent of scripts/verify_weaviate_scripture.py, which must also exit 0.

    SCRIPTURE_LIVE_WEAVIATE=1 pipenv run python -m pytest tests/test_scripture_load_full.py -q
"""
import os
import subprocess
import sys

import pytest

from tests.scripture_world import ROOT, q1

PLAUSIBLE_PLAN = {"Alma 12", "Alma 22", "Alma 34", "Alma 40", "Alma 41", "Alma 42", "2 Ne. 2", "2 Ne. 9", "2 Ne. 31",
                  "Moses 1", "Moses 5", "Moses 6", "Abr. 3", "D&C 76", "D&C 88", "D&C 93", "D&C 131", "D&C 137",
                  "D&C 138", "1 Cor. 15", "Mosiah 15", "Mosiah 16", "Hel. 14", "3 Ne. 27", "Alma 11", "Alma 13"}

pytestmark = pytest.mark.skipif(os.environ.get("SCRIPTURE_LIVE_WEAVIATE") != "1",
                                reason="reads the real Weaviate and embedder; set SCRIPTURE_LIVE_WEAVIATE=1 to run")

BUILD_ID = "SELECT value FROM build_meta WHERE key='build_id'"


@pytest.fixture(scope="module")
def db(full_store):
    if not q1(full_store, BUILD_ID):
        pytest.skip("db/scripture.db has not been built (build_scriptures.py)")
    return full_store


@pytest.fixture(scope="module")
def live_env():
    """WEAVIATE_*/EMBEDDING_URL from the environment or .env, applied for this module only."""
    old = dict(os.environ)
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    yield dict(os.environ)
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture(scope="module")
def wv(live_env, db):
    from config.weaviate_client import get_weaviate_client
    try:
        client = get_weaviate_client()
        assert client.is_ready()
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"Weaviate at {os.environ.get('WEAVIATE_HOST')}:{os.environ.get('WEAVIATE_PORT')} is not reachable ({e})")
    yield client
    client.close()


def _count(client, name, flt=None):
    return client.collections.use(name).aggregate.over_all(total_count=True, filters=flt).total_count


def _one(client, ref):
    from weaviate.classes.query import Filter
    r = client.collections.use("ScriptureVerses").query.fetch_objects(
        filters=Filter.by_property("reference").equal(ref), limit=2, include_vector=True)
    assert r.objects, f"SCR-03: no object for {ref}"
    return r.objects[0]


def test_scr01_02_counts(wv, db):
    from weaviate.classes.aggregate import GroupByAggregate
    from weaviate.classes.query import Filter
    verses = q1(db, "SELECT COUNT(*) FROM verse")
    f = q1(db, "SELECT COUNT(*) FROM jst_verse WHERE source_flag='F'")
    got = _count(wv, "ScriptureVerses")
    print(f"ScriptureVerses {got} (expected {verses} + {f})")
    assert got == verses + f, f"SCR-01: ScriptureVerses {got} != canonical {verses} + F {f}"
    assert _count(wv, "ScriptureVerses", Filter.by_property("variant").equal("jst")) == f
    chapters = q1(db, "SELECT COUNT(*) FROM chapter")
    got_c = _count(wv, "ScriptureChapters")
    assert got_c >= chapters, f"SCR-02: ScriptureChapters {got_c} < {chapters} chapter rows"
    groups = wv.collections.use("ScriptureVerses").aggregate.over_all(
        group_by=GroupByAggregate(prop="volume"), total_count=True).groups
    vols = {g.grouped_by.value: g.total_count for g in groups}
    print("verses per volume:", vols)
    assert len([v for v in vols.values() if v > 500]) >= 5, f"SCR-02: all five volumes must be present: {vols}"


def test_scr03_spot_checks(wv):
    for ref, start in {"John 3:16": "For God so loved the world", "Alma 32:21": "And now as I said concerning faith",
                       "1 Ne. 3:7": "And it came to pass that I, Nephi", "D&C 45:32": "But my disciples shall stand"}.items():
        assert _one(wv, ref).properties["text"].startswith(start), ref
    ex = _one(wv, "Ex. 7:3").properties
    assert ex["has_jst"] and "JST Ex. 7:3" in ex["jst_refs"], f"SCR-03: Ex. 7:3 {ex.get('has_jst')} {ex.get('jst_refs')}"


def test_scr04_05_flags_windows_vectors(wv, db):
    from weaviate.classes.query import Filter
    has = _count(wv, "ScriptureVerses", Filter.by_property("has_jst").equal(True))
    expected = q1(db, "SELECT COUNT(DISTINCT f.verse_id) FROM footnote_ref r JOIN footnote f ON f.footnote_id=r.footnote_id "
                      "WHERE r.category='jst' AND r.target_jst_verse_id IS NOT NULL")
    assert has >= expected, f"SCR-04: has_jst {has} < {expected} verses with resolved jst footnotes"
    col = wv.collections.use("ScriptureVerses")
    empty = col.aggregate.over_all(total_count=True, filters=Filter.by_property("context_window").equal("")).total_count
    assert empty == 0, f"SCR-05: {empty} empty context_window"
    sample = col.query.fetch_objects(limit=300, include_vector=True).objects
    assert sample and all(o.vector for o in sample), "SCR-05: objects without vectors"


def test_scr06_semantic_and_keyword_sanity(wv):
    from config.embedding import get_embedding_function
    from weaviate.classes.query import Filter
    ef = get_embedding_function(task="query")
    col = wv.collections.use("ScriptureVerses")
    std = Filter.by_property("variant").equal("standard")
    hits = col.query.near_vector(ef(["faith as a seed"])[0], limit=10, filters=std).objects
    refs = [o.properties["reference"] for o in hits]
    assert any(r.startswith("Alma 32:") for r in refs), f"SCR-06: 'faith as a seed' -> {refs}"
    bm = [o.properties["reference"] for o in col.query.bm25("charity suffereth long", limit=5, filters=std).objects]
    assert {"1 Cor. 13:4", "Moro. 7:45"} & set(bm), f"SCR-06: BM25 'charity suffereth long' -> {bm}"
    ch = wv.collections.use("ScriptureChapters").query.near_vector(ef(["plan of salvation"])[0], limit=10).objects
    crefs = [o.properties["reference"] for o in ch]
    assert PLAUSIBLE_PLAN & set(crefs), f"SCR-06: chapter search 'plan of salvation' -> {crefs}"


def test_meta_and_repo_verifier(wv, db, live_env):
    meta = list(wv.collections.use("ScriptureMeta").iterator())
    assert len(meta) == 1 and meta[0].properties["build_id"] == q1(db, BUILD_ID), \
        "ScriptureMeta.build_id must equal db/scripture.db's build_id after the full load"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_weaviate_scripture.py"), "--db", str(db)],
                       cwd=ROOT, capture_output=True, text=True, timeout=600, env=live_env)
    assert r.returncode == 0, f"scripts/verify_weaviate_scripture.py failed:\n{(r.stdout + r.stderr)[-1500:]}"
