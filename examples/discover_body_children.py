"""
Discovery: Every direct child tag/class combination inside the talk body container,
and every grandchild of each direct child.

Iterates every talk, runs Phases 1–2 (metadata + HTML fetch), locates the body
container, records each direct child Tag as a (tag_name, classes) pattern, then
drills into each direct child and records its own direct children.

Prints a ranked frequency table for body children, then a sub-inventory for each
body-child type.
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str(Path(__file__).parent.parent))

from db import core_db, content_db
from extractors.phase1_talk_metadata import fetch_all_talks, extract_talk_metadata
from extractors.phase2_paragraph_extraction import fetch_talk_html
from extractors.html_parsing_utils import parse_html, find_body_container

# =============================================================================
# Setup
# =============================================================================

print("Fetching all talks...")
rows = fetch_all_talks(core_db)
total = len(rows)
print(f"Found {total} talks\n")

# =============================================================================
# Discovery loop
# =============================================================================

child_talks: dict = defaultdict(set)  # parent_pattern → {talk_id}
# parent_pattern → child_pattern → {talk_id}
grandchild_talks: dict = defaultdict(lambda: defaultdict(set))
talk_id_to_date: dict = {}  # talk_id → talk_date string
phase1_errors = 0
no_html = 0
no_container = 0

for i, row in enumerate(rows, 1):
    talk_id = row.get("talk_id", "?")
    if talk_id != "?" and row.get("talk_date"):
        talk_id_to_date[talk_id] = row["talk_date"]

    # --- Phase 1 ---
    try:
        metadata = extract_talk_metadata(row)
    except Exception as e:
        phase1_errors += 1
        print(f"[{i}/{total}] talk_id={talk_id}  PHASE 1 ERROR: {e}")
        continue

    # --- Fetch HTML (Phase 2 DB layer) ---
    html = fetch_talk_html(content_db, talk_id)
    if not html:
        no_html += 1
        continue

    soup = parse_html(html)
    if not soup:
        no_html += 1
        continue

    container = find_body_container(soup)
    if not container:
        no_container += 1
        continue

    # --- Collect direct children of body container ---
    for child in container.children:
        if not hasattr(child, "name") or child.name is None:
            if str(child).strip():
                child_talks[("_text", ())].add(talk_id)
            continue

        parent_pattern = (child.name, tuple(sorted(child.get("class", []))))
        child_talks[parent_pattern].add(talk_id)

        # --- Collect grandchildren (direct children of this child) ---
        for grandchild in child.children:
            if not hasattr(grandchild, "name") or grandchild.name is None:
                if str(grandchild).strip():
                    grandchild_talks[parent_pattern][("_text", ())].add(talk_id)
                continue

            gc_pattern = (grandchild.name, tuple(sorted(grandchild.get("class", []))))
            grandchild_talks[parent_pattern][gc_pattern].add(talk_id)

    if i % 500 == 0:
        print(f"  {i}/{total} processed...")

# =============================================================================
# Summary
# =============================================================================

processed = total - phase1_errors - no_html - no_container


def date_range_str(talk_ids: set, id_to_date: dict) -> str:
    """Return 'first=DATE  mid=DATE  last=DATE' for a set of talk_ids sorted by date."""
    dated = sorted(
        ((id_to_date.get(tid, ""), tid) for tid in talk_ids),
        key=lambda x: x[0],
    )
    n = len(dated)
    if n == 0:
        return ""
    first_date, first_id = dated[0]
    last_date, last_id = dated[-1]
    mid_date, mid_id = dated[n // 2]
    parts = [
        f"first={first_date}(id={first_id})",
        f"mid={mid_date}(id={mid_id})",
        f"last={last_date}(id={last_id})",
    ]
    return "  ".join(parts)


sorted_patterns = sorted(child_talks.items(), key=lambda x: len(x[1]), reverse=True)

print()
print("=" * 60)
print("Direct-child tag/class inventory")
print("=" * 60)
print(f"  Total talks     : {total}")
print(f"  Processed       : {processed}")
print(f"  Phase 1 errors  : {phase1_errors}")
print(f"  No HTML         : {no_html}")
print(f"  No container    : {no_container}")
print(f"  Unique patterns : {len(child_talks)}")
print()

SHOW_IDS_THRESHOLD = 6000
SHOW_IDS_LIMIT = 5

for (tag, classes), talk_ids in sorted_patterns:
    classes_str = " ".join(f".{c}" for c in classes) if classes else "(no class)"
    count = len(talk_ids)
    print(f"[{count:>6} talks]  {tag}  {classes_str}")
    print(f"           dates   : {date_range_str(talk_ids, talk_id_to_date)}")
    if count < SHOW_IDS_THRESHOLD:
        sample = sorted(talk_ids)[:SHOW_IDS_LIMIT]
        suffix = ", ..." if count > SHOW_IDS_LIMIT else ""
        print(f"           talk_ids: {', '.join(str(t) for t in sample)}{suffix}")
    print()

# =============================================================================
# Grandchild inventory per body-child type
# =============================================================================

print()
print("=" * 60)
print("Grandchild inventory  (direct children of each body-child type)")
print("=" * 60)
print()

for parent_pattern, _ in sorted_patterns:
    if parent_pattern not in grandchild_talks:
        continue

    parent_tag, parent_classes = parent_pattern
    parent_classes_str = " ".join(f".{c}" for c in parent_classes) if parent_classes else "(no class)"
    gc_map = grandchild_talks[parent_pattern]
    all_talk_ids = set().union(*gc_map.values())

    print(f"  {parent_tag}  {parent_classes_str}  [{len(all_talk_ids)} talks]")

    sorted_gc = sorted(gc_map.items(), key=lambda x: len(x[1]), reverse=True)
    for (gc_tag, gc_classes), talk_ids in sorted_gc:
        gc_classes_str = " ".join(f".{c}" for c in gc_classes) if gc_classes else "(no class)"
        count = len(talk_ids)
        print(f"    [{count:>6} talks]  {gc_tag}  {gc_classes_str}")
        print(f"               dates   : {date_range_str(talk_ids, talk_id_to_date)}")
        if count < SHOW_IDS_THRESHOLD:
            sample = sorted(talk_ids)[:SHOW_IDS_LIMIT]
            suffix = ", ..." if count > SHOW_IDS_LIMIT else ""
            print(f"               talk_ids: {', '.join(str(t) for t in sample)}{suffix}")
    print()
