"""Shared harness for the M1 scripture tests: a fake Church API, in-process CLI runs, and real-store guards.

Fixture tests never touch the network: requests' HTTPAdapter.send is patched to serve the recorded Church API
pages in tests/fixtures/scriptures/. Tests of the real store (db/scripture.db) and of anything that needs the
user-built db/core.<version>.db skip when those files are missing or empty.
"""
import contextlib
import io
import json
import os
import re
import runpy
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
API_DIR = Path(__file__).parent / "fixtures" / "scriptures"
FULL_DB = ROOT / "db" / "scripture.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API_HOST = "www.churchofjesuschrist.org"
CONTENT_PATH = "/study/api/v3/language-pages/type/content"

VOLUMES = ["ot", "nt", "bofm", "dc-testament", "pgp"]

# Pages served by the fake API (beyond the TOCs). Volume TOCs are filtered to these.
WORLD_PAGES = {
    "ot": ["gen/_contents", "gen/1", "gen/6", "gen/9", "ex/4", "ex/7", "ps/23", "isa/53"],
    "nt": ["john/3", "1-cor/13", "jude/1", "rev/22"],
    "bofm": ["title-page", "1-ne/3", "enos/1", "alma/32", "3-ne/11", "moro/7", "moro/10"],
    "dc-testament": ["introduction", "dc/45", "dc/76", "od/1"],
    "pgp": ["moses/1", "abr/fac-1", "js-h/1", "a-of-f/1"],
    "jst": ["jst-gen/1-8", "jst-gen/9", "jst-ex/4"],
}


# ---------------------------------------------------------------------------
# Fake Church API
# ---------------------------------------------------------------------------

def _load_page(uri: str) -> dict:
    fn = API_DIR / (uri.strip("/").replace("/", "__") + ".json")
    return json.loads(fn.read_text())


def _href_uri(href: str):
    m = re.match(r"/study(/scriptures/[^?#\"]+)", href)
    return m.group(1) if m else None


def _filter_toc(toc: dict, keep: set) -> dict:
    """Drop every <a> (and its <li>) whose target page is not in `keep`."""
    toc = json.loads(json.dumps(toc))
    body = toc["content"]["body"]

    def li_sub(m):
        hrefs = re.findall(r'href="([^"]+)"', m.group(0))
        uris = {_href_uri(h) for h in hrefs}
        return m.group(0) if uris & keep else ""

    # leaf <li ...><a ...>...</a></li> entries
    body = re.sub(r"<li[^>]*>\s*<a [^>]*>.*?</a>\s*</li>", li_sub, body, flags=re.S)
    # then book entries whose chapter list is now empty
    body = re.sub(r'<li data-content-type="book"[^>]*>(?:(?!<li).)*?<ul class="doc-map">\s*</ul>\s*</li>', "", body, flags=re.S)
    toc["content"]["body"] = body
    return toc


def build_world() -> dict:
    world = {}
    for vol, pages in WORLD_PAGES.items():
        uris = {f"/scriptures/{vol}/{p}" for p in pages}
        for u in uris:
            world[u] = _load_page(u)
        world[f"/scriptures/{vol}"] = _filter_toc(_load_page(f"/scriptures/{vol}"), uris)
    return world


def world_toc_links(world: dict, vol: str) -> set:
    body = world[f"/scriptures/{vol}"]["content"]["body"]
    return {u for u in (_href_uri(h) for h in re.findall(r'href="([^"]+)"', body)) if u}


class FakeAPI:
    """Patches requests' HTTPAdapter.send to serve `world`."""

    def __init__(self, world: dict):
        self.world = world
        self.requests = []          # (monotonic time, uri, user-agent, path)
        self.fail_after = None      # raise ConnectionError for every request after N served
        self.fail_uris = set()      # always 500 for these

    def __enter__(self):
        import requests
        from requests.adapters import HTTPAdapter
        from requests.models import Response

        api = self
        self._orig = HTTPAdapter.send

        def send(adapter, request, **kwargs):
            u = urlparse(request.url)
            if u.hostname != API_HOST:
                return api._orig(adapter, request, **kwargs)
            q = parse_qs(u.query)
            uri = unquote(q.get("uri", [""])[0])
            api.requests.append((time.monotonic(), uri, request.headers.get("User-Agent", ""), u.path))
            if api.fail_after is not None and len(api.requests) > api.fail_after:
                raise requests.exceptions.ConnectionError("fake network down")
            resp = Response()
            resp.url = request.url
            resp.request = request
            resp.headers["Content-Type"] = "application/json"
            if u.path != CONTENT_PATH:
                resp.status_code = 404
                resp._content = b'{"error":"wrong endpoint; use type/content"}'
            elif uri in api.fail_uris:
                resp.status_code = 500
                resp._content = b'{"error":"boom"}'
            elif uri in api.world:
                resp.status_code = 200
                resp._content = json.dumps(api.world[uri]).encode()
            else:
                resp.status_code = 404
                resp._content = b'{"error":"not found"}'
            return resp

        HTTPAdapter.send = send
        return self

    def __exit__(self, *exc):
        from requests.adapters import HTTPAdapter
        HTTPAdapter.send = self._orig
        return False


