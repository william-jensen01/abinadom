"""The Dockerfile's server and tools targets, read statically with .dockerignore (no image is built).

Each stage's files are worked out from its COPY lines and the build context, written to a temp dir, and the
scripts are run from there with --help: an import the image would miss fails here.
"""
import http.server
import json
import os
import re
import threading
from pathlib import Path

import pytest

from tests.deploy_helpers import (CODE_DIR, PY, _copy_args, clean_env, compose_project, context_files, excluded,
                                  ignore_rules, materialize, parse_dockerfile, render, run, stage_filesystems)

pytestmark = pytest.mark.skipif(
    os.environ.get("SCI_TEST_DEPLOY") != "1",
    reason="starts many subprocesses (~45s); set SCI_TEST_DEPLOY=1 to run",
)


CHURCH_JSON = ["talk_metadata.json", "talk_previews.json", "conference_topics.json", "talk_corrections.json"]
# Scripts of the Docker deploy path, plus fetch.py, process_topics.py and the db helper: all must start in the image.
RUNNABLE = ["build.py", "fetch.py", "fetch_scriptures.py", "build_scriptures.py", "run_pipeline.py",
            "run_scripture_pipeline.py", "verify_weaviate_pipeline.py", "verify_weaviate_scripture.py",
            "field_coverage.py", "process_topics.py", "db_schema_extractor.py"]
NEVER = re.compile(r"(\.db|\.db-shm|\.db-wal|\.sqlite)$|^\.env$|(^|/)\.env$|^data/|^db/sci/|^\.git/|^\.goal/")
NOT_IN_SERVER = re.compile(r"^(scripts|db/one-off-migration|api|process_topic_talks|tests|docs|data|benchmark|"
                           r"\.planning|tasks|output)/|^(?!skills/).*\.json$")


# Files a deploy machine may hold that this checkout does not (infra/.env on the hosted server, finished dbs,
# the raw release, reports, the planning dir). Any the .dockerignore lets through count as part of the context.
ELSEWHERE = ["infra/.env", ".env", "db/core.55.db", "db/content.55.db", "db/scripture.db", "db/sci/core.55.db",
             "db/build_report.55.json", "data/failed_talks.json", "data/reports/x.json", ".goal/GOAL.md",
             "http_cache.sqlite", "db/reports/failed_talks.json"]


@pytest.fixture(scope="module")
def stages():
    rules = ignore_rules()
    ctx = context_files() | {p for p in ELSEWHERE if not excluded(p, rules)}
    return stage_filesystems(ctx=ctx)


def _rel(stage):
    wd = stage["workdir"].rstrip("/") + "/"
    return {p[len(wd):] for p in stage["fs"] if p.startswith(wd)}


def test_both_targets_exist(stages):
    for t in ("server", "tools"):
        assert t in stages, f"Dockerfile needs a stage named {t!r}; has {[k for k in stages]}"
        assert stages[t]["workdir"] == "/app", f"{t}: WORKDIR {stages[t]['workdir']} (the code lives in /app)"


def test_no_dead_mcp_env():
    text = (CODE_DIR / "Dockerfile").read_text()
    assert not re.search(r"^\s*ENV\s+MCP_(HOST|PORT)\b", text, re.M), "Dockerfile still sets MCP_HOST/MCP_PORT (the server reads FASTMCP_*)"


def test_server_runs_server_py(stages):
    cmds = [r for op, r in stages["server"]["instrs"] if op in ("CMD", "ENTRYPOINT")]
    assert cmds and "server.py" in cmds[-1], f"server stage must start server.py: {cmds}"


def test_server_stage_is_lean(stages):
    files = _rel(stages["server"])
    assert "server.py" in files and "db/__init__.py" in files and "db/scripture.py" in files, "server stage misses server code"
    extra = sorted(f for f in files if NOT_IN_SERVER.search(f))
    assert not extra, f"server stage carries tool or data files: {extra[:10]}"


def test_server_stage_carries_every_skill_file(stages):
    files = _rel(stages["server"])
    repo = {p.relative_to(CODE_DIR).as_posix() for p in (CODE_DIR / "skills").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}
    assert repo, "skills/ holds no files"
    missing = sorted(repo - files)
    assert not missing, f"server stage misses skill files: {missing}"


