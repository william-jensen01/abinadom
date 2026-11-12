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
