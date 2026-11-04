"""M1 jst-full — JST links on the real store (SPEC-v2 §5.2 'must be confirmed', §10 JST, phase 3 checkpoint).

Builds a temp copy of db/scripture.db; skips when that store or core.db is missing.
"""
import re

import pytest

from tests.scripture_world import ROOT, core_scalar, q, q1

AUDIT = ROOT / "docs" / "scriptures" / "AUDIT.md"


@pytest.fixture
def full(full_built):
    return full_built


def test_full_jst_import_and_links(full):
    db, out = full
    jf = core_scalar("SELECT COUNT(*) FROM scripture WHERE Flag IN ('J','F')")
    assert q1(db, "SELECT COUNT(*) FROM jst_verse") == jf, "jst_verse must hold every core.db J+F row"
    total = q1(db, "SELECT COUNT(*) FROM footnote_ref WHERE category='jst'")
    rows = q(db, "SELECT label FROM footnote_ref WHERE category='jst' AND target_jst_verse_id IS NULL")
    print(f"jst refs: {total}, unresolved: {len(rows)}")
    assert total > 900, f"only {total} jst-category refs on the full store"  # estimate: AUDIT.md (I3) measured 941 jst-footnote JST verses
    assert len(rows) <= total * 0.005, f"{len(rows)}/{total} jst refs unresolved: {[r[0] for r in rows[:8]]}"
    audit = AUDIT.read_text() if AUDIT.exists() else ""
    unlisted = sorted({r[0] for r in rows if r[0] and r[0] not in audit})
    assert not unlisted, f"unresolved jst refs must each be listed in docs/scriptures/AUDIT.md: {unlisted[:8]}"
    t = q(db, """SELECT j.chapter, j.verse, j.source_flag FROM footnote_ref r JOIN footnote f ON f.footnote_id=r.footnote_id
                 JOIN verse v ON v.verse_id=f.verse_id JOIN chapter c ON c.chapter_id=v.chapter_id
                 JOIN page p ON p.page_id=c.page_id JOIN jst_verse j ON j.jst_verse_id=r.target_jst_verse_id
                 WHERE p.uri='/scriptures/ot/ex/7' AND v.verse=3 AND r.category='jst'""")
    assert (7, 3, "F") in t, f"KJV Ex 7:3 must link to JST Ex 7:3 (F), got {t}"


def test_f_coverage_is_reported(full):
    assert AUDIT.exists(), "docs/scriptures/AUDIT.md missing"
    text = AUDIT.read_text()
    sec = re.search(r"^#+ [^\n]*\bQ1\b[^\n]*\n(.*?)(?=^#+ |\Z)", text, re.M | re.S)
    assert sec, "AUDIT.md needs a Q1 (JST link coverage) section"
    assert re.search(r"\d", sec.group(1)) and re.search(r"\bF\b", sec.group(1)), \
        "Q1 must report how many F rows the Church's jst footnotes / appendix passages reach (and how many they do not)"
