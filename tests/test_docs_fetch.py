"""docs/DEPLOY.md gets the SCI release with the tools container instead of asking the user for it,
and docs/update/HOW_UPDATES_WORK.md describes fetching releases (it keeps its pipenv commands).

Checks commands and keywords only, not how well the sections read.
"""
import re

from tests.deploy_helpers import CODE_DIR

TOOLS = "docker compose run --rm tools scripts/"


def _deploy():
    return (CODE_DIR / "docs" / "DEPLOY.md").read_text()


def test_prerequisites_do_not_ask_for_the_release():
    m = re.search(r"^## Prerequisites\n(.*?)(?=^## )", _deploy(), re.M | re.S)
    assert m, "docs/DEPLOY.md needs a '## Prerequisites' section"
    pre = m.group(1)
    assert not re.search(r"core\.|content\.|citation index|\bSCI\b", pre, re.I), \
        f"Prerequisites still ask for the raw SCI release files:\n{pre[-600:]}"


def test_setup_and_fetch_commands():
    d = _deploy()
    for cmd in ("setup_data.py talks", "setup_data.py scriptures", "fetch_sci.py"):
        assert TOOLS + cmd in d, f"docs/DEPLOY.md must show `{TOOLS}{cmd}`"
    assert "latest" in d and "scriptures.byu.edu" in d, "docs/DEPLOY.md must say where releases come from and that `latest` finds the newest"


def test_setup_before_loads():
    d = _deploy()
    s = d.find(TOOLS + "setup_data.py talks")
    load = d.find(TOOLS + "run_pipeline.py")
    assert 0 <= s < load, "the setup step must come before the Weaviate loads"


def _section(doc, heading_re):
    m = re.search(heading_re + r".*?(?=^## |\Z)", doc, re.M | re.S)
    return m.group(0) if m else ""


def test_deploy_says_pull_and_rebuild_before_a_newer_release():
    step3 = _section(_deploy(), r"^## Step 3")
    assert step3, "docs/DEPLOY.md needs its '## Step 3' section"
    assert "git pull" in step3 and "docker compose build tools" in step3, \
        "Step 3 must say: before building a newer release, `git pull` and `docker compose build tools` (the Church JSON is baked)"


def test_updates_doc_covers_fetch_sci():
    u = (CODE_DIR / "docs" / "update" / "HOW_UPDATES_WORK.md").read_text()
    for s in ("fetch_sci.py", "setup_data.py", "latest", "unexpected", "pipenv run python scripts/"):
        assert s in u, f"docs/update/HOW_UPDATES_WORK.md must cover {s!r}"
    for stale in ("it's the only thing that does", "**Only `fetch` touches the network.**", "Copy `core.55.db`",
                  "Put the raw files in `db/sci/`"):
        assert stale not in u, f"docs/update/HOW_UPDATES_WORK.md still says {stale!r} (the SCI release is fetched now)"
