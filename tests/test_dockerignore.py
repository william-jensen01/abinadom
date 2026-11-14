"""The image is code only: .dockerignore keeps every SQLite file out but ships the `db` package the server imports."""
import glob
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _rules():
    """[(negated, regex)] in file order. Docker reads each pattern relative to the context root; `*` and `?` stay
    within one path segment and `**` spans any number of them, which is what glob.translate produces."""
    rules = []
    for line in (ROOT / ".dockerignore").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = os.path.normpath(line.lstrip("!").strip()).strip("/")
        rules.append((negated, re.compile(glob.translate(pattern, recursive=True, include_hidden=True))))
    return rules


def _excluded(path, rules):
    """The last rule that matches the path, or a directory above it, decides; `!` re-includes."""
    parts = path.split("/")
    prefixes = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    excluded = False
    for negated, rx in rules:
        if any(rx.match(p) for p in prefixes):
            excluded = not negated
    return excluded


def test_db_package_is_in_the_image():
    rules = _rules()
    for needed in ("db/__init__.py", "db/scripture.py"):
        assert (ROOT / needed).exists(), needed
        assert not _excluded(needed, rules), f"{needed} must be in the build context"


def test_database_paths_are_excluded_even_before_they_exist():
    """A fresh clone has no .db files on disk, so check the paths the server mounts or builds by name."""
    rules = _rules()
    for path in ("db/scripture.db", "db/core.55.db", "db/content.55.db", "db/scripture.db-wal",
                 "db/scripture.db-shm", "db/sci/core.55.db", "data/other.sqlite"):
        assert _excluded(path, rules), f"{path} would be baked into the image"


def test_no_sqlite_file_is_in_the_image():
    rules = _rules()
    leaked = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        rel_dir = os.path.relpath(dirpath, ROOT)
        for f in filenames:
            rel = f if rel_dir == "." else f"{rel_dir}/{f}"
            if re.search(r"\.(db|db-shm|db-wal|sqlite)$", f) and not _excluded(rel, rules):
                leaked.append(rel)
    assert not leaked, f"database files would be baked into the image: {leaked[:10]}"


def test_test_and_benchmark_artifacts_are_excluded():
    """Neither is imported by the server; .pytest_cache and benchmark results only bloat the build context."""
    rules = _rules()
    for path in (".pytest_cache/v/cache/nodeids", "benchmark/runner.py", "benchmark/results/run.json"):
        assert _excluded(path, rules), f"{path} would be sent in the build context"
    assert not _excluded("server.py", rules)
