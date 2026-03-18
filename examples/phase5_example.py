"""
Phase 5 Example: Full Pipeline + Validation Gate

Runs talk_id=8615 ("And They Sought to See Jesus Who He Was", Oct 2022)
through all four extraction phases and then through the Phase 5 validation gate.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from db import core_db, content_db
from config.schemas import PARAGRAPH_CONFIG, CITATION_CONFIG, FOOTNOTE_CONFIG
from extractors.phase1_talk_metadata import fetch_talk_by_id, extract_talk_metadata
from extractors.phase2_paragraph_extraction import process_talk_paragraphs
from extractors.phase3_citation_extraction import (
    process_talk_citations,
    fetch_all_books,
)
from extractors.phase4_footnote_extraction import process_talk_footnotes
from extractors.phase5_validation import validate_talk

# TALK_ID = 6453  # And They Sought to See Jesus Who He Was
TALK_ID = 8820  # And Now I See

# =============================================================================
# Phase 1 — Talk metadata
# =============================================================================

print("=" * 60)
print(f"Phase 1: Talk Metadata  (talk_id={TALK_ID})")
print("=" * 60)

row = fetch_talk_by_id(core_db, TALK_ID)
if row is None:
    print(f"[ERROR] talk_id={TALK_ID} not found in database")
    sys.exit(1)

metadata = extract_talk_metadata(row)
print(f"{metadata}")
print(f"  Title:    {metadata.title}")
print(f"  Speaker:  {metadata.speaker_name}")
print(f"  Date:     {metadata.talk_date}")

# =============================================================================
# Phase 2 — Paragraph extraction
# =============================================================================

print()
print("=" * 60)
print("Phase 2: Paragraph Extraction")
print("=" * 60)

talk_paragraphs, p2_errors = process_talk_paragraphs(
    content_db, TALK_ID, PARAGRAPH_CONFIG
)
print(f"{talk_paragraphs}")
for p in talk_paragraphs.paragraphs:
    print(f"  {p.paragraph_number}:   {p.text}")
if p2_errors:
    print(f"  Errors ({len(p2_errors)}):")
    for e in p2_errors:
        print(f"    - {e}")

# =============================================================================
# Phase 3 — Citation extraction
# =============================================================================

print()
print("=" * 60)
print("Phase 3: Citation Extraction")
print("=" * 60)

book_cache = fetch_all_books(core_db)
talk_citations, p3_warnings = process_talk_citations(
    core_db, TALK_ID, talk_paragraphs.paragraphs, book_cache, CITATION_CONFIG
)
print(f"  {talk_citations}")
if p3_warnings:
    print(f"  Warnings ({len(p3_warnings)}):")
    for w in p3_warnings:
        print(f"    - {w}")

# =============================================================================
# Phase 4 — Footnote extraction
# =============================================================================

print()
print("=" * 60)
print("Phase 4: Footnote Extraction")
print("=" * 60)

talk_footnotes, p4_warnings = process_talk_footnotes(
    TALK_ID, talk_paragraphs.paragraphs, FOOTNOTE_CONFIG
)
print(f"  {talk_footnotes}")
for fn in talk_footnotes.footnotes:
    print(f"    {fn.footnote_number}: {fn.footnote_id}")
if p4_warnings:
    print(f"  Warnings ({len(p4_warnings)}):")
    for w in p4_warnings:
        print(f"    - {w}")

# =============================================================================
# Phase 5 — Validation gate
# =============================================================================

print()
print("=" * 60)
print("Phase 5: Validation Gate")
print("=" * 60)

report = validate_talk(
    metadata, talk_paragraphs, talk_citations, talk_footnotes, db=core_db
)

status = "VALID" if report.is_valid else "INVALID"
print(f"  Result: {status}")
print(f"  Errors:   {len(report.errors)}")
print(f"  Warnings: {len(report.warnings)}")
print()
print("  Stats:")
for key, val in report.stats.items():
    print(f"    {key}: {val}")

if report.errors:
    print()
    print("  ERRORS:")
    for e in report.errors:
        print(f"    [ERROR] {e}")

if report.warnings:
    print()
    print("  Warnings:")
    for w in report.warnings:
        print(f"    [WARN]  {w}")

print()
print("=" * 60)
print(f"Pipeline complete — talk_id={TALK_ID} is {status}")
print("=" * 60)
