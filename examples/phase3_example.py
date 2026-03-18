# Phase 3 depends on Phase 2 output (ParagraphData with text_raw)
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from extractors.phase2_paragraph_extraction import process_talk_paragraphs
from extractors.phase3_citation_extraction import (
    process_talk_citations,
    fetch_all_books,
)
from db import core_db, content_db
from config.schemas import PARAGRAPH_CONFIG, CITATION_CONFIG

# Load book cache ONCE (99 rows, reused across all talks)
book_cache = fetch_all_books(core_db)

# talk_id = 8615
# talk_id = 8820 # And Now I See, 2025-Oct
talk_id = 8615  # And They Sought to See Jesus Who He Was, 2022-Oct

# Per talk: Phase 2 -> Phase 3
talk_paras, p2_errors = process_talk_paragraphs(content_db, talk_id, PARAGRAPH_CONFIG)
print(f"Finished Phase 2")
print(f"    talk_paras: {talk_paras}")
talk_citations, warnings = process_talk_citations(
    core_db, talk_id, talk_paras.paragraphs, book_cache, CITATION_CONFIG
)

print(f"Finished Phase 3")
print(f"    talk_citations: {talk_citations}")


# Results
print(f"{talk_citations.total_citations} citations found")
for c in talk_citations.citations:
    print(f"[{c.citation_location}] {c.scripture_ref} @ char {c.char_position}")
    print(f"  context_before: {c.context_before}")
    print(f"  context_after: {c.context_after}")
    print(f"{c.to_dict()}")
    print("\n")