# ---------------------------------------------------------------------------
# Running the scripts in-process
# ---------------------------------------------------------------------------

def run_script(script: str, *args, fast: bool = True) -> tuple[int, str]:
    """runpy a script under scripts/ with argv; returns (exit code, combined output).

    fast=True removes the church_api throttle and retry delay for the duration of the run (restored afterwards).
    """
    import utils.church_api as ca

    path = ROOT / "scripts" / script
    assert path.exists(), f"missing {path.relative_to(ROOT)}"
    old_argv, old_env = sys.argv, dict(os.environ)
    old_timing = (ca.MIN_INTERVAL, ca.RETRY_DELAY)
    buf = io.StringIO()
    code = 0
    try:
        sys.argv = [str(path), *map(str, args)]
        if fast:
            ca.MIN_INTERVAL = 0.0
            ca.RETRY_DELAY = 0.0
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                runpy.run_path(str(path), run_name="__main__")
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            except Exception:  # noqa: BLE001 - a crash is a failure with output
                import traceback
                traceback.print_exc()
                code = 99
    finally:
        sys.argv = old_argv
        os.environ.clear()
        os.environ.update(old_env)
        ca.MIN_INTERVAL, ca.RETRY_DELAY = old_timing
    return code, buf.getvalue()


def q(db: Path, sql: str, params=()):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def q1(db: Path, sql: str, params=()):
    rows = q(db, sql, params)
    return rows[0][0] if rows else None


# ---------------------------------------------------------------------------
# core.db (read only through db.Database) and the real store: skip when absent
# ---------------------------------------------------------------------------

def _present(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 0


def need_core_db():
    from db import CORE_DB_PATH
    p = Path(CORE_DB_PATH)
    if not _present(p):
        pytest.skip(f"{p} is missing or empty (build it with `pipenv run python scripts/build.py --version 55`)")
    return p


def core_scalar(sql: str, params=()):
    need_core_db()
    from db import Database, CORE_DB_PATH
    return Database(CORE_DB_PATH, timeout=60).scalar(sql, params)


def core_select(sql: str, params=()):
    need_core_db()
    from db import Database, CORE_DB_PATH
    return Database(CORE_DB_PATH, timeout=60).select(sql, params)


def need_full_db():
    if not _present(FULL_DB):
        pytest.skip(f"{FULL_DB} is missing or empty (the real Church API store; run scripts/fetch_scriptures.py)")
    return FULL_DB


# ---------------------------------------------------------------------------
# Fixtures (imported by tests/conftest.py)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def world():
    return build_world()


@pytest.fixture(scope="session")
def fetched_db(tmp_path_factory, world):
    """A scripture.db holding the fake world's raw pages, produced by scripts/fetch_scriptures.py."""
    db = tmp_path_factory.mktemp("fetched") / "scripture.db"
    with FakeAPI(world):
        code, out = run_script("fetch_scriptures.py", "--db", db)
    assert code == 0, f"fetch_scriptures.py failed ({code}):\n{out[-2000:]}"
    return db


@pytest.fixture(scope="session")
def built_db(tmp_path_factory, fetched_db):
    """fetched_db after build_scriptures.py (needs the user-built core db for the JST import)."""
    need_core_db()
    db = tmp_path_factory.mktemp("built") / "scripture.db"
    shutil.copy(fetched_db, db)
    code, out = run_script("build_scriptures.py", "--db", db)
    assert code == 0, f"build_scriptures.py failed ({code}):\n{out[-2000:]}"
    return db


@pytest.fixture(scope="session")
def full_store(tmp_path_factory):
    """A temp copy of the real raw store; the real file is never opened by a test."""
    src = need_full_db()
    db = tmp_path_factory.mktemp("fullstore") / "scripture.db"
    shutil.copy(src, db)
    return db


@pytest.fixture(scope="session")
def full_built(tmp_path_factory, full_store):
    """build_scriptures.py run on a temp copy of the real store."""
    need_core_db()
    db = tmp_path_factory.mktemp("fullbuilt") / "scripture.db"
    shutil.copy(full_store, db)
    code, out = run_script("build_scriptures.py", "--db", db)
    print(out[-3000:])
    assert code == 0, f"build_scriptures.py failed on the full store ({code}):\n{out[-2500:]}"
    return db, out