def test_skill_json_and_txt_reach_the_lean_server_stage():
    """Reference files a skill adds later (.json, .txt) pass .dockerignore and are not flagged as tool or data files."""
    rules = ignore_rules()
    extra = {"skills/x/references/table.json", "skills/x/references/list.txt"}
    assert not any(excluded(p, rules) for p in extra), "skill .json/.txt files would be dropped from the context"
    files = _rel(stage_filesystems(ctx=context_files() | extra)["server"])
    assert extra <= {f"skills/{p[len('skills/'):]}" for p in files if p.startswith("skills/")}
    assert not sorted(f for f in files if NOT_IN_SERVER.search(f)), "a skill file trips the lean server check"


@pytest.mark.parametrize("target", ["server", "tools"])
def test_no_data_or_secrets_in_any_stage(target, stages):
    bad = sorted(p for p in (stages[target]["fs"].values()) if NEVER.search(p))
    assert not bad, f"{target} stage would contain {bad[:10]}"


def test_tools_stage_has_scripts_and_church_json(stages):
    files = _rel(stages["tools"])
    # verify_chromadb_pipeline.py stays out: chromadb is a dev package, so the script could not start in the image
    want = {f"scripts/{p.name}" for p in (CODE_DIR / "scripts").glob("*.py")} - {"scripts/verify_chromadb_pipeline.py"}
    want |= {f"db/one-off-migration/{p.name}" for p in (CODE_DIR / "db" / "one-off-migration").glob("*.py")}
    want |= {f"db/one-off-migration/{j}" for j in CHURCH_JSON} | {"db/scripture_schema.sql", "server.py"}
    missing = sorted(want - files)
    assert not missing, f"tools stage misses {missing[:15]}"
    assert "scripts/verify_chromadb_pipeline.py" not in files, "the tools image has no chromadb for this script"


@pytest.fixture(scope="module")
def tools_tree(stages, tmp_path_factory):
    return materialize(stages["tools"], tmp_path_factory.mktemp("tools-image"))


@pytest.fixture(scope="module")
def server_tree(stages, tmp_path_factory):
    return materialize(stages["server"], tmp_path_factory.mktemp("server-image"))


@pytest.mark.parametrize("script", RUNNABLE)
def test_script_starts_in_tools_image(script, tools_tree):
    # As `docker compose run --rm tools scripts/<x>.py` does: cwd is the WORKDIR, the script's dir leads sys.path.
    r = run([PY, "-s", str(tools_tree / "scripts" / script), "--help"], cwd=tools_tree, env=clean_env())
    assert r.returncode == 0, f"{script} --help in the tools image tree (exit {r.returncode}):\n{(r.stdout + r.stderr)[-900:]}"


def test_server_imports_in_server_image(server_tree):
    r = run([PY, "-s", "-c", "import server"], cwd=server_tree, env=clean_env())
    assert r.returncode == 0, f"import server in the server image tree:\n{(r.stdout + r.stderr)[-900:]}"


def test_server_image_serves_every_skill_byte_for_byte(server_tree):
    """Started from the server image's file tree, the server lists each skill in skills/ with identical files."""
    probe = r'''
import asyncio, base64, json
from unittest.mock import MagicMock, patch
import server
from fastmcp import Client
from fastmcp.skills import SkillsClientExtension
async def go():
    out = {}
    async with Client(server.mcp, extensions=[SkillsClientExtension()]) as c:
        for e in await c.list_skills():
            sk = await c.read_skill(e.uri)
            out[str(e.frontmatter.name)] = {k: base64.b64encode(v.content if hasattr(v, "content") else bytes(v)).decode()
                                            for k, v in sk.files.items()}
    return out
with patch("server._startup", return_value=server.AppContext(client=MagicMock())):
    print("@@" + json.dumps(asyncio.run(go())))
'''
    r = run([PY, "-s", "-c", probe], cwd=server_tree, env=clean_env())
    line = [l for l in r.stdout.splitlines() if l.startswith("@@")]
    assert r.returncode == 0 and line, f"serving skills from the server image tree:\n{(r.stdout + r.stderr)[-900:]}"
    import base64
    got = {n: {k: base64.b64decode(v) for k, v in files.items()} for n, files in json.loads(line[-1][2:]).items()}
    want = {}
    for skill_md in (CODE_DIR / "skills").glob("*/SKILL.md"):
        folder = skill_md.parent
        want[folder.name] = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert got == want


