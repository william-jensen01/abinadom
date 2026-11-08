"""_scripture_status: build-id comparison and "no finished load" handling (SPEC-v2 §9.3)."""
from types import SimpleNamespace

import server


class _Col:
    def __init__(self, props):
        self.props = props

    def iterator(self):
        return iter([SimpleNamespace(properties=self.props)] if self.props is not None else [])


class _Client:
    def __init__(self, existing, meta):
        self.collections = SimpleNamespace(exists=lambda n: existing, use=lambda n: _Col(meta))


def _store(build_id):
    return SimpleNamespace(db=SimpleNamespace(scalar=lambda q: build_id))


def test_mismatch_reports_both_ids(caplog):
    loaded, st = server._scripture_status(_Client(True, {"build_id": "old"}), _store("new"))
    assert loaded and st["mismatch"] and st["file_build_id"] == "new" and st["loaded_build_id"] == "old"
    assert "mismatch" in caplog.text and "run_scripture_pipeline.py" in caplog.text
    assert "run_scripture_pipeline.py" in st["hint"]


def test_slice_without_finished_build_is_not_a_mismatch():
    loaded, st = server._scripture_status(_Client(True, {"loading_build_id": "x"}), _store("new"))
    assert loaded and not st["mismatch"] and st["loaded_build_id"] is None and st["loading_build_id"] == "x"


def test_not_available_message_has_exact_phrase():
    from tools.scripture_tools import NOT_AVAILABLE
    assert "scripture corpus not available" in NOT_AVAILABLE   # GOAL.md: exact, case-sensitive


def test_missing_collections_and_db():
    loaded, st = server._scripture_status(_Client(False, None), None)
    assert not loaded and not st["db"] and not st["mismatch"]


# ---------------------------------------------------------------------------
# Optional startup through the MCP server (embedded Weaviate, fake embedder)
# ---------------------------------------------------------------------------

import shutil  # noqa: E402

from tests.scripture_world import FakeAPI, blob, build_world, call_tools, health, q1, run_script  # noqa: E402


def _unavailable(r):
    return "not available" in blob(r).lower()


def test_no_scripture_db_keeps_talk_tools(loaded, tmp_path):
    _, _, env = loaded
    e = dict(env, SCRIPTURE_DB_PATH=str(tmp_path / "nope.db"))
    stats, verse, srch = call_tools(e, [
        ("corpus_stats", {"collection": "talks"}),
        ("get_verse", {"book": "John", "chapter": 3, "verse_start": 16}),
        ("search", {"query": "faith", "collection": "scripture_verses", "alpha": 0.0}),
    ], unset=("SCRIPTURE_DB_URL",))
    assert isinstance(stats, list) or "total" in blob(stats), f"talk tools must still work: {blob(stats)[:200]}"
    assert _unavailable(verse), f"get_verse without scripture.db must say 'scripture corpus not available': {blob(verse)[:200]}"
    assert "scripture corpus not available" in blob(verse), f"exact, case-sensitive phrase: {blob(verse)[:200]}"
    (unset_only,) = call_tools({k: v for k, v in env.items() if k != "SCRIPTURE_DB_PATH"},
                               [("corpus_stats", {"collection": "talks"})], unset=("SCRIPTURE_DB_PATH", "SCRIPTURE_DB_URL"))
    assert "total" in blob(unset_only), "server must start with no scripture settings at all"


def test_unloaded_collections_keep_talk_tools(loaded):
    db, client, env = loaded
    for n in ("ScriptureVerses", "ScriptureChapters", "ScriptureMeta"):
        if client.collections.exists(n):
            client.collections.delete(n)
    try:
        stats, srch = call_tools(env, [
            ("corpus_stats", {"collection": "talks"}),
            ("search", {"query": "faith", "collection": "scripture_verses", "alpha": 0.0}),
        ])
        assert "total" in blob(stats), f"server must start without scripture collections: {blob(stats)[:200]}"
        assert _unavailable(srch), f"scripture search with collections not loaded must say 'not available': {blob(srch)[:200]}"
        assert "scripture corpus not available" in blob(srch), f"exact, case-sensitive phrase: {blob(srch)[:200]}"
    finally:
        code, out = run_script("run_scripture_pipeline.py", "--db", db, env=env)
        assert code == 0, out[-1500:]


def test_build_id_mismatch_is_reported(loaded, tmp_path):
    db, client, env = loaded
    loaded_id = q1(db, "SELECT value FROM build_meta WHERE key='build_id'")
    db2 = tmp_path / "newer.db"
    shutil.copy(db, db2)
    world = build_world()
    world["/scriptures/bofm/enos/1"]["content"]["body"] = world["/scriptures/bofm/enos/1"]["content"]["body"].replace(
        "Behold, it came to pass", "Behold, it came to pass (mismatch test)")
    with FakeAPI(world):
        code, out = run_script("fetch_scriptures.py", "--db", db2, "--refresh")
    assert code == 0, out[-1500:]
    code, out = run_script("build_scriptures.py", "--db", db2)
    assert code == 0, out[-1500:]
    file_id = q1(db2, "SELECT value FROM build_meta WHERE key='build_id'")
    assert file_id != loaded_id
    e = dict(env, SCRIPTURE_DB_PATH=str(db2))
    status, body = health(e, unset=("SCRIPTURE_DB_URL",))
    assert file_id in body and loaded_id in body, f"/health must report the mismatch naming both build IDs: {body[:300]}"
    (stats,) = call_tools(e, [("corpus_stats", {"collection": "talks"})], unset=("SCRIPTURE_DB_URL",))
    assert "total" in blob(stats), "the server still starts on a mismatch"
