"""scripts/fetch_scriptures.py with a fake session: no network."""
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


def toc(*uris):
    return {"content": {"body": "".join(f'<a href="/study{u}?lang=eng">x</a>' for u in uris)}}


WORLD = {
    "/scriptures/ot": toc("/scriptures/ot/gen/1", "/scriptures/ot/gen/1", "/scriptures/tg/faith"),  # dup + study help
    "/scriptures/nt": toc("/scriptures/nt/jude/1", "/scriptures/bofm/alma/32"),   # cross-volume link, fetched once
    "/scriptures/bofm": toc("/scriptures/bofm/alma/32", "/scriptures/bofm/enos/1"),
    "/scriptures/dc-testament": toc("/scriptures/dc-testament/od/1"),
    "/scriptures/pgp": toc("/scriptures/pgp/moses/_contents"),
    "/scriptures/jst": toc("/scriptures/jst/jst-gen/9"),
}
PAGES = ["/scriptures/ot/gen/1", "/scriptures/nt/jude/1", "/scriptures/bofm/alma/32", "/scriptures/bofm/enos/1",
         "/scriptures/dc-testament/od/1", "/scriptures/pgp/moses/_contents", "/scriptures/jst/jst-gen/9"]
WORLD.update({u: {"uri": u, "content": {"body": f"<p>{u}</p>"}} for u in PAGES})


class Response:
    def __init__(self, payload, status=200):
        self.status_code, self.text, self.from_cache = status, json.dumps(payload), False

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """Serves `pages`; URIs in `fail` answer 500; after `down_after` requests the network is down."""

    def __init__(self, pages, fail=(), down_after=None):
        self.pages, self.fail, self.down_after, self.uris = pages, set(fail), down_after, []

    def get(self, url, timeout):
        assert "/type/content?" in url
        uri = url.split("uri=", 1)[1]
        self.uris.append(uri)
        if self.down_after is not None and len(self.uris) > self.down_after:
            raise requests.exceptions.ConnectionError("down")
        if uri in self.fail:
            return Response({"error": "boom"}, 500)
        return Response(self.pages[uri]) if uri in self.pages else Response({"error": "not found"}, 404)


def run(monkeypatch, db, session, *args):
    monkeypatch.setattr(church_api, "fresh_session", lambda: session)
    return fs.main(["--db", str(db), *args])


def raw(db, sql="SELECT uri, json FROM raw_page ORDER BY uri"):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_fetch_stores_every_toc_page_once(tmp_path, monkeypatch):
    s = FakeSession(WORLD)
    assert run(monkeypatch, tmp_path / "s.db", s) == 0
    assert sorted(s.uris) == sorted(WORLD)          # each page once; study helps are not fetched
    stored = dict(raw(tmp_path / "s.db"))
    assert set(stored) == set(WORLD)
    assert json.loads(stored["/scriptures/bofm/alma/32"]) == WORLD["/scriptures/bofm/alma/32"]


def test_unchanged_refetch_writes_nothing_and_a_change_adds_a_row(tmp_path, monkeypatch):
    db = tmp_path / "s.db"
    assert run(monkeypatch, db, FakeSession(WORLD)) == 0
    assert run(monkeypatch, db, FakeSession(WORLD), "--refresh") == 0
    assert len(raw(db)) == len(WORLD)
    changed = dict(WORLD, **{"/scriptures/nt/jude/1": {"uri": "x", "content": {"body": "<p>new</p>"}}})
    assert run(monkeypatch, db, FakeSession(changed)) == 0
    assert len(raw(db)) == len(WORLD) + 1
    latest = raw(db, "SELECT json FROM raw_latest WHERE uri = '/scriptures/nt/jude/1'")
    assert "new" in latest[0][0]


def test_a_page_that_reverts_to_earlier_content_is_latest_again(tmp_path, monkeypatch, capsys):
    db, uri = tmp_path / "s.db", "/scriptures/nt/jude/1"
    b = dict(WORLD, **{uri: {"uri": uri, "content": {"body": "<p>B</p>"}}})
    latest = f"SELECT json FROM raw_latest WHERE uri = '{uri}'"
    assert run(monkeypatch, db, FakeSession(WORLD)) == 0                  # A
    assert run(monkeypatch, db, FakeSession(b)) == 0                      # B
    assert "<p>B</p>" in raw(db, latest)[0][0]
    capsys.readouterr()
    assert run(monkeypatch, db, FakeSession(WORLD)) == 0                  # A again, within the same second
    assert json.loads(raw(db, latest)[0][0]) == WORLD[uri]
    assert len(raw(db)) == len(WORLD) + 1                                 # A's row reused, B kept
    assert "'added': 0, 'reverted': 1," in capsys.readouterr().out
    assert run(monkeypatch, db, FakeSession(WORLD)) == 0                  # A -> A: nothing written
    assert len(raw(db)) == len(WORLD) + 1
    assert json.loads(raw(db, latest)[0][0]) == WORLD[uri]
    assert "'added': 0, 'reverted': 0," in capsys.readouterr().out


def test_only_missing_requests_only_what_is_missing(tmp_path, monkeypatch):
    db = tmp_path / "s.db"
    assert run(monkeypatch, db, FakeSession(WORLD, fail={"/scriptures/bofm/enos/1"})) == 1
    s = FakeSession(WORLD)
    assert run(monkeypatch, db, s, "--only-missing") == 0
    assert s.uris == ["/scriptures/bofm/enos/1"]


def test_a_failing_page_is_named_and_fails_the_run(tmp_path, monkeypatch, capsys):
    assert run(monkeypatch, tmp_path / "s.db", FakeSession(WORLD, fail={"/scriptures/bofm/enos/1"})) == 1
    assert "/scriptures/bofm/enos/1" in capsys.readouterr().err
    assert len(raw(tmp_path / "s.db")) == len(WORLD) - 1


def test_network_down_stops_after_ten_failures_and_resume_completes(tmp_path, monkeypatch, capsys):
    db = tmp_path / "s.db"
    many = dict(WORLD, **{"/scriptures/ot": toc(*[f"/scriptures/ot/ps/{n}" for n in range(1, 41)])})
    many.update({f"/scriptures/ot/ps/{n}": {"content": {"body": str(n)}} for n in range(1, 41)})
    del many["/scriptures/ot/gen/1"]
    s = FakeSession(many, down_after=8)
    assert run(monkeypatch, db, s) == 1
    assert "not attempted" in capsys.readouterr().err
    assert len(s.uris) == 8 + 10 * 2                 # 10 pages in a row failed, each tried twice; then it stopped
    kept = {u for u, _ in raw(db)}
    assert len(kept) == 8
    s = FakeSession(many)
    assert run(monkeypatch, db, s, "--only-missing") == 0
    assert not kept & set(s.uris)
    assert {u for u, _ in raw(db)} == set(many)
