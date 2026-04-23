"""
Integration tests for loaders/chromadb_loader.py.

Requires ChromaDB running at localhost:8000.
Tests auto-skip when Docker is not running (D-08).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import os
import pytest

_CHROMADB_HOST = os.environ.get("BENCHMARK_CHROMADB_HOST", "10.0.0.231")
_CHROMADB_PORT = int(os.environ.get("BENCHMARK_CHROMADB_PORT", "8763"))


class TestChromaDBLoader:
    def test_round_trip_paragraph(self, chromadb_available, talk_bundle):
        """Insert a talk bundle then query paragraphs collection by vector; expect the inserted record."""
        from loaders.chromadb_loader import ChromaDBLoader

        def _mock_embed(text: str) -> list[float]:
            return [0.1] * 768
        loader = ChromaDBLoader(_CHROMADB_HOST, _CHROMADB_PORT, embed_fn=_mock_embed, batch_size=10)

        # Remove any stale records for talk_id=9999 from prior runs before loading,
        # so the round-trip assertion cannot match a different talk's paragraph (WR-05).
        col = loader._client.get_or_create_collection(name="conference_talk_paragraphs")
        col.delete(where={"talk_id": 9999})

        loader.load(talk_bundle)

        # Query the paragraphs collection filtered to talk_id=9999 so stale records
        # from other talks cannot satisfy the assertion non-deterministically.
        results = col.query(
            query_embeddings=[[0.1] * 768],
            n_results=5,
            where={"talk_id": 9999},
            include=["metadatas", "documents"],
        )
        assert len(results["ids"][0]) >= 1
        # Every returned ID must belong to talk_id=9999
        returned_id = results["ids"][0][0]
        assert "para_" in returned_id
        assert results["metadatas"][0][0].get("talk_id") == 9999
