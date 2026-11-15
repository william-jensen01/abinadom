"""Scripts take their default paths from SCI_DB_DIR, SCRIPTURE_DB_PATH and SCI_REPORT_DIR.

Unset (or empty) -> the paths under the script's own checkout, whatever the cwd. Set -> under the variable.
An explicit flag beats both. 'Unset' cases run in a copy of the code tree so nothing real (data/failed_talks.json,
db/*.db) is read or written; every script runs from an unrelated cwd.
"""
import json
import os
import tempfile
from pathlib import Path

import pytest

from tests.deploy_helpers import CODE_DIR, PY, clean_env, copy_code_tree, probe_args, run, same_path

pytestmark = pytest.mark.skipif(
    os.environ.get("SCI_TEST_DEPLOY") != "1",
    reason="starts many subprocesses (~45s); set SCI_TEST_DEPLOY=1 to run",
)


SCRIPTURE_SCRIPTS = ["fetch_scriptures.py", "build_scriptures.py", "run_scripture_pipeline.py",
                     "verify_weaviate_scripture.py"]
# script -> report file name it writes by default under data/ today
REPORT_SCRIPTS = {"verify_weaviate_pipeline.py": "weaviate_verification_report.json",
                  "field_coverage.py": "field_coverage_report.json",
                  "verify_chromadb_pipeline.py": "verification_report.json"}


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    return copy_code_tree(tmp_path_factory.mktemp("code"))


@pytest.fixture
def cwd(tmp_path):
    d = tmp_path / "elsewhere"
    d.mkdir()
    return d


# ----------------------------------------------------------------------------- scripture.db (--db)
@pytest.mark.parametrize("script", SCRIPTURE_SCRIPTS)
def test_scripture_db_default_unset(script, tree, cwd):
    got = probe_args(tree, script, env=clean_env(), cwd=cwd)["db"]
    assert same_path(got, tree / "db" / "scripture.db"), f"{script}: unset default --db is {got}"


@pytest.mark.parametrize("script", SCRIPTURE_SCRIPTS)
def test_scripture_db_default_empty_is_unset(script, tree, cwd):
    got = probe_args(tree, script, env=clean_env(SCRIPTURE_DB_PATH=""), cwd=cwd)["db"]
    assert same_path(got, tree / "db" / "scripture.db"), f"{script}: SCRIPTURE_DB_PATH='' gives --db {got}"


@pytest.mark.parametrize("script", SCRIPTURE_SCRIPTS)
def test_scripture_db_from_env(script, tree, cwd, tmp_path):
    want = tmp_path / "vol" / "scripture.db"
    got = probe_args(tree, script, env=clean_env(SCRIPTURE_DB_PATH=want), cwd=cwd)["db"]
    assert same_path(got, want), f"{script}: SCRIPTURE_DB_PATH={want} gives --db {got}"


@pytest.mark.parametrize("script", SCRIPTURE_SCRIPTS)
def test_scripture_db_flag_wins(script, tree, cwd, tmp_path):
    flag = tmp_path / "flag" / "x.db"
    got = probe_args(tree, script, ["--db", str(flag)], env=clean_env(SCRIPTURE_DB_PATH=tmp_path / "env.db"),
                     cwd=cwd)["db"]
    assert same_path(got, flag), f"{script}: --db {flag} with SCRIPTURE_DB_PATH set gives {got}"


# ----------------------------------------------------------------------------- reports (--output)
@pytest.mark.parametrize("script,name", REPORT_SCRIPTS.items())
def test_report_default_unset(script, name, tree, cwd):
    for env in (clean_env(), clean_env(SCI_REPORT_DIR="")):
        got = probe_args(tree, script, env=env, cwd=cwd)["output"]
        assert same_path(got, tree / "data" / name), f"{script}: unset/empty SCI_REPORT_DIR gives --output {got}"


@pytest.mark.parametrize("script,name", REPORT_SCRIPTS.items())
def test_report_from_env(script, name, tree, cwd, tmp_path):
    rep = tmp_path / "reports"
    got = probe_args(tree, script, env=clean_env(SCI_REPORT_DIR=rep), cwd=cwd)["output"]
    assert same_path(got, rep / name), f"{script}: SCI_REPORT_DIR={rep} gives --output {got}"
    flag = tmp_path / "mine.json"
    got = probe_args(tree, script, ["--output", str(flag)], env=clean_env(SCI_REPORT_DIR=rep), cwd=cwd)["output"]
    assert same_path(got, flag), f"{script}: --output beats SCI_REPORT_DIR, got {got}"


# ----------------------------------------------------------------------------- failed_talks.json
def _from_failed(root, env, cwd):
    r = run([PY, str(root / "scripts" / "run_pipeline.py"), "--from-failed"], cwd=cwd, env=env)
    out = r.stdout + r.stderr
    assert r.returncode == 0 and "nothing to do" in out, f"run_pipeline --from-failed (exit {r.returncode}):\n{out[-1200:]}"
    return out


def test_run_pipeline_failed_talks_unset(tree, cwd):
    """With no failed_talks.json in the copy, --from-failed names the file it read and stops before Weaviate."""
    for env in (clean_env(), clean_env(SCI_REPORT_DIR="")):
        out = _from_failed(tree, env, cwd)
        assert str(tree / "data" / "failed_talks.json") in out, f"unset SCI_REPORT_DIR: {out[-600:]}"


