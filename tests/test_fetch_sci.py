"""scripts/fetch_sci.py downloads an SCI release zip into $SCI_DB_DIR/sci and installs it.

Every case runs against a local fake of the release site (sci_server.py), passed with --base-url; nothing here
touches the network. Installed release N = sci/core.N.db, sci/content.N.db, sci/lucene.N/ (the zip's lucene/ contents)
and sci/sci.N.json (the download record). A failed run leaves sci/ exactly as it was.
"""
import ast
import os
import sys

import pytest

from tests.deploy_helpers import CODE_DIR, PY, clean_env, copy_code_tree, run
from tests.sci_server import (SciServer, closed_port_url, fake_db, make_zip, release_members, release_zip,
                              tree_files)

pytestmark = pytest.mark.skipif(
    os.environ.get("SCI_TEST_DEPLOY") != "1",
    reason="starts many subprocesses (~25s); set SCI_TEST_DEPLOY=1 to run",
)

SCRIPT = "fetch_sci.py"
DEFAULT_START = 55   # db/__init__.py's SCI_DB_VERSION default


def env_for(vol=None, **extra):
    e = clean_env(**extra)
    if "SCI_DB_VERSION" not in extra:
        e.pop("SCI_DB_VERSION", None)
    if vol is not None:
        e["SCI_DB_DIR"] = str(vol)
    return e


