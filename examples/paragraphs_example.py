"""
Paragraphs Example: Extract paragraphs from a talk.

This script demonstrates the paragraph extraction functionality.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from extractors.paragraphs import (
    process_talk_paragraphs,
    fetch_all_talk_ids,
    extract_paragraphs_for_chromadb,
)
from db import content_db
from config.schemas import PARAGRAPH_CONFIG


def example_single_talk():
    """Example: Extract paragraphs from a single talk."""
    print("=" * 80)
    print("Example 1: Extract paragraphs from a single talk")
    print("=" * 80)

    # Get first available talk ID
    # talk_ids = fetch_all_talk_ids(content_db)
    # if not talk_ids:
    #     print("No talks found in database!")
    #     return

    # talk_id = talk_ids[0]
    # talk_id = 8820
    talk_id = 8615
    print(f"\nProcessing talk ID: {talk_id}")

    # Process the talk
    talk_paras, errors = process_talk_paragraphs(
        content_db, talk_id, PARAGRAPH_CONFIG, strict=False
    )

    if not talk_paras:
        print(f"Failed to extract paragraphs: {errors}")
        return

    # Display results
    print(f"\n--- Extraction Results ---")
    print(f"Talk ID: {talk_paras.talk_id}")
    print(f"Total paragraphs: {talk_paras.total_paragraphs}")
    print(f"Total words: {talk_paras.total_words}")
    print(f"Extraction success: {talk_paras.extraction_success}")

    if errors:
        print(f"\nErrors/Warnings ({len(errors)}):")
        for error in errors[:5]:
            print(f"  - {error}")

    if talk_paras.paragraphs:
        print(f"\n--- First Paragraph ---")
        p = talk_paras.paragraphs[0]
        print(f"Paragraph ID: {p.paragraph_id}")
        print(f"Paragraph number: {p.paragraph_number}")
        print(f"Word count: {p.word_count}")
        print(f"Text: {p.text[:200]}...")

        if talk_paras.total_paragraphs > 1:
            print(f"\n--- Last Paragraph ---")
            p = talk_paras.paragraphs[-1]
            print(f"Paragraph ID: {p.paragraph_id}")
            print(f"Paragraph number: {p.paragraph_number}")
            print(f"Text: {p.text[:200]}...")

        print(f"\n--------------------------------")
        print(f"FULL PARAGRAPHS...")

        for p in talk_paras.paragraphs:
            print(f"Paragraph ID: {p.paragraph_id}")
            print(f"Paragraph number: {p.paragraph_number}")
            print(f"Word count: {p.word_count}")
            print(f"Text: {p.text}")
            print(f"--------------------------------")


def example_multiple_talks():
    """Example: Extract paragraphs from multiple talks."""
    print("\n" + "=" * 80)
    print("Example 2: Extract paragraphs from multiple talks (limit=10)")
    print("=" * 80)

    # Extract paragraphs from first 10 talks
    documents, metadatas, ids = extract_paragraphs_for_chromadb(
        limit=10, validate=False
    )

    print(f"\n--- Extraction Results ---")
    print(f"Total paragraphs extracted: {len(documents)}")
    print(f"Total unique IDs: {len(set(ids))}")

    if documents:
        print(f"\n--- Sample Paragraph ---")
        print(f"ID: {ids[0]}")
        print(f"Document text: {documents[0][:200]}...")
        print(f"Metadata keys: {list(metadatas[0].keys())}")
        print(f"Metadata sample:")
        for key in ["talk_id", "paragraph_number", "word_count"]:
            if key in metadatas[0]:
                print(f"  {key}: {metadatas[0][key]}")


if __name__ == "__main__":
    try:
        # Run examples
        example_single_talk()
        # example_multiple_talks()

        print("\n" + "=" * 80)
        print("Examples completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
