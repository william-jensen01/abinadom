"""scripts/setup_data.py prepares one category of data per run and never loads Weaviate.

  setup_data.py talks [--version N|latest] [--base-url URL] [--force]   fetch_sci.py, then build.py --version <N>
  setup_data.py scriptures                                               fetch_scriptures.py, then build_scriptures.py

Runs in a copy of the code tree whose build, scripture and load/verify scripts are replaced by stubs that record how
they were run (each step runs as its own script). fetch_sci.py is the real one, against the local fake release site.
"""
import json
import os
import re

import pytest

from tests.deploy_helpers import PY, clean_env, copy_code_tree, run
from tests.sci_server import SciServer, release_zip

pytestmark = pytest.mark.skipif(
    os.environ.get("SCI_TEST_DEPLOY") != "1",
    reason="starts many subprocesses (~25s); set SCI_TEST_DEPLOY=1 to run",
)

STEPS = ["build.py", "fetch_scriptures.py", "build_scriptures.py"]
LOADS = ["run_pipeline.py", "verify_weaviate_pipeline.py", "run_scripture_pipeline.py", "verify_weaviate_scripture.py",
         "verify_chromadb_pipeline.py", "field_coverage.py", "UPDATE.py", "upgrade.py"]

# STUB_REPORT="<sci unexpected>,<church unexpected>": the build stub writes $SCI_DB_DIR/build_report.<N>.json shaped
# like the real one (keys as in db/build_report.55.json: 9 expected Ensign-only talks, 0 unexpected on 2026-11-15).
STUB = r'''
import json, os, sys
name = os.path.basename(__file__)
with open(os.environ["SETUP_RECORD"], "a") as f:
    f.write(json.dumps({"script": name, "argv": sys.argv[1:], "SCI_DB_DIR": os.environ.get("SCI_DB_DIR")}) + "\n")
spec = os.environ.get("STUB_REPORT")
if name == "build.py" and spec:
    n = sys.argv[sys.argv.index("--version") + 1]
    sci_k, church_k = (int(x) for x in spec.split(","))
    talk = lambda i, y: {"talk_id": 9000 + i, "date": f"{y}-04-05", "title": f"Talk {i}", "uri_gc": None}
    report = {
        "sci_conference_talks": 4100, "matched": 4090,
        "sci_talks_without_church_data": {"expected_ensign": [talk(i, 1978) for i in range(9)],
                                          "unexpected": [talk(100 + i, 2027) for i in range(sci_k)]},
        "church_uris_without_sci_talk": {"expected": {"sustaining": 12},
                                         "unexpected": [{"uri": f"/general-conference/2027/04/{i}x", "title": "t"}
                                                        for i in range(church_k)]},
        "topic_entries_without_sci_talk": {"expected": {}, "unexpected": []},
    }
    with open(os.path.join(os.environ["SCI_DB_DIR"], f"build_report.{n}.json"), "w") as f:
        json.dump(report, f)
sys.exit(int(os.environ.get("STUB_EXIT_" + name.replace(".", "_"), "0")))
'''


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    t = copy_code_tree(tmp_path_factory.mktemp("code"))
    for s in STEPS + LOADS:
        (t / "scripts" / s).write_text(STUB)
    return t


@pytest.fixture
def ctx(tmp_path):
    vol = tmp_path / "vol"
    vol.mkdir()
    return vol, tmp_path / "record.jsonl"


def setup(tree, vol, record, args, **extra):
    env = clean_env(SCI_DB_DIR=vol, SETUP_RECORD=record, **extra)
    if "SCI_DB_VERSION" not in extra:
        env.pop("SCI_DB_VERSION", None)
    r = run([PY, str(tree / "scripts" / "setup_data.py"), *map(str, args)], cwd=vol.parent, env=env, timeout=180)
    calls = [json.loads(l) for l in record.read_text().splitlines()] if record.exists() else []
    return r.returncode, r.stdout + r.stderr, calls


def no_loads(calls):
    loads = [c["script"] for c in calls if c["script"] in LOADS]
    assert not loads, f"setup_data.py must never load or verify Weaviate; it ran {loads}"


def test_talks_pinned(tree, ctx):
    vol, rec = ctx
    with SciServer({55: release_zip(55)}) as s:
        code, out, calls = setup(tree, vol, rec, ["talks", "--version", 55, "--base-url", s.url])
    assert code == 0, f"setup_data.py talks --version 55 failed:\n{out[-1500:]}"
    assert (vol / "sci" / "core.55.db").exists(), "talks must fetch the release into $SCI_DB_DIR/sci first"
    assert [c["script"] for c in calls] == ["build.py"], f"talks must run build.py once, as its own script: {calls}"
    argv = calls[0]["argv"]
    assert argv[argv.index("--version") + 1] == "55" and "--force" not in argv, f"build.py args: {argv}"
    assert calls[0]["SCI_DB_DIR"] == str(vol), "build.py must see the same SCI_DB_DIR"
    assert "SCI_DB_VERSION=55" in out, f"must end by naming the .env line SCI_DB_VERSION=55:\n{out[-600:]}"
    no_loads(calls)


