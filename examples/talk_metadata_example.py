"""
Talk Metadata Example: Extract Talk Metadata

This example demonstrates how to use talk metadata extraction to prepare
talk metadata for ChromaDB insertion.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from extractors import extract_talks_for_chromadb, get_extraction_stats
from db import core_db


def example_basic_extraction():
    """Example 1: Basic extraction with limited results."""
    print("=" * 60)
    print("Example 1: Basic Extraction (10 talks)")
    print("=" * 60)

    # Extract 10 talks
    documents, metadatas, ids = extract_talks_for_chromadb(limit=10)

    print(f"\n[OK] Extracted {len(documents)} talks")
    print(f"\nSample talk:")
    print(f"  ID: {ids[0]}")
    print(f"  Document:\n{documents[0]}")
    print(f"\n  Metadata (selected fields):")
    print(f"    - Title: {metadatas[0]['title']}")
    print(f"    - Speaker: {metadatas[0]['speaker_name']}")
    print(f"    - Conference: {metadatas[0]['conference_description']}")
    print(f"    - Year: {metadatas[0]['conference_year']}")


def example_extraction_stats():
    """Example 2: Get extraction statistics."""
    print("\n" + "=" * 60)
    print("Example 2: Extraction Statistics")
    print("=" * 60)

    from extractors.talk_metadata import extract_all_talk_metadata

    # Extract metadata (without ChromaDB preparation)
    metadata_list = extract_all_talk_metadata(core_db, limit=100)

    # Get statistics
    stats = get_extraction_stats(metadata_list)

    print(f"\n[STATS] Statistics for {stats['total_talks']} talks:")
    print(f"  - Unique conferences: {stats['conferences']}")
    print(f"  - Unique speakers: {stats['speakers']}")
    print(f"  - Year range: {stats['year_range'][0]} - {stats['year_range'][1]}")
    print(f"  - With session info: {stats['with_session']}")
    print(f"  - With audio: {stats['with_audio']}")
    print(f"  - With video: {stats['with_video']}")


def example_single_talk():
    """Example 3: Extract a single talk by ID."""
    print("\n" + "=" * 60)
    print("Example 3: Single Talk Extraction")
    print("=" * 60)

    from extractors.talk_metadata import fetch_talk_by_id, extract_talk_metadata

    talk_id = 8820  # Example talk ID

    # Fetch raw database row
    row = fetch_talk_by_id(core_db, talk_id)

    if row:
        # Extract metadata
        metadata = extract_talk_metadata(row)

        print(f"\n[OK] Found talk ID {talk_id}")
        print(f"  Title: {metadata.title}")
        print(f"  Speaker: {metadata.speaker_name}")
        print(f"  Conference: {metadata.conference_description}")
        print(f"  Date: {metadata.talk_date}")
        print(f"  URL: {metadata.url or 'N/A'}")

        # Convert to ChromaDB format
        document, meta, doc_id = metadata.to_chromadb_format()
        print(f"\n  ChromaDB ID: {doc_id}")
        print(f"  Document preview: {document[:100]}...")
    else:
        print(f"[ERROR] Talk ID {talk_id} not found")


def example_chromadb_integration():
    """Example 4: Integration with ChromaDB (mock)."""
    print("\n" + "=" * 60)
    print("Example 4: ChromaDB Integration (Mock)")
    print("=" * 60)

    # Extract talks
    documents, metadatas, ids = extract_talks_for_chromadb(limit=5)

    print(f"\n[OK] Prepared {len(documents)} talks for ChromaDB")
    print("\nTo insert into ChromaDB, use:")
    print(
        """
    import chromadb

    client = chromadb.Client()
    collection = client.create_collection("conference_talks")
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    """
    )

    print(f"\nSample data structure:")
    print(f"  - documents: List[str] ({len(documents)} items)")
    print(f"  - metadatas: List[Dict] ({len(metadatas)} items)")
    print(f"  - ids: List[str] ({len(ids)} items)")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Talk Metadata Extraction Examples")
    print("=" * 60)

    try:
        example_basic_extraction()
        example_extraction_stats()
        example_single_talk()
        example_chromadb_integration()

        print("\n" + "=" * 60)
        print("[SUCCESS] All examples completed successfully!")
        print("=" * 60)
        print("\nFor more information, see docs/pipeline/metadata/PHASE1_README.md")

    except Exception as e:
        print(f"\n[ERROR] Error running examples: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
