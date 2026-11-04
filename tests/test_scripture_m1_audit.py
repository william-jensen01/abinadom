"""M1 audit — docs/scriptures/AUDIT.md answers SPEC-v2 §12 Q2/Q3 with numbers from the full raw store.

Reads a temp copy of the real store; skips when db/scripture.db is missing or empty.
"""
import json
import re
from collections import Counter

import pytest

from tests.scripture_world import ROOT, q

AUDIT = ROOT / "docs" / "scriptures" / "AUDIT.md"


@pytest.fixture(scope="module")
def store(full_store):
    cats, kinds, pclasses = Counter(), Counter(), Counter()
    for (js,) in q(full_store, "SELECT json FROM raw_latest WHERE lang='eng' AND status=200"):
        c = json.loads(js)["content"]
        for f in (c.get("footnotes") or {}).values():
            for cat in re.findall(r'data-note-category="([^"]+)"', f.get("text", "")):
                cats[cat] += 1
        for k in re.findall(r'data-content-type="([^"]+)"', c["body"]):
            kinds[k] += 1
        for cl in re.findall(r'<p class="([^"]+)"', c["body"]):
            pclasses[cl] += 1
    return cats, kinds, pclasses


def _section(text, q):
    m = re.search(rf"^#+ [^\n]*\b{q}\b[^\n]*\n(.*?)(?=^#+ |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def test_section_helper_self_check():
    assert _section("# AUDIT\n## Q2: x\n`jst` 21\n## Q3\nchapter\n", "Q2").strip() == "`jst` 21"
    assert _section("## Q3 kinds\nchapter\n", "Q3").strip() == "chapter"


def test_audit_lists_every_footnote_category(store):
    cats, _, _ = store
    assert AUDIT.exists(), "docs/scriptures/AUDIT.md missing"
    sec = _section(AUDIT.read_text(), "Q2")
    assert sec, "AUDIT.md needs a Q2 (footnote categories) section"
    missing = [c for c in cats if f"`{c}`" not in sec and not re.search(rf"\b{re.escape(c)}\b", sec)]
    assert not missing, f"Q2 must list every data-note-category in the store (with counts); missing: {missing}"
    print("categories:", dict(cats))


def test_audit_lists_page_kinds_and_paragraph_classes(store):
    _, kinds, pclasses = store
    text = AUDIT.read_text() if AUDIT.exists() else ""
    sec = _section(text, "Q3")
    assert sec, "AUDIT.md needs a Q3 (page kinds) section"
    missing = [k for k in kinds if not re.search(rf"\b{re.escape(k)}\b", sec)]
    assert not missing, f"Q3 must cover every TOC data-content-type; missing: {missing}"
    rare = [c for c, n in pclasses.items() if not re.search(rf"\b{re.escape(c)}\b", text)]
    assert not rare, f"AUDIT.md must mention every <p class> seen in page bodies; missing: {rare[:10]}"
    assert "ScriptureChapters" in sec, "Q3 must say which kinds become ScriptureChapters objects and which are raw-only"