def test_church_json_is_the_committed_copy(tools_tree):
    for j in CHURCH_JSON:
        a, b = tools_tree / "db" / "one-off-migration" / j, CODE_DIR / "db" / "one-off-migration" / j
        assert a.read_bytes() == b.read_bytes(), f"{j} in the tools image differs from the checkout"


# --------------------------------------------------------------------------- the Dockerfile adds no modes or owners
def test_no_run_changes_modes_or_owners_and_tools_stage_has_no_run():
    stages = parse_dockerfile((CODE_DIR / "Dockerfile").read_text())
    bad = [f"{st['name']}: RUN {rest}" for st in stages for op, rest in st["instrs"]
           if op == "RUN" and re.search(r"chmod|chown|umask|/app\b", rest)]
    assert not bad, f"the Dockerfile changes ownership or modes, or touches /app, with RUN: {bad}"
    tools = [st for st in stages if (st["name"] or "").lower() == "tools"]
    assert tools, "no tools stage"
    runs = [rest for op, rest in tools[0]["instrs"] if op == "RUN"]
    assert not runs, f"the tools stage needs no RUN (it only adds files to the server stage): {runs}"


def test_copy_chmod_only_on_named_files():
    # --chmod on a directory source would set that directory's mode too; only the rewritten files may get one
    for st in parse_dockerfile((CODE_DIR / "Dockerfile").read_text()):
        for op, rest in st["instrs"]:
            if op in ("COPY", "ADD"):
                flags, srcs, dest = _copy_args(rest)
                if "chmod" in flags:
                    not_files = [s for s in srcs if not (CODE_DIR / s).is_file()]
                    assert not not_files, f"COPY --chmod on something other than a named file: {not_files} ({rest})"


# --------------------------------------------------------------------------- what the tools stage leaves out
def test_tools_stage_leaves_out_audit_sample_and_migration_sql(stages):
    files = set(stages["tools"]["fs"])
    assert "/app/config/audit_sample.json" not in files, "the tools image carries config/audit_sample.json"
    bad = sorted(p for p in files if re.search(r"/db/one-off-migration/[^/]+\.sql$", p))
    assert not bad, f"the tools image carries one-off migration SQL: {bad}"
    assert "/app/db/scripture_schema.sql" in files, "db/scripture_schema.sql left the tools image"


def test_dockerfile_says_run_audit_is_left_out():
    comments = [l for l in (CODE_DIR / "Dockerfile").read_text().splitlines() if l.lstrip().startswith("#")]
    assert any("run_audit" in l for l in comments), "no Dockerfile comment says run_audit.py is left out on purpose"


