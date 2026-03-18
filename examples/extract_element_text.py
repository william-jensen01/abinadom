"""
Extract text from the first matching element in each talk's body container.

Usage:
    pipenv run py examples/extract_element_text.py <tag> [class]

Examples:
    pipenv run py examples/extract_element_text.py p title
    pipenv run py examples/extract_element_text.py h2
    pipenv run py examples/extract_element_text.py div author-name

Iterates every talk, finds the first element matching the given tag (and
optional CSS class) inside the body container, and prints its text.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str(Path(__file__).parent.parent))

from db import core_db, content_db
from extractors.phase1_talk_metadata import fetch_all_talks, extract_talk_metadata
from extractors.phase2_paragraph_extraction import fetch_talk_html
from extractors.html_parsing_utils import parse_html, find_body_container

# =============================================================================
# Args
# =============================================================================

if len(sys.argv) < 2:
    print("Usage: extract_element_text.py <tag> [class]")
    sys.exit(1)

target_tag = sys.argv[1]
target_class = sys.argv[2] if len(sys.argv) >= 3 else None

selector_label = f"<{target_tag}>" if not target_class else f"<{target_tag} class='{target_class}'>"
print(f"Searching for: {selector_label}")
print()

# =============================================================================
# Main loop
# =============================================================================

rows = fetch_all_talks(core_db)
total = len(rows)
print(f"Found {total} talks\n")

results: list[tuple[int | str, str, str]] = []  # (talk_id, date, text)
skipped = 0

for i, row in enumerate(rows, 1):
    talk_id = row.get("talk_id", "?")
    talk_date = row.get("talk_date", "")

    try:
        extract_talk_metadata(row)
    except Exception:
        skipped += 1
        continue

    html = fetch_talk_html(content_db, talk_id)
    if not html:
        skipped += 1
        continue

    soup = parse_html(html)
    if not soup:
        skipped += 1
        continue

    container = find_body_container(soup)
    if not container:
        skipped += 1
        continue

    kwargs = {"class_": target_class} if target_class else {}
    element = container.find(target_tag, **kwargs)
    if element:
        text = element.get_text(separator=" ", strip=True)
        results.append((talk_id, talk_date or "", text))

    if i % 500 == 0:
        print(f"  {i}/{total} processed...")

# =============================================================================
# Output
# =============================================================================

MAX_TEXT = 200

print()
print("=" * 80)
print(f"Results for {selector_label}")
print("=" * 80)
print(f"{'talk_id':<10}  {'date':<12}  text")
print(f"{'-'*10}  {'-'*12}  {'-'*50}")

for talk_id, date, text in sorted(results, key=lambda x: x[1]):
    display = text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "..."
    print(f"{str(talk_id):<10}  {date:<12}  {display}")

print()
print(f"Summary: {len(results)} / {total} talks had a match  (skipped: {skipped})")
