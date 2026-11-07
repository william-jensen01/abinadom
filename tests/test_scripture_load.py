"""Loading the built scripture.db into Weaviate: transforms (pure), then ScriptureLoader and
scripts/run_scripture_pipeline.py against embedded Weaviate with a fake embedder (no network, no real Weaviate)."""
import hashlib
import json
import math
import re
import shutil
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from loaders.shared_transforms import prepare_chapter_records, prepare_verse_records
from tests import scripture_world
from tests.scripture_world import FakeAPI, build_world, q1
from tests.test_scripture_build import ALMA_32_21

VERSES, CHAPTERS, META = "ScriptureVerses", "ScriptureChapters", "ScriptureMeta"
DIM = 64


# ---------------------------------------------------------------------------
# Pure transforms
# ---------------------------------------------------------------------------

def _verse(n, chapter=1, book_uri="/scriptures/bofm/enos"):
    return dict(book="Enos", book_uri=book_uri, cite_abbr="Enos", volume="The Book of Mormon", chapter=chapter,
                verse=n, text=f"text {n}", aid=str(n), footnote_count=0)


def test_window_is_chapter_bounded_and_skip_does_not_shift_it():
    verses = [_verse(n) for n in (1, 2, 3)] + [_verse(1, chapter=2)]
    recs = {r[2]: r for r in prepare_verse_records(verses, [], radius=1)}
    assert recs["verse_/scriptures/bofm/enos_1_1"][0] == "Enos 1:1\ntext 1\ntext 2"
    assert recs["verse_/scriptures/bofm/enos_1_2"][0] == "Enos 1:2\ntext 1\ntext 2\ntext 3"
    assert recs["verse_/scriptures/bofm/enos_2_1"][0] == "Enos 2:1\ntext 1"
    only = prepare_verse_records(verses, [], radius=1, skip=lambda d: not d.endswith("_1_2"))
    assert [r[2] for r in only] == ["verse_/scriptures/bofm/enos_1_2"] and only[0][0] == recs["verse_/scriptures/bofm/enos_1_2"][0]
    assert prepare_verse_records(verses, [], radius=0)[1][0] == "Enos 1:2\ntext 2"


def test_jst_verse_is_embedded_alone_and_skipped_records_are_not_embedded():
    jst = [dict(book="Genesis", book_uri="/scriptures/ot/gen", cite_abbr="Gen.", volume="Old Testament", chapter=8,
                verse=13, text="jst text", kjv_refs=["Gen. 6:6"])]
    seen = []
    recs = prepare_verse_records([_verse(1)], jst, embed_fn=lambda t: seen.extend(t) or [[0.0]] * len(t),
                                 skip=lambda d: d.startswith("verse_"))
    assert seen == ["JST Genesis 8:13\njst text"] and len(recs) == 1
    meta = recs[0][1]
    assert meta["variant"] == "jst" and meta["reference"] == "JST Gen. 8:13" and meta["kjv_refs"] == ["Gen. 6:6"]
    assert recs[0][2] == "jst_/scriptures/ot/gen_8_13"


def test_chapter_records():
    rows = [dict(page_uri="/scriptures/bofm/alma/32", kind="chapter", number=32, cite_abbr="Alma", book="Alma",
                 volume="The Book of Mormon", title="Alma 32", summary="S", intro=None, verse_count=43),
            dict(page_uri="/scriptures/bofm/title-page", kind="front_matter", number=None, cite_abbr=None, book=None,
                 volume="The Book of Mormon", title="Title Page", summary=None, intro=None, verse_count=0)]
    a, t = prepare_chapter_records(rows)
    assert a[1]["reference"] == "Alma 32" and a[0] == "Alma 32: Alma 32\n\nS" and a[2] == "chapter_/scriptures/bofm/alma/32"
    assert t[1]["reference"] == "Title Page" and "book" not in t[1] and t[1]["verse_count"] == 0


# ---------------------------------------------------------------------------
# Embedded Weaviate + fake embedder
# ---------------------------------------------------------------------------

