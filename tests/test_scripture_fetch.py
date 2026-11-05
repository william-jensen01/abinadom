"""scripts/fetch_scriptures.py against the fake Church API."""
import json

from tests.scripture_world import FakeAPI, VOLUMES, q, q1, run_script, world_toc_links, CONTENT_PATH


def _expected_uris(world):
    uris = set()
    for v in VOLUMES + ["jst"]:
        uris.add(f"/scriptures/{v}")
        uris |= world_toc_links(world, v)
    return uris


def test_first_fetch_stores_every_toc_page(tmp_path, world):
    db = tmp_path / "scripture.db"
    with FakeAPI(world) as api:
        code, out = run_script("fetch_scriptures.py", "--db", db, fast=False)
    assert code == 0, out[-1500:]
    stored = {r[0] for r in q(db, "SELECT uri FROM raw_latest WHERE lang='eng' AND status=200")}
    missing = _expected_uris(world) - stored
    assert not missing, f"pages linked from the five volume TOCs or the JST appendix TOC but not stored: {sorted(missing)[:10]}"

    # the content endpoint, the project User-Agent, and the ≤2 req/s throttle
    assert api.requests, "no requests reached the (fake) Church API"
    assert all(p == CONTENT_PATH for _, _, _, p in api.requests), \
        f"must use {CONTENT_PATH}; saw {sorted({p for *_, p in api.requests})}"
    assert all("lds-sci-mcp" in ua for _, _, ua, _ in api.requests), "requests must send the project User-Agent"
    times = [t for t, *_ in api.requests]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert min(gaps) >= 0.45, f"requests closer than 0.5s apart (min gap {min(gaps):.3f}s): use the utils.church_api throttle"

    # raw json is the response, unmodified
    row = q(db, "SELECT json, content_hash, fetched_at FROM raw_latest WHERE uri=? AND lang='eng'",
            ("/scriptures/bofm/alma/32",))
    assert row, "alma/32 not stored"
    assert json.loads(row[0][0]) == world["/scriptures/bofm/alma/32"], "raw_page.json must be the response, unmodified"
    assert len(row[0][1]) == 64, "content_hash should be a sha256 hex digest"


def test_refetch_is_idempotent_and_refresh_records_only_changes(tmp_path, world):
    db = tmp_path / "scripture.db"
    with FakeAPI(world):
        code, out = run_script("fetch_scriptures.py", "--db", db)
    assert code == 0, out[-1500:]
    n0 = q1(db, "SELECT COUNT(*) FROM raw_page")

    # --only-missing on a complete store: no page requests, no rows
    with FakeAPI(world) as api:
        code, out = run_script("fetch_scriptures.py", "--db", db, "--only-missing")
    assert code == 0, out[-1500:]
    page_reqs = [u for _, u, *_ in api.requests if u.count("/") > 2]
    assert not page_reqs, f"--only-missing re-requested stored pages: {page_reqs[:5]}"
    assert q1(db, "SELECT COUNT(*) FROM raw_page") == n0

    # --refresh with nothing changed: re-requests pages, inserts nothing
    with FakeAPI(world) as api:
        code, out = run_script("fetch_scriptures.py", "--db", db, "--refresh")
    assert code == 0, out[-1500:]
    assert len(api.requests) >= len(_expected_uris(world)), "--refresh must re-fetch every page"
    assert q1(db, "SELECT COUNT(*) FROM raw_page") == n0, "unchanged re-fetch must write nothing"

    # --refresh with one changed page: exactly one new row, history kept, raw_latest = new
    changed = json.loads(json.dumps(world))
    changed["/scriptures/nt/jude/1"]["content"]["body"] = changed["/scriptures/nt/jude/1"]["content"]["body"].replace(
        "Beloved, when I gave", "Beloved (edition test), when I gave")
    with FakeAPI(changed):
        code, out = run_script("fetch_scriptures.py", "--db", db, "--refresh")
    assert code == 0, out[-1500:]
    assert q1(db, "SELECT COUNT(*) FROM raw_page") == n0 + 1, "a changed page must add exactly one row"
    assert q1(db, "SELECT COUNT(*) FROM raw_page WHERE uri='/scriptures/nt/jude/1'") == 2, "old version must be kept"
    latest = q1(db, "SELECT json FROM raw_latest WHERE uri='/scriptures/nt/jude/1' AND lang='eng'")
    assert "(edition test)" in latest, "raw_latest must return the newest version"


def test_interrupted_fetch_resumes(tmp_path, world):
    db = tmp_path / "scripture.db"
    with FakeAPI(world) as api:
        api.fail_after = 9          # the network dies after 9 requests
        code, out = run_script("fetch_scriptures.py", "--db", db)
    assert code != 0, "a fetch that could not reach every page must exit non-zero"
    partial = {r[0] for r in q(db, "SELECT uri FROM raw_latest")} if db.exists() else set()
    assert len(partial) >= 3, f"pages fetched before the failure should be kept (kept {len(partial)})"

    with FakeAPI(world) as api:
        code, out = run_script("fetch_scriptures.py", "--db", db, "--only-missing")
    assert code == 0, out[-1500:]
    again = {u for _, u, *_ in api.requests} & (partial - {f"/scriptures/{v}" for v in VOLUMES + ["jst"]})
    assert not again, f"resume re-fetched already-stored pages: {sorted(again)[:5]}"
    stored = {r[0] for r in q(db, "SELECT uri FROM raw_latest WHERE status=200")}
    assert not (_expected_uris(world) - stored), "resume did not complete the store"


def test_server_error_is_reported_not_silently_skipped(tmp_path, world):
    db = tmp_path / "scripture.db"
    with FakeAPI(world) as api:
        api.fail_uris = {"/scriptures/bofm/enos/1"}
        code, out = run_script("fetch_scriptures.py", "--db", db)
    assert code != 0, "a page that keeps failing must make the run exit non-zero"
    assert "enos/1" in out, "the failing URI must be named in the output"