def test_run_pipeline_failed_talks_from_env(tree, cwd, tmp_path):
    rep = tmp_path / "reports"
    rep.mkdir()
    (rep / "failed_talks.json").write_text("[]")
    out = _from_failed(tree, clean_env(SCI_REPORT_DIR=rep), cwd)
    assert str(rep / "failed_talks.json") in out, f"SCI_REPORT_DIR={rep}: {out[-600:]}"


_VERIFY_COUNTS = r"""
import json, os, sys
sys.path.insert(0, sys.argv[1])
import scripts.verify_weaviate_pipeline as m
class _DB:
    def select(self, *a, **k): return [{"cnt": 1}]
class _Agg:
    def over_all(self, **k): return type("R", (), {"total_count": 1})()
class _Col:
    aggregate = _Agg()
class _Cols:
    def use(self, name): return _Col()
    get = use
class _Client:
    collections = _Cols()
m.core_db = _DB()
info = m.check_counts(_Client()).get("failed_talks_file") or {}
print("FAILED_PATH " + json.dumps(info.get("path")))
"""


def _verify_failed_path(root, env, cwd):
    r = run([PY, "-c", _VERIFY_COUNTS, str(root)], cwd=cwd, env=env)
    for line in r.stdout.splitlines():
        if line.startswith("FAILED_PATH "):
            return json.loads(line[len("FAILED_PATH "):])
    raise AssertionError(f"verify_weaviate_pipeline.check_counts with stub client/core_db failed "
                         f"(exit {r.returncode}):\n{(r.stdout + r.stderr)[-1200:]}")


def test_verify_pipeline_reads_failed_talks_unset(tree, cwd):
    (tree / "data").mkdir(exist_ok=True)
    (tree / "data" / "failed_talks.json").write_text("[]")
    try:
        got = _verify_failed_path(tree, clean_env(), cwd)
    finally:
        (tree / "data" / "failed_talks.json").unlink()
    assert got and same_path(got, tree / "data" / "failed_talks.json"), f"unset: reads {got}"


def test_verify_pipeline_reads_failed_talks_from_env(tree, cwd, tmp_path):
    rep = tmp_path / "reports"
    rep.mkdir()
    (rep / "failed_talks.json").write_text("[]")
    got = _verify_failed_path(tree, clean_env(SCI_REPORT_DIR=rep), cwd)
    assert got and same_path(got, rep / "failed_talks.json"), f"SCI_REPORT_DIR={rep}: reads {got}"


def test_run_pipeline_creates_missing_report_dir(tree, cwd, tmp_path):
    """A fresh /data/reports does not exist yet: recording a failure must create it (and not touch data/)."""
    rep = tmp_path / "fresh" / "reports"
    code = ("import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/scripts');"
            "import run_pipeline as m; m._record_failure(4242, 'boom', [])")
    r = run([PY, "-c", code, str(tree)], cwd=cwd, env=clean_env(SCI_REPORT_DIR=rep))
    assert r.returncode == 0, (r.stdout + r.stderr)[-1200:]
    data = json.loads((rep / "failed_talks.json").read_text())
    assert [e["talk_id"] for e in data] == [4242], data
    assert not (tree / "data" / "failed_talks.json").exists(), "wrote data/failed_talks.json with SCI_REPORT_DIR set"


# ----------------------------------------------------------------------------- build.py
def _build(root, env, cwd):
    # 99: a release number with no files anywhere (db/sci holds 55 only), so build.py stops before building
    r = run([PY, str(root / "scripts" / "build.py"), "--version", "99"], cwd=cwd, env=env)
    return r.returncode, r.stdout + r.stderr


def test_build_raw_and_output_unset(tree, cwd):
    db = tree / "db"
    for env in (clean_env(), clean_env(SCI_DB_DIR="")):
        code, out = _build(tree, env, cwd)
        assert code != 0 and str(db / "sci" / "core.99.db") in out, f"unset SCI_DB_DIR, raw path:\n{out[-800:]}"
    (db / "sci").mkdir(exist_ok=True)
    made = [db / "sci" / "core.99.db", db / "sci" / "content.99.db", db / "core.99.db"]
    for p in made:
        p.write_bytes(b"")                    # empty placeholders, never real databases
    try:
        code, out = _build(tree, clean_env(), cwd)
        assert code != 0 and "Build already exists" in out and str(db / "core.99.db") in out, \
            f"unset SCI_DB_DIR, output path:\n{out[-800:]}"
    finally:
        for p in made:
            p.unlink()


def test_build_raw_and_output_from_env(tree, cwd, tmp_path):
    vol = tmp_path / "vol"
    vol.mkdir()
    code, out = _build(tree, clean_env(SCI_DB_DIR=vol), cwd)
    assert code != 0 and str(vol / "sci" / "core.99.db") in out, f"SCI_DB_DIR={vol}, raw path:\n{out[-800:]}"
    (vol / "sci").mkdir()
    for p in (vol / "sci" / "core.99.db", vol / "sci" / "content.99.db", vol / "core.99.db"):
        p.write_bytes(b"")
    code, out = _build(tree, clean_env(SCI_DB_DIR=vol), cwd)
    assert code != 0 and "Build already exists" in out and str(vol / "core.99.db") in out, \
        f"SCI_DB_DIR={vol}, output path:\n{out[-800:]}"
    assert not list((tree / "db").glob("*.99.*")), "build.py wrote under the code's db/ with SCI_DB_DIR set"


def test_real_checkout_untouched():
    """None of the above may have written into the real checkout."""
    assert not list((CODE_DIR / "db").glob("*.99.*")), list((CODE_DIR / "db").glob("*.99.*"))