def test_run_audit_in_the_image_says_to_run_it_on_the_host(tools_tree, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    r = run([PY, "-s", str(tools_tree / "scripts" / "run_audit.py")], cwd=tools_tree,
            env=clean_env(SCI_DB_DIR=data, SCI_REPORT_DIR=data / "reports"))
    out = r.stdout + r.stderr
    assert r.returncode != 0, f"run_audit.py in the tools image exited 0:\n{out[-800:]}"
    assert "Traceback" not in out, f"run_audit.py in the tools image crashed instead of explaining:\n{out[-1200:]}"
    assert re.search(r"\bhost\b", out, re.I), f"run_audit.py in the tools image must say it runs on the host:\n{out[-800:]}"


# --------------------------------------------------------------------------- fetch.py with the image read-only
TALK = "/general-conference/2026/04/99zzcheck"
TOPIC = "/general-conference/topics/zz-check-topic"
TOPICS_INDEX = "/general-conference/topics"

# Runs <root>/scripts/fetch.py --conference 2026-04 against the fake API (only the base URL and throttle are patched).
FETCH_RUNNER = """
import runpy, sys
root, base = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
import utils.church_api as c
c.API_BASE_URL = base
c.MIN_INTERVAL = 0
c.RETRY_DELAY = 0
sys.argv = [root + "/scripts/fetch.py", "--conference", "2026-04"]
runpy.run_path(root + "/scripts/fetch.py", run_name="__main__")
"""


@pytest.fixture(scope="module")
def fake_api():
    pages = {
        "/general-conference/2026/04": {"toc": {"entries": [{}, {"section": {"entries": [
            {"content": {"uri": TALK, "title": "Check Talk", "subtitle": ""}}]}}]}},
        TALK: {"content": {
            "meta": {"title": "Check Talk", "pageAttributes": {"data-aid": "424242"}},
            "content": {"body": '<p class="author-role">Of the Seventy</p>',
                        "head": {"page-meta-social": {"pageMeta": {"description": "Check preview"}}}}}},
        TOPICS_INDEX: {"collection": {"sections": [{"entries": [{"type": "search", "items": [
            {"type": "collection", "title": "zz-check-topic", "uri": TOPIC}]}]}]}},
        TOPIC: {"collection": {"sections": [{"entries": [{"uri": TALK, "title": "Check Talk"}]}]}},
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            uri = self.path.split("uri=", 1)[1] if "uri=" in self.path else ""
            body = pages.get(uri)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api?lang=eng&uri="
    srv.shutdown()


def _chmod_files(stages):
    """{absolute image path: mode} for every file a tools-stage `COPY --chmod=` puts in the image."""
    out, wd_by = {}, {}
    for i, st in enumerate(parse_dockerfile((CODE_DIR / "Dockerfile").read_text())):
        wd = wd_by.get(st["base"].lower(), "/")          # a stage built FROM another starts in its WORKDIR
        for op, rest in st["instrs"]:
            if op == "WORKDIR":
                wd = os.path.normpath(os.path.join(wd, rest.strip()))
            if op in ("COPY", "ADD"):
                flags, srcs, dest = _copy_args(rest)
                if "chmod" in flags and "from" not in flags:
                    mini = f"FROM scratch AS x\nWORKDIR {wd}\nCOPY {' '.join(srcs)} {dest}\n"
                    for p in stage_filesystems(dockerfile_text=mini, ctx=context_files())["x"]["fs"]:
                        out[p] = int(flags["chmod"], 8)
        wd_by[(st["name"] or str(i)).lower()] = wd
        if (st["name"] or "").lower() == "tools":
            break
    return out


def test_fetch_runs_as_another_uid_with_the_image_read_only(fake_api, stages, tmp_path):
    import requests_cache
    from urllib.parse import unquote

    if os.geteuid() == 0:
        pytest.skip("root ignores the file modes this test relies on")
    (tmp_path / "compose").mkdir()
    cfg = render(compose_project(tmp_path / "compose"), ["docker-compose.yml"])
    value = str((cfg["services"]["tools"].get("environment") or {}).get("SCI_HTTP_CACHE") or "")
    assert value.startswith("/data/"), f"tools service: SCI_HTTP_CACHE={value!r}; want a path under /data"

    tree = materialize(stages["tools"], tmp_path / "image")
    data = tmp_path / "data"
    data.mkdir()
    cache = data / os.path.relpath(value, "/data")
    # The image as a uid that owns nothing: directories not writable, files read-only, except COPY --chmod files.
    modes = {tmp_path / "image" / p.lstrip("/"): m for p, m in _chmod_files(stages).items()}
    for dirpath, _dirs, filenames in os.walk(tmp_path / "image"):
        for f in filenames:
            p = Path(dirpath) / f
            p.chmod(modes.get(p, 0o444) & 0o777)
    for dirpath, _dirs, _files in os.walk(tmp_path / "image", topdown=False):
        Path(dirpath).chmod(0o555)
    try:
        runner = tmp_path / "fetch_runner.py"
        runner.write_text(FETCH_RUNNER)
        env = clean_env(PYTHONDONTWRITEBYTECODE="1", NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost",
                        SCI_DB_DIR=data, SCI_REPORT_DIR=data / "reports", SCI_HTTP_CACHE=cache)
        r = run([PY, "-s", str(runner), str(tree), fake_api], cwd=tree, env=env, timeout=180)
        out = (r.stdout + r.stderr)[-1500:]
        assert r.returncode == 0, f"fetch.py --conference 2026-04 with the image read-only (exit {r.returncode}):\n{out}"
        topics = json.loads((tree / "topics.json").read_text())
        assert [t["uri"] for t in topics] == [TOPIC], f"topics.json was not rewritten by fetch:\n{out}"
        meta = json.loads((tree / "db" / "one-off-migration" / "talk_metadata.json").read_text())
        assert any(m["uri"] == TALK for m in meta), "talk_metadata.json was not rewritten by fetch"
        assert cache.is_file(), f"no HTTP cache at {cache}"
        cached = [unquote(u) for u in requests_cache.CachedSession(str(cache), backend="sqlite").cache.urls()]
        assert any(TALK in u for u in cached), f"the talk page is not cached in {cache}"
    finally:
        for dirpath, _dirs, _files in os.walk(tmp_path / "image"):
            Path(dirpath).chmod(0o755)
