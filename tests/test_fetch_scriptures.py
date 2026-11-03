"""Tests for scripts/fetch_scriptures.py (SPEC-v2 §4.1, §8) with a fake session: no network."""

import json
import sqlite3

import pytest
import requests

import scripts.fetch_scriptures as fs
import utils.church_api as church_api


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(church_api, "MIN_INTERVAL", 0)
    monkeypatch.setattr(church_api, "RETRY_DELAY", 0)
    monkeypatch.setattr(church_api, "_last_network_request", 0.0)


def _toc(*uris):
    links = "".join(f'<a href="/study{u}?lang=eng">x</a>' for u in uris)
    return {"content": {"body": f"<nav>{links}</nav>"}}


def _page(uri, text="verse text"):
    return {"uri": uri, "content": {"body": f"<p>{text}</p>", "footnotes": {}}}


def _world():
    world = {
        "/scriptures/ot": _toc("/scriptures/ot/gen/1", "/scriptures/ot/gen/1"),  # duplicate link
        "/scriptures/nt": _toc("/scriptures/nt/jude/1", "/scriptures/bofm/alma/32"),  # cross-volume link: deduplicated, not fetched twice
        "/scriptures/bofm": _toc("/scriptures/bofm/bofm-title", "/scriptures/bofm/alma/32", "/scriptures/bofm/enos/1"),
        "/scriptures/dc-testament": _toc("/scriptures/dc-testament/dc/1", "/scriptures/dc-testament/od/1"),
        "/scriptures/pgp": _toc("/scriptures/pgp/moses/1", "/scriptures/pgp/_contents"),
        "/scriptures/jst": _toc("/scriptures/jst/jst-gen/1-8"),
    }
    for toc in list(world):
        for uri in fs.toc_links(world[toc]):
            world.setdefault(uri, _page(uri))
    return world


class _Resp:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.text = json.dumps(payload) if payload is not None else ""
        self._payload = payload
        self.from_cache = False

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)


class FakeSession:
    """Serves `pages` by URI; URIs in `fail` answer 500; records every requested URL."""

    def __init__(self, pages, fail=()):
        self.pages, self.fail, self.urls = pages, set(fail), []

    def get(self, url, timeout):
        self.urls.append(url)
        uri = url.split("uri=", 1)[1]
        if uri in self.fail:
            return _Resp({"error": "boom"}, 500)
        if uri not in self.pages:
            return _Resp({"error": "not found"}, 404)
        return _Resp(self.pages[uri])

    def uris(self):
        return [u.split("uri=", 1)[1] for u in self.urls]


def _run(monkeypatch, db, session, *args):
    monkeypatch.setattr(church_api, "fresh_session", lambda: session)
    return fs.main(["--db", str(db), *args])


def _rows(db, sql, params=()):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _all_uris(world):
    return set(world)


def test_walks_volume_and_jst_tocs_including_contents_pages(monkeypatch, tmp_path):
    world, db = _world(), tmp_path / "scripture.db"
    session = FakeSession(world)
    assert _run(monkeypatch, db, session) == 0

    stored = {r[0] for r in _rows(db, "SELECT uri FROM raw_latest WHERE lang='eng' AND status=200")}
    assert stored == _all_uris(world)
    assert "/scriptures/pgp/_contents" in stored
    assert "/scriptures/jst/jst-gen/1-8" in stored
    # content endpoint, each page requested once even when linked twice
    assert all(church_api.CONTENT_BASE_URL in u for u in session.urls)
    assert session.uris().count("/scriptures/bofm/alma/32") == 1
    assert session.uris().count("/scriptures/ot/gen/1") == 1

    raw, h = _rows(db, "SELECT json, content_hash FROM raw_latest WHERE uri='/scriptures/bofm/alma/32'")[0]
    assert json.loads(raw) == world["/scriptures/bofm/alma/32"]
    assert h == fs.content_hash(world["/scriptures/bofm/alma/32"])


def test_unchanged_refetch_adds_no_rows(monkeypatch, tmp_path):
    world, db = _world(), tmp_path / "scripture.db"
    assert _run(monkeypatch, db, FakeSession(world)) == 0
    n0 = _rows(db, "SELECT COUNT(*) FROM raw_page")[0][0]

    session = FakeSession(world)
    assert _run(monkeypatch, db, session, "--refresh") == 0
    assert set(session.uris()) == _all_uris(world)
    assert _rows(db, "SELECT COUNT(*) FROM raw_page")[0][0] == n0