def _vector(text):
    v = [0.0] * DIM
    for w in re.findall(r"[a-z]+", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0 if (h >> 8) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class _Embed(BaseHTTPRequestHandler):
    calls = 0
    fail_after = None       # answer 500 once this many inputs were embedded (an interrupted load)

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        inputs = body.get("input", [])
        if type(self).fail_after is not None and type(self).calls + len(inputs) > type(self).fail_after:
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        type(self).calls += len(inputs)
        out = json.dumps({"data": [{"index": i, "embedding": _vector(t)} for i, t in enumerate(inputs)]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def run_script(script, *args, env=None):
    """scripture_world.run_script with extra environment variables for the run."""
    import os
    old = dict(os.environ)
    os.environ.update(env or {})
    try:
        return scripture_world.run_script(script, *args)
    finally:
        os.environ.clear()
        os.environ.update(old)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def weaviate_env(tmp_path_factory):
    import weaviate
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Embed)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port, grpc = _free_port(), _free_port()
    client = weaviate.connect_to_embedded(
        port=port, grpc_port=grpc, persistence_data_path=str(tmp_path_factory.mktemp("weaviate")),
        environment_variables={"DISABLE_TELEMETRY": "true", "LOG_LEVEL": "error"})
    yield client, {"WEAVIATE_HOST": "localhost", "WEAVIATE_PORT": str(port), "WEAVIATE_GRPC_PORT": str(grpc),
                   "EMBEDDING_URL": f"http://127.0.0.1:{srv.server_address[1]}"}
    client.close()
    srv.shutdown()


def objects(client, name):
    return list(client.collections.use(name).iterator(include_vector=True))


def by_ref(client):
    return {o.properties["reference"]: o.properties for o in objects(client, VERSES)}


def drop(client):
    for n in (VERSES, CHAPTERS, META):
        if client.collections.exists(n):
            client.collections.delete(n)


@pytest.fixture(scope="module")
def loaded(tmp_path_factory, built_db, weaviate_env):
    client, env = weaviate_env
    drop(client)
    db = tmp_path_factory.mktemp("loaded") / "scripture.db"
    shutil.copy(built_db, db)
    code, out = run_script("run_scripture_pipeline.py", "--db", db, env=env)
    assert code == 0, out[-1500:]
    return db, client, env


def test_one_book_slice_writes_no_meta(tmp_path, built_db, weaviate_env):
    client, env = weaviate_env
    drop(client)
    db = tmp_path / "s.db"
    shutil.copy(built_db, db)
    code, out = run_script("run_scripture_pipeline.py", "--db", db, "--book", "Enos", env=env)
    assert code == 0, out[-1500:]
    std = [o for o in objects(client, VERSES) if o.properties["variant"] == "standard"]
    assert len(std) == 27 and {o.properties["chapter"] for o in std} == {1}
    meta = [o.properties for o in objects(client, META)]
    assert len(meta) == 1 and not meta[0].get("build_id")
    assert meta[0]["loading_build_id"] == q1(db, "SELECT value FROM build_meta WHERE key='build_id'")
    drop(client)


def _rebuild(db, uri, old, new):
    """Re-fetch and rebuild db with one verse's text changed; returns the new build_id."""
    world = build_world()
    page = world[uri]["content"]
    assert old in page["body"]
    page["body"] = page["body"].replace(old, new, 1)
    old_id = q1(db, "SELECT value FROM build_meta WHERE key='build_id'")
    with FakeAPI(world):
        assert run_script("fetch_scriptures.py", "--db", db, "--refresh")[0] == 0
    assert run_script("build_scriptures.py", "--db", db)[0] == 0
    new_id = q1(db, "SELECT value FROM build_meta WHERE key='build_id'")
    assert new_id != old_id
    return new_id


def _full_load_is_fresh(db, client, env, ref, marker, new_id):
    code, out = run_script("run_scripture_pipeline.py", "--db", db, env=env)
    assert code == 0, out[-1500:]
    refs = by_ref(client)
    assert marker in refs[ref]["text"], "a resume kept an object from the old build"
    assert len([p for p in refs.values() if p["variant"] == "standard"]) == q1(db, "SELECT COUNT(*) FROM verse")
    meta = [o.properties for o in objects(client, META)]
    assert len(meta) == 1 and meta[0]["build_id"] == new_id


def test_interrupted_load_then_rebuild_reloads(tmp_path, built_db, weaviate_env):
    client, env = weaviate_env
    drop(client)
    db = tmp_path / "i.db"
    shutil.copy(built_db, db)
    # Genesis is the first book; let its records embed, then fail in the next book
    gen = q1(db, "SELECT book_id FROM book WHERE uri = '/scriptures/ot/gen'")
    n_gen = (q1(db, f"SELECT COUNT(*) FROM verse WHERE book_id = {gen}")
             + q1(db, f"SELECT COUNT(*) FROM jst_verse WHERE book_id = {gen} AND source_flag = 'F'")
             + q1(db, f"SELECT COUNT(*) FROM chapter WHERE book_id = {gen}"))
    _Embed.calls, _Embed.fail_after = 0, n_gen + 1
    try:
        code, _ = run_script("run_scripture_pipeline.py", "--db", db, env=env)
    finally:
        _Embed.fail_after = None
    assert code != 0
    assert "Gen. 1:1" in by_ref(client) and not any(o.properties.get("build_id") for o in objects(client, META))
    new_id = _rebuild(db, "/scriptures/ot/gen/1", '<span class="verse-number">1 </span>In the ',
                      '<span class="verse-number">1 </span>In the (stale test) ')
    _full_load_is_fresh(db, client, env, "Gen. 1:1", "(stale test)", new_id)
    drop(client)


def test_slice_then_rebuild_then_full_load_reloads(tmp_path, built_db, weaviate_env):
    client, env = weaviate_env
    drop(client)
    db = tmp_path / "b.db"
    shutil.copy(built_db, db)
    assert run_script("run_scripture_pipeline.py", "--db", db, "--book", "Enos", env=env)[0] == 0
    assert "Enos 1:1" in by_ref(client)
    new_id = _rebuild(db, "/scriptures/bofm/enos/1", "Behold, it came to pass", "Behold, it came to pass (stale test)")
    _full_load_is_fresh(db, client, env, "Enos 1:1", "(stale test)", new_id)
    drop(client)


def test_counts_properties_and_windows(loaded):
    db, client, _ = loaded
    n_f = q1(db, "SELECT COUNT(*) FROM jst_verse WHERE source_flag='F'")
    variants = [o.properties["variant"] for o in objects(client, VERSES)]
    assert variants.count("standard") == q1(db, "SELECT COUNT(*) FROM verse") and variants.count("jst") == n_f
    refs = by_ref(client)
    a = refs["Alma 32:21"]
    assert a["text"] == ALMA_32_21 and a["footnote_count"] == 3 and a["has_jst"] is False and a["aid"] == "128351643"
    assert a["context_window"] == f"Alma 32:21\n{refs['Alma 32:20']['text']}\n{ALMA_32_21}\n{refs['Alma 32:22']['text']}"
    assert refs["Alma 32:1"]["context_window"].count("\n") == 2
    assert all(o.vector["default"] for o in objects(client, VERSES))
    for ref in ("1 Ne. 3:7", "D&C 45:32", "Jude 1:3", "Enos 1:3", "John 3:16"):
        assert ref in refs


def test_jst_links_and_chapters_and_meta(loaded):
    db, client, _ = loaded
    refs = by_ref(client)
    assert refs["Ex. 7:3"]["has_jst"] is True and "JST Ex. 7:3" in refs["Ex. 7:3"]["jst_refs"]
    j = refs["JST Gen. 8:13"]
    assert j["variant"] == "jst" and "Gen. 6:6" in j["kjv_refs"] and j["context_window"].count("\n") == 1
    ch = {o.properties["reference"]: o.properties for o in objects(client, CHAPTERS)}
    assert ch["Alma 32"]["verse_count"] == 43 and {"D&C 45", "Gen. 1"} <= set(ch)
    assert any(p["kind"] == "declaration" for p in ch.values()) and any(p["kind"] == "front_matter" for p in ch.values())
    assert len(ch) == q1(db, "SELECT COUNT(*) FROM chapter")
    meta = objects(client, META)
    assert len(meta) == 1 and meta[0].properties["build_id"] == q1(db, "SELECT value FROM build_meta WHERE key='build_id'")


def test_resume_skips_and_a_changed_build_reloads(loaded):
    db, client, env = loaded
    before = len(objects(client, VERSES))
    _Embed.calls = 0
    assert run_script("run_scripture_pipeline.py", "--db", db, env=env)[0] == 0
    assert len(objects(client, VERSES)) == before and _Embed.calls == 0

    world = build_world()
    jude = world["/scriptures/nt/jude/1"]["content"]
    jude["body"] = jude["body"].replace("Beloved, when I gave", "Beloved (edition test), when I gave")
    old_id = q1(db, "SELECT value FROM build_meta WHERE key='build_id'")
    with FakeAPI(world):
        assert run_script("fetch_scriptures.py", "--db", db, "--refresh")[0] == 0
    assert run_script("build_scriptures.py", "--db", db)[0] == 0
    new_id = q1(db, "SELECT value FROM build_meta WHERE key='build_id'")
    assert new_id != old_id
    code, out = run_script("run_scripture_pipeline.py", "--db", db, env=env)
    assert code == 0, out[-1500:]
    assert "(edition test)" in by_ref(client)["Jude 1:3"]["text"]
    assert objects(client, META)[0].properties["build_id"] == new_id and len(objects(client, VERSES)) == before
