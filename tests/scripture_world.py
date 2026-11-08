"""Shared harness for the scripture tests: a fake Church API, in-process CLI runs, and real-store guards.

Fixture tests never touch the network: requests' HTTPAdapter.send is patched to serve the recorded Church API
pages in tests/fixtures/scriptures/. Tests of the real store (db/scripture.db) and of anything that needs the
user-built db/core.<version>.db skip when those files are missing or empty.
"""
import contextlib
import hashlib
import io
import json
import math
import os
import re
import runpy
import shutil
import socket
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

def run_script(script: str, *args, env: dict | None = None, fast: bool = True) -> tuple[int, str]:
    """runpy a script under scripts/ with argv; returns (exit code, combined output).

    env is merged into os.environ for the run (restored afterwards). fast=True removes the church_api throttle and retry delay for the duration of the run (restored afterwards).
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
        if env:
            os.environ.update({k: str(v) for k, v in env.items()})
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


# ---------------------------------------------------------------------------
# Embedded Weaviate + fake embedder (no network, no real Weaviate)
# ---------------------------------------------------------------------------

DIM = 64


def fake_vector(text: str, dim: int = DIM) -> list[float]:
    """Hashed bag of words: deterministic, and texts that share words land close together."""
    v = [0.0] * dim
    for w in re.findall(r"[a-z]+", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class EmbedHandler(BaseHTTPRequestHandler):
    """llama-server /v1/embeddings shape. calls counts embedded texts; fail_after interrupts a load with a 500."""
    calls = 0
    fail_after = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_POST(self):
        inputs = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}").get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]
        if EmbedHandler.fail_after is not None and EmbedHandler.calls + len(inputs) > EmbedHandler.fail_after:
            out, status = b"", 500
        else:
            EmbedHandler.calls += len(inputs)
            out = json.dumps({"data": [{"index": i, "embedding": fake_vector(t), "object": "embedding"}
                                       for i, t in enumerate(inputs)]}).encode()
            status = 200
        self.send_response(status)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def weaviate_env(tmp_path_factory):
    """(client, env) for an embedded Weaviate and a fake embedder, shared by the whole session (two embedded
    instances cannot run side by side). Seeded with the talk collections so server.py can start against it."""
    import weaviate
    from weaviate.classes.config import Configure, DataType, Property
    from config.pipeline_config import WEAVIATE_COLLECTION_NAMES

    srv = ThreadingHTTPServer(("127.0.0.1", 0), EmbedHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port, grpc = free_port(), free_port()
    client = weaviate.connect_to_embedded(
        port=port, grpc_port=grpc, persistence_data_path=str(tmp_path_factory.mktemp("weaviate")),
        environment_variables={"DISABLE_TELEMETRY": "true", "LOG_LEVEL": "error"})
    for name in WEAVIATE_COLLECTION_NAMES.values():
        if not client.collections.exists(name):
            client.collections.create(name, vector_config=Configure.Vectors.self_provided(),
                                      properties=[Property(name="text", data_type=DataType.TEXT)])
        client.collections.use(name).data.insert({"text": "seed"}, vector=[0.1] * DIM)
    yield client, {"WEAVIATE_HOST": "localhost", "WEAVIATE_PORT": str(port), "WEAVIATE_GRPC_PORT": str(grpc),
                   "EMBEDDING_URL": f"http://127.0.0.1:{srv.server_address[1]}"}
    client.close()
    srv.shutdown()


@pytest.fixture(scope="module")
def loaded(tmp_path_factory, built_db, weaviate_env):
    """built_db loaded into the embedded Weaviate by run_scripture_pipeline.py. Returns (db, client, env), where
    env also points the server at the db copy (SCRIPTURE_DB_PATH)."""
    client, env = weaviate_env
    for n in ("ScriptureVerses", "ScriptureChapters", "ScriptureMeta"):
        if client.collections.exists(n):
            client.collections.delete(n)
    db = tmp_path_factory.mktemp("loaded") / "scripture.db"
    shutil.copy(built_db, db)
    e = dict(env, SCRIPTURE_DB_PATH=str(db))
    code, out = run_script("run_scripture_pipeline.py", "--db", db, env=e)
    assert code == 0, f"run_scripture_pipeline.py failed ({code}):\n{out[-2000:]}"
    return db, client, e


# ---------------------------------------------------------------------------
# Calling the MCP tools on the real server module, in-process
# ---------------------------------------------------------------------------

def _tool_text(result) -> str:
    parts = [t for t in (getattr(c, "text", None) for c in (getattr(result, "content", result) or [])) if t is not None]
    if not parts and getattr(result, "data", None) is not None:
        d = result.data
        return d if isinstance(d, str) else json.dumps(d)
    return "\n".join(parts)


@contextlib.contextmanager
def _server_env(env: dict, unset: tuple = ()):
    old = dict(os.environ)
    for k in unset:
        os.environ.pop(k, None)
    os.environ.update({k: str(v) for k, v in env.items()})
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


def call_tools(env: dict, calls: list[tuple[str, dict]], unset: tuple = ()) -> list:
    """Start server.py's lifespan once under env, run each (tool, args), return the parsed results.

    A result is the tool's JSON (dict/list) when it parses, else the raw text.
    """
    import asyncio
    import importlib

    async def go():
        from fastmcp import Client
        import server
        importlib.reload(server)
        out = []
        async with Client(server.mcp) as c:
            for name, args in calls:
                try:
                    txt = _tool_text(await c.call_tool(name, args, raise_on_error=False))
                except Exception as e:  # noqa: BLE001
                    txt = f"TOOL ERROR: {e}"
                try:
                    out.append(json.loads(txt))
                except Exception:
                    out.append(txt)
        return out

    with _server_env(env, unset):
        return asyncio.run(go())


def health(env: dict, unset: tuple = ()) -> tuple[int, str]:
    """Start the server lifespan under env, then call its /health handler; returns (status, body)."""
    import asyncio
    import importlib

    async def go():
        from fastmcp import Client
        from starlette.requests import Request
        import server
        importlib.reload(server)
        async with Client(server.mcp) as c:
            await c.list_tools()
            req = Request({"type": "http", "method": "GET", "path": "/health", "headers": [], "query_string": b""})
            resp = await server.health_handler(req)
            return resp.status_code, resp.body.decode()

    with _server_env(env, unset):
        return asyncio.run(go())


def find_verse(result, verse: int):
    for v in (result or {}).get("verses", []):
        if int(v.get("verse", -1)) == verse:
            return v
    return None


def blob(x) -> str:
    return json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x
