#!/usr/bin/env python3
"""Package each skill in skills/ as an upload-ready zip for claude.ai.

Usage: python scripts/package_skills.py <out_dir>

Writes <out_dir>/<name>.zip for every skills/<name>/ that holds a SKILL.md.
Each zip holds the folder <name>/ with the skill's files; hidden files and
__pycache__ directories are left out. Output is deterministic.
"""

import sys
import zipfile
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def skill_files(folder: Path):
    """Files under folder, sorted, skipping hidden entries and __pycache__."""
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        if any(p.startswith(".") or p == "__pycache__" for p in rel.parts):
            continue
        if path.is_file():
            yield path, rel


def package(folder: Path, out_dir: Path) -> Path:
    target = out_dir / f"{folder.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path, rel in skill_files(folder):
            info = zipfile.ZipInfo(f"{folder.name}/{rel.as_posix()}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())
    return target


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    out_dir = Path(argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    folders = [p.parent for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))]
    if not folders:
        print(f"no skills found in {SKILLS_DIR}", file=sys.stderr)
        return 1
    for folder in folders:
        print(package(folder, out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
