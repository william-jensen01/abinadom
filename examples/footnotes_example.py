# Footnote extraction depends on paragraph extraction output (ParagraphData with text_raw)
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from extractors.paragraphs import process_talk_paragraphs
from extractors.footnotes import process_talk_footnotes
from db import content_db
from config.schemas import PARAGRAPH_CONFIG, FOOTNOTE_CONFIG

# talk_id = 8615  # And They Sought to See Jesus Who He Was, 2022-Oct (footnote-heavy)
talk_id = 8615

# Per talk: paragraphs -> footnotes
talk_paras, p2_errors = process_talk_paragraphs(content_db, talk_id, PARAGRAPH_CONFIG)
print(f"Finished paragraphs")
print(f"    talk_paras: {talk_paras}")

talk_footnotes, warnings = process_talk_footnotes(
    talk_id, talk_paras.paragraphs, FOOTNOTE_CONFIG
)

print(f"\nFinished footnotes")
print(f"    talk_footnotes: {talk_footnotes}")
print(f"    warnings ({len(warnings)}):")
for w in warnings:
    print(f"      - {w}")

# Results
print(f"\n{talk_footnotes.total_footnotes} footnotes found")
for fn in talk_footnotes.footnotes:
    print(f"  \n{fn.to_dict()}")
    # print(f"\n[Para {fn.paragraph_number}] Footnote {fn.footnote_number} @ char {fn.char_position}")
    # print(f"  text: {fn.footnote_text_raw}")
    # print(f"  context_before: {fn.context_before!r}")
    # print(f"  context_after:  {fn.context_after!r}")

# Verify paragraph flags
print("\n--- Paragraph flags ---")
for p in talk_paras.paragraphs:
    if p.has_footnote:
        print(
            f"  Para {p.paragraph_number}: has_footnote={p.has_footnote}, footnote_count={p.footnote_count}"
        )
