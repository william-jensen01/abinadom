"""The repo's tests give the same result whether or not SCI_DB_DIR, SCRIPTURE_DB_PATH and
SCI_REPORT_DIR are set in the caller's shell, and they write nothing to where those point.

Runs the repo suite twice (vars unset; vars pointing at an empty temp dir) and compares every test's outcome.
Slow (two full suite runs), so it is opt-in:

    SCI_TEST_ENV_ISOLATION=1 pipenv run python -m pytest tests/test_env_isolation.py -q
"""
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.deploy_helpers import CODE_DIR, PY, clean_env

pytestmark = pytest.mark.skipif(
    os.environ.get("SCI_TEST_ENV_ISOLATION") != "1",
    reason="runs the whole suite twice; set SCI_TEST_ENV_ISOLATION=1 to run",
)


def outcomes(env, xml):
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml", str(xml), "tests",
                        "--ignore=tests/test_env_isolation.py"],
                       cwd=CODE_DIR, env=env, capture_output=True, text=True, timeout=1800)
    res = {}
    for case in ET.parse(xml).getroot().iter("testcase"):
        tid = f"{case.get('classname')}::{case.get('name')}"
        kinds = {c.tag for c in case}
        res[tid] = "failed" if kinds & {"failure", "error"} else "skipped" if "skipped" in kinds else "passed"
    return r.returncode, res, r.stdout[-600:]


def test_suite_is_independent_of_path_vars():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        vol = t / "vol"
        vol.mkdir()
        code_a, a, tail_a = outcomes(clean_env(), t / "a.xml")
        env = clean_env(SCI_DB_DIR=vol, SCRIPTURE_DB_PATH=vol / "scripture.db", SCI_REPORT_DIR=vol / "reports")
        code_b, b, tail_b = outcomes(env, t / "b.xml")
        fails = []
        if code_a != 0:
            fails.append(f"suite fails with the vars unset (exit {code_a}):\n{tail_a}")
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        if diff:
            fails.append(f"{len(diff)} tests change outcome when the vars are set, e.g.:\n" +
                         "\n".join(f"  {k}: unset={a.get(k)} set={b.get(k)}" for k in diff[:12]))
        written = sorted(str(p.relative_to(vol)) for p in vol.rglob("*"))
        if written:
            fails.append(f"tests wrote into the dir the vars point at: {written[:10]}")
        if fails:
            pytest.fail("\n".join(fails), pytrace=False)