def fetch(args, env, root=CODE_DIR, cwd=None, timeout=120):
    r = run([PY, str(root / "scripts" / SCRIPT), *map(str, args)], cwd=cwd or os.path.dirname(str(env.get("SCI_DB_DIR") or root)),
            env=env, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def installed(n, members):
    """The files fetch_sci must leave for release N whose zip held `members` (record file excluded)."""
    want = {f"core.{n}.db": members[f"core.{n}.db"], f"content.{n}.db": members[f"content.{n}.db"]}
    for name, data in members.items():
        if name.startswith("lucene/"):
            want[os.path.join(f"lucene.{n}", name[len("lucene/"):])] = data
    return want


def sci_files(vol, record=False):
    d = vol / "sci"
    if not d.exists():
        return {}
    files = tree_files(d)
    return files if record else {k: v for k, v in files.items() if not (k.startswith("sci.") and k.endswith(".json"))}


@pytest.fixture
def vol(tmp_path):
    v = tmp_path / "vol"
    v.mkdir()
    return v


# ----------------------------------------------------------------------------- pinned versions
def test_pinned_version_installs_release(vol):
    m = release_members(55)
    with SciServer({55: make_zip(m)}) as s:
        code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
    assert code == 0, f"fetch_sci.py --version 55 failed:\n{out[-1500:]}"
    files = sci_files(vol, record=True)
    want = installed(55, m)
    got = {k: v for k, v in files.items() if k != "sci.55.json"}
    assert got == want, f"sci/ should hold exactly {sorted(want)} plus sci.55.json; has {sorted(files)}"
    assert "sci.55.json" in files, "the download record sci/sci.55.json is missing"
    assert s.zip_downloads(55), "never downloaded sci.55.zip"


def test_version_defaults_to_sci_db_version(vol):
    with SciServer({53: release_zip(53), 55: release_zip(55)}) as s:
        code, out = fetch(["--base-url", s.url], env_for(vol, SCI_DB_VERSION="53"))
        assert code == 0, out[-1500:]
        assert set(sci_files(vol)) >= {"core.53.db", "content.53.db"} and "core.55.db" not in sci_files(vol), \
            f"no --version with SCI_DB_VERSION=53 must fetch 53; sci/ has {sorted(sci_files(vol))}"
    vol2 = vol.parent / "vol2"
    vol2.mkdir()
    with SciServer({53: release_zip(53), 55: release_zip(55)}) as s:
        code, out = fetch(["--base-url", s.url], env_for(vol2))
        assert code == 0, out[-1500:]
        assert {"core.55.db", "content.55.db"} <= set(sci_files(vol2)), \
            f"no --version and no SCI_DB_VERSION must fetch {DEFAULT_START}; sci/ has {sorted(sci_files(vol2))}"


def test_missing_release_fails_cleanly(vol):
    with SciServer({55: release_zip(55)}) as s:
        code, out = fetch(["--version", 54, "--base-url", s.url], env_for(vol))
    assert code != 0, "a release the site does not have (404) must exit non-zero"
    assert "54" in out, f"the error must name the version it could not find:\n{out[-800:]}"
    assert sci_files(vol, record=True) == {}, f"a failed fetch left files: {sorted(sci_files(vol, True))}"


def test_other_versions_untouched(vol):
    sci = vol / "sci"
    (sci / "lucene.53").mkdir(parents=True)
    old = {"core.53.db": fake_db("hand53"), "content.53.db": fake_db("hand53c"), "lucene.53/segments": b"x" * 30}
    for k, v in old.items():
        (sci / k).write_bytes(v)
    with SciServer({55: release_zip(55)}) as s:
        code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
    assert code == 0, out[-1500:]
    files = sci_files(vol)
    assert all(files.get(k) == v for k, v in old.items()), "fetching 55 changed release 53's files"


# ----------------------------------------------------------------------------- latest
@pytest.mark.parametrize("site,local,env_ver,want,asked_max", [
    # the real site on 2026-11-15: 52, 53, 55 exist; 54, 56, 57 do not
    ({52, 53, 55}, None, None, 55, 58),
    # a one-number gap is crossed, then three misses in a row end the search: 56 miss, 57 hit, 58-60 miss
    ({52, 53, 55, 57}, None, None, 57, 60),
    # two-number gap: 56, 57 miss, 58 hit, 59-61 miss
    ({55, 58}, None, None, 58, 61),
    # three misses after 55 end it, even though 59 exists
    ({55, 59}, None, None, 55, 58),
    # the search starts from the newest release already in sci/ (57), so 59 is found: 58 miss, 59 hit
    ({55, 59}, 57, None, 59, 62),
    # ...or from SCI_DB_VERSION when that is newer
    ({55, 59}, None, "57", 59, 62),
])
def test_latest(vol, site, local, env_ver, want, asked_max):
    if local is not None:
        (vol / "sci").mkdir()
        (vol / "sci" / f"core.{local}.db").write_bytes(fake_db(f"l{local}"))
        (vol / "sci" / f"content.{local}.db").write_bytes(fake_db(f"l{local}c"))
    extra = {"SCI_DB_VERSION": env_ver} if env_ver else {}
    with SciServer({n: release_zip(n) for n in site}) as s:
        code, out = fetch(["--version", "latest", "--base-url", s.url], env_for(vol, **extra))
        asked = s.versions_asked()
    assert code == 0, f"--version latest (site {sorted(site)}) failed:\n{out[-1500:]}"
    files = set(sci_files(vol))
    assert {f"core.{want}.db", f"content.{want}.db"} <= files, \
        f"site {sorted(site)}, local {local}, SCI_DB_VERSION {env_ver}: latest must be {want}; sci/ has {sorted(files)}"
    others = {f for f in files if f.startswith("core.") and f not in (f"core.{want}.db", f"core.{local}.db")}
    assert not others, f"latest must install only {want}, also got {sorted(others)}"
    assert max(asked) == asked_max, f"must stop after three misses in a row: asked for {sorted(asked)}, last should be {asked_max}"
    assert str(want) in out, f"must say which release it found:\n{out[-600:]}"


@pytest.mark.parametrize("why", ["server error", "connection refused"])
def test_latest_stops_on_errors_that_are_not_404(vol, why):
    if why == "server error":
        with SciServer({55: release_zip(55), 57: release_zip(57)}, errors={56: 500}) as s:
            code, out = fetch(["--version", "latest", "--base-url", s.url], env_for(vol))
    else:
        code, out = fetch(["--version", "latest", "--base-url", closed_port_url()], env_for(vol))
    assert code != 0, f"--version latest must fail on a {why}, not treat it as a missing release:\n{out[-800:]}"
    assert sci_files(vol, record=True) == {}, f"a failed latest left files: {sorted(sci_files(vol, True))}"


# ----------------------------------------------------------------------------- re-runs
def test_rerun_skips_download_and_etag_change_replaces(vol):
    with SciServer({55: release_zip(55)}) as s:
        for _ in range(2):
            code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
            assert code == 0, out[-1500:]
        assert len(s.zip_downloads(55)) == 1, f"a re-run with the release in place must not download again: {s.log}"
        m2 = release_members(55, tag="republished")
        s.replace(55, make_zip(m2))
        code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
        assert code == 0, out[-1500:]
    assert sci_files(vol) == installed(55, m2), "a release republished under a new ETag must replace the old files exactly"


def test_hand_placed_release_is_kept(vol):
    sci = vol / "sci"
    sci.mkdir()
    old = {"core.55.db": fake_db("hand"), "content.55.db": fake_db("handc")}
    for k, v in old.items():
        (sci / k).write_bytes(v)
    with SciServer({55: release_zip(55)}) as s:
        code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
        assert code == 0, out[-1500:]
        assert not s.zip_downloads(55), "core/content.55.db already present (no record): must not download"
    assert {k: sci_files(vol)[k] for k in old} == old, "hand-placed release files were changed"


def test_force_downloads_again(vol):
    with SciServer({55: release_zip(55)}) as s:
        fetch(["--version", 55, "--base-url", s.url], env_for(vol))
        code, out = fetch(["--version", 55, "--base-url", s.url, "--force"], env_for(vol))
        assert code == 0, out[-1500:]
        assert len(s.zip_downloads(55)) == 2, "--force must download the release again"


# ----------------------------------------------------------------------------- bad downloads leave sci/ as it was
def _bad_zips(abs_target="/nonexistent-dir/abs-escape.txt"):
    m = release_members(55)
    no_content = {k: v for k, v in m.items() if k != "content.55.db"}
    not_sqlite = dict(m, **{"core.55.db": b"<html>not a database</html>" * 50})
    escape = dict(m, **{"lucene/../../escape.txt": b"pwned"})
    absolute = dict(m, **{abs_target: b"pwned"})
    return {
        "missing content.55.db": make_zip(no_content),
        "core.55.db is not SQLite": make_zip(not_sqlite),
        "entry escapes with ..": make_zip(escape),
        "absolute entry": make_zip(absolute),
        "symlink entry": make_zip(m, symlinks={"lucene/link": "../../../etc/passwd"}),
    }


@pytest.mark.parametrize("case", list(_bad_zips()))
def test_bad_zip_installs_nothing(vol, case):
    data = _bad_zips(str(vol.parent / "abs-escape.txt"))[case]
    with SciServer({55: data}) as s:
        code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
    assert code != 0, f"{case}: must exit non-zero:\n{out[-600:]}"
    assert sci_files(vol, record=True) == {}, f"{case}: left {sorted(sci_files(vol, True))} in sci/"
    stray = [p for p in tree_files(vol.parent) if p.endswith("escape.txt") or p.endswith("link")]
    assert not stray, f"{case}: wrote {stray}"


def test_truncated_download_installs_nothing(vol):
    with SciServer({55: release_zip(55)}, truncate={55}) as s:
        code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
    assert code != 0, f"a download cut short must exit non-zero:\n{out[-600:]}"
    assert sci_files(vol, record=True) == {}, f"a cut download left {sorted(sci_files(vol, True))}"


def test_failed_update_keeps_old_release(vol):
    m = release_members(55)
    with SciServer({55: make_zip(m)}) as s:
        assert fetch(["--version", 55, "--base-url", s.url], env_for(vol))[0] == 0
        before = sci_files(vol, record=True)
        s.replace(55, release_zip(55, tag="v2"))
        s.truncate.add(55)
        code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
    assert code != 0, "a failed re-download must exit non-zero"
    assert sci_files(vol, record=True) == before, "a failed re-download changed the installed release"


def test_extra_top_level_members_are_ignored(vol):
    m = release_members(55)
    with SciServer({55: make_zip(dict(m, **{"README.txt": b"hi"}))}) as s:
        code, out = fetch(["--version", 55, "--base-url", s.url], env_for(vol))
    assert code == 0, out[-1500:]
    assert sci_files(vol) == installed(55, m), f"only the dbs and lucene.55/ are installed; got {sorted(sci_files(vol))}"


# ----------------------------------------------------------------------------- paths and dependencies
def test_default_dir_unset_is_repo_db_sci(tmp_path):
    tree = copy_code_tree(tmp_path / "code")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for env in (env_for(), env_for(SCI_DB_DIR="")):
        with SciServer({55: release_zip(55)}) as s:
            code, out = fetch(["--version", 55, "--base-url", s.url], env, root=tree, cwd=elsewhere)
        assert code == 0, out[-1500:]
        assert (tree / "db" / "sci" / "core.55.db").exists(), "unset/empty SCI_DB_DIR must install into the checkout's db/sci/"
        assert not list(elsewhere.rglob("*.db")), "wrote relative to the cwd"


def test_no_new_dependencies():
    tree = ast.parse((CODE_DIR / "scripts" / SCRIPT).read_text())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and not n.level}
    third_party = sorted(mods - sys.stdlib_module_names)
    assert not third_party, f"fetch_sci.py must use the standard library only; it imports {third_party}"