def test_changed_page_adds_one_row_and_raw_latest_returns_it(monkeypatch, tmp_path):
    world, db = _world(), tmp_path / "scripture.db"
    assert _run(monkeypatch, db, FakeSession(world)) == 0
    n0 = _rows(db, "SELECT COUNT(*) FROM raw_page")[0][0]

    world["/scriptures/nt/jude/1"] = _page("/scriptures/nt/jude/1", "new edition")
    assert _run(monkeypatch, db, FakeSession(world), "--refresh") == 0
    assert _rows(db, "SELECT COUNT(*) FROM raw_page")[0][0] == n0 + 1
    assert _rows(db, "SELECT COUNT(*) FROM raw_page WHERE uri='/scriptures/nt/jude/1'")[0][0] == 2
    latest = _rows(db, "SELECT json FROM raw_latest WHERE uri='/scriptures/nt/jude/1'")[0][0]
    assert "new edition" in latest
    assert len(_rows(db, "SELECT uri FROM raw_latest")) == len(world)


def test_only_missing_skips_stored_pages(monkeypatch, tmp_path):
    world, db = _world(), tmp_path / "scripture.db"
    # first run: enos/1 fails, everything else is stored
    assert _run(monkeypatch, db, FakeSession(world, fail={"/scriptures/bofm/enos/1"})) == 1

    session = FakeSession(world)
    assert _run(monkeypatch, db, session, "--only-missing") == 0
    page_requests = [u for u in session.uris() if u not in fs.TOC_URIS]
    assert page_requests == ["/scriptures/bofm/enos/1"]
    stored = {r[0] for r in _rows(db, "SELECT uri FROM raw_latest WHERE status=200")}
    assert stored == _all_uris(world)


def test_failing_uri_exits_nonzero_and_is_named(monkeypatch, tmp_path, capsys):
    world, db = _world(), tmp_path / "scripture.db"
    assert _run(monkeypatch, db, FakeSession(world, fail={"/scriptures/bofm/enos/1"})) == 1
    err = capsys.readouterr().err
    assert "/scriptures/bofm/enos/1" in err
    # pages fetched around the failure are kept
    stored = {r[0] for r in _rows(db, "SELECT uri FROM raw_latest")}
    assert stored == _all_uris(world) - {"/scriptures/bofm/enos/1"}


def test_failed_toc_under_refresh_counts_as_failed(monkeypatch, tmp_path, capsys):
    world, db = _world(), tmp_path / "scripture.db"
    assert _run(monkeypatch, db, FakeSession(world)) == 0
    capsys.readouterr()

    # default mode: the stored TOC is an acceptable fallback
    assert _run(monkeypatch, db, FakeSession(world, fail={"/scriptures/pgp"})) == 0
    # --refresh: the TOC was not refreshed, so the run fails and names it
    session = FakeSession(world, fail={"/scriptures/pgp"})
    assert _run(monkeypatch, db, session, "--refresh") == 1
    assert "/scriptures/pgp " in capsys.readouterr().err
    assert "/scriptures/pgp/moses/1" in session.uris()  # still walked via the stored TOC


def test_abort_summarizes_not_attempted_uris(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(fs, "MAX_CONSECUTIVE_FAILURES", 2)
    monkeypatch.setattr(fs, "SHOW_NOT_ATTEMPTED", 1)
    tocs = {"/scriptures/ot": _toc(*[f"/scriptures/ot/gen/{i}" for i in range(1, 7)])}
    for t in fs.TOC_URIS[1:]:
        tocs[t] = _toc()
    world = dict(tocs, **{f"/scriptures/ot/gen/{i}": _page(f"/scriptures/ot/gen/{i}") for i in range(1, 7)})
    fail = {"/scriptures/ot/gen/2", "/scriptures/ot/gen/3"}
    db = tmp_path / "scripture.db"

    assert _run(monkeypatch, db, FakeSession(world, fail=fail)) == 1
    err = capsys.readouterr().err
    assert "/scriptures/ot/gen/2" in err and "/scriptures/ot/gen/3" in err
    assert "3 URIs not attempted" in err
    assert "/scriptures/ot/gen/4" in err and "/scriptures/ot/gen/5" not in err
    assert {r[0] for r in _rows(db, "SELECT uri FROM raw_latest")} >= {"/scriptures/ot/gen/1"}
