"""scripts/package_skills.py writes one upload-ready zip per skill, for claude.ai."""
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"


def _files_of(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*"))
            if p.is_file() and not any(part.startswith(".") or part == "__pycache__"
                                       for part in p.relative_to(folder).parts)}


def test_one_zip_per_skill_holding_the_skill_folder(tmp_path):
    out = tmp_path / "zips"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "package_skills.py"), str(out)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    folders = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
    zips = {p.stem: p for p in out.glob("*.zip")}
    assert set(zips) == folders
    for name, zp in zips.items():
        with zipfile.ZipFile(zp) as z:
            got = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
            assert z.testzip() is None
        assert got == {f"{name}/{rel}": b for rel, b in _files_of(SKILLS_DIR / name).items()}


def test_zips_unpack_into_a_directory_the_skills_provider_loads(tmp_path):
    from fastmcp.skills.provider import SkillsDirectoryProvider
    out = tmp_path / "zips"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "package_skills.py"), str(out)],
                   check=True, capture_output=True, timeout=60)
    unpacked = tmp_path / "unpacked"
    for zp in out.glob("*.zip"):
        zipfile.ZipFile(zp).extractall(unpacked)
    SkillsDirectoryProvider(unpacked)


def test_readme_says_how_to_make_the_zips():
    assert "package_skills.py" in (ROOT / "README.md").read_text()
