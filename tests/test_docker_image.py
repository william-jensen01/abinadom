"""The Dockerfile's server and tools targets, read statically with .dockerignore (no image is built).

Each stage's files are worked out from its COPY lines and the build context, written to a temp dir, and the
scripts are run from there with --help: an import the image would miss fails here.
"""
import os
import re
from pathlib import Path

import pytest

from tests.deploy_helpers import (CODE_DIR, PY, clean_env, context_files, excluded, ignore_rules, materialize, run,
                                  stage_filesystems)

pytestmark = pytest.mark.skipif(
    os.environ.get("SCI_TEST_DEPLOY") != "1",
    reason="starts many subprocesses (~45s); set SCI_TEST_DEPLOY=1 to run",
)


CHURCH_JSON = ["talk_metadata.json", "talk_previews.json", "conference_topics.json", "talk_corrections.json"]
# Scripts of the Docker deploy path, plus fetch.py, process_topics.py and the db helper: all must start in the image.
RUNNABLE = ["build.py", "fetch.py", "fetch_scriptures.py", "build_scriptures.py", "run_pipeline.py",
            "run_scripture_pipeline.py", "verify_weaviate_pipeline.py", "verify_weaviate_scripture.py",
            "field_coverage.py", "process_topics.py", "db_schema_extractor.py", "verify_chromadb_pipeline.py"]
NEVER = re.compile(r"(\.db|\.db-shm|\.db-wal|\.sqlite)$|^\.env$|(^|/)\.env$|^data/|^db/sci/|^\.git/|^\.goal/")
NOT_IN_SERVER = re.compile(r"^(scripts|db/one-off-migration|api|process_topic_talks|tests|docs|data|benchmark|"
                           r"\.planning|tasks|output)/|\.json$")


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


@pytest.mark.parametrize("target", ["server", "tools"])
def test_no_data_or_secrets_in_any_stage(target, stages):
    bad = sorted(p for p in (stages[target]["fs"].values()) if NEVER.search(p))
    assert not bad, f"{target} stage would contain {bad[:10]}"


def test_tools_stage_has_scripts_and_church_json(stages):
    files = _rel(stages["tools"])
    want = {f"scripts/{p.name}" for p in (CODE_DIR / "scripts").glob("*.py")}
    want |= {f"db/one-off-migration/{p.name}" for p in (CODE_DIR / "db" / "one-off-migration").glob("*.py")}
    want |= {f"db/one-off-migration/{j}" for j in CHURCH_JSON} | {"db/scripture_schema.sql", "server.py"}
    missing = sorted(want - files)
    assert not missing, f"tools stage misses {missing[:15]}"


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


def test_church_json_is_the_committed_copy(tools_tree):
    for j in CHURCH_JSON:
        a, b = tools_tree / "db" / "one-off-migration" / j, CODE_DIR / "db" / "one-off-migration" / j
        assert a.read_bytes() == b.read_bytes(), f"{j} in the tools image differs from the checkout"