def test_talks_latest_builds_what_it_found(tree, ctx):
    vol, rec = ctx
    with SciServer({55: release_zip(55), 57: release_zip(57)}) as s:
        code, out, calls = setup(tree, vol, rec, ["talks", "--version", "latest", "--base-url", s.url])
    assert code == 0, out[-1500:]
    assert [c["script"] for c in calls] == ["build.py"], calls
    argv = calls[0]["argv"]
    assert argv[argv.index("--version") + 1] == "57", f"latest found 57, build.py got {argv}"
    assert "SCI_DB_VERSION=57" in out, f"must tell the user to set SCI_DB_VERSION=57:\n{out[-600:]}"
    no_loads(calls)


def test_talks_default_version_and_force(tree, ctx):
    vol, rec = ctx
    with SciServer({53: release_zip(53)}) as s:
        code, out, calls = setup(tree, vol, rec, ["talks", "--base-url", s.url, "--force"], SCI_DB_VERSION="53")
    assert code == 0, out[-1500:]
    argv = calls[0]["argv"]
    assert argv[argv.index("--version") + 1] == "53" and "--force" in argv, \
        f"no --version uses SCI_DB_VERSION (53); --force is passed to build.py: {argv}"


def test_talks_fetch_failure_stops_before_build(tree, ctx):
    vol, rec = ctx
    with SciServer({55: release_zip(55)}) as s:
        code, out, calls = setup(tree, vol, rec, ["talks", "--version", 54, "--base-url", s.url])
    assert code != 0, "a failed fetch must fail setup"
    assert calls == [], f"build.py must not run after a failed fetch: {calls}"


def test_talks_build_failure_fails(tree, ctx):
    vol, rec = ctx
    with SciServer({55: release_zip(55)}) as s:
        code, out, calls = setup(tree, vol, rec, ["talks", "--version", 55, "--base-url", s.url], STUB_EXIT_build_py="3")
    assert code != 0 and [c["script"] for c in calls] == ["build.py"], f"a failed build must fail setup (exit {code})"


def test_scriptures(tree, ctx):
    vol, rec = ctx
    code, out, calls = setup(tree, vol, rec, ["scriptures"])
    assert code == 0, out[-1500:]
    assert [c["script"] for c in calls] == ["fetch_scriptures.py", "build_scriptures.py"], \
        f"scriptures must run fetch_scriptures.py then build_scriptures.py, each as its own script: {calls}"
    assert all(c["SCI_DB_DIR"] == str(vol) for c in calls)
    no_loads(calls)


def test_scriptures_fetch_failure_stops(tree, ctx):
    vol, rec = ctx
    code, out, calls = setup(tree, vol, rec, ["scriptures"], STUB_EXIT_fetch_scriptures_py="1")
    assert code != 0, "a failed scripture fetch must fail setup"
    assert [c["script"] for c in calls] == ["fetch_scriptures.py"], f"build_scriptures.py must not run: {calls}"


@pytest.mark.parametrize("args", [[], ["talks", "scriptures"], ["everything"]])
def test_one_category_per_run(tree, ctx, args):
    vol, rec = ctx
    code, out, calls = setup(tree, vol, rec, args)
    assert code != 0 and calls == [], f"setup_data.py {' '.join(args)!r} must be refused (one category per run): {calls}"


# ----------------------------------------------------------------------------- stale Church JSON hint
HINT_MARKERS = ("git pull", "--force")   # the fix the hint must name: refresh the Church JSON, then rebuild


def test_hint_when_sci_talks_lack_church_data(tree, ctx):
    vol, rec = ctx
    with SciServer({55: release_zip(55)}) as s:
        code, out, calls = setup(tree, vol, rec, ["talks", "--version", 55, "--base-url", s.url], STUB_REPORT="7,0")
    assert code == 0, f"the hint is a warning, not a failure (exit {code}):\n{out[-1200:]}"
    assert any(re.search(r"\b7\b", l) and "Church" in l for l in out.splitlines()), \
        f"7 unexpected SCI talks without Church data: one line must give the count and say Church data is missing:\n{out[-1200:]}"
    assert all(m in out for m in HINT_MARKERS), f"the hint must name the fix ({HINT_MARKERS}):\n{out[-1200:]}"


@pytest.mark.parametrize("spec,why", [("0,0", "a healthy report (only the expected Ensign-only talks)"),
                                      ("0,4", "Church talks waiting for SCI (normal: Church data comes first)"),
                                      (None, "no report written")])
def test_no_hint_otherwise(tree, ctx, spec, why):
    vol, rec = ctx
    extra = {"STUB_REPORT": spec} if spec else {}
    with SciServer({55: release_zip(55)}) as s:
        code, out, calls = setup(tree, vol, rec, ["talks", "--version", 55, "--base-url", s.url], **extra)
    assert code == 0, f"{why}: setup must still succeed:\n{out[-1200:]}"
    assert "git pull" not in out, f"{why}: no stale-JSON hint expected:\n{out[-1200:]}"
