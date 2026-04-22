"""
Integration tests for loaders/chromadb_loader.py.

Requires ChromaDB running at localhost:8000.
Tests auto-skip when Docker is not running (D-08).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest


class TestChromaDBLoader:
    def test_round_trip_paragraph(self, chromadb_available, talk_bundle):
        """Insert a talk bundle then query paragraphs collection by vector; expect the inserted record."""
        from loaders.chromadb_loader import ChromaDBLoader

        def _mock_embed(text: str) -> list[float]:
            return [0.1] * 768

        loader = ChromaDBLoader("localhost", 8000, embed_fn=_mock_embed, batch_size=10)
        loader.load(talk_bundle)

        # Query the paragraphs collection by vector
        import chromadb
        client = chromadb.HttpClient(host="localhost", port=8000)
        col = client.get_or_create_collection(name="conference_talk_paragraphs")
        results = col.query(
            query_embeddings=[[0.1] * 768],
            n_results=1,
            include=["metadatas", "documents"],
        )
        assert len(results["ids"][0]) == 1
        # The returned ID should belong to talk_id=9999
        returned_id = results["ids"][0][0]
        assert "para_" in returned_id
        assert results["metadatas"][0][0].get("talk_id") == 9999
