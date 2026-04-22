"""
Integration tests for loaders/qdrant_loader.py.

Requires Qdrant running at localhost:6333.
Tests auto-skip when Docker is not running (D-08).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest


class TestQdrantLoader:
    def test_round_trip_paragraph(self, qdrant_available, talk_bundle):
        """Insert a talk bundle then vector search paragraphs collection; expect the inserted point."""
        from loaders.qdrant_loader import QdrantLoader

        def _mock_embed(text: str) -> list[float]:
            return [0.1] * 768

        loader = QdrantLoader("localhost", 6333, embed_fn=_mock_embed, batch_size=10)
        loader.load(talk_bundle)

        results = loader._client.query_points(
            collection_name="paragraphs",
            query=[0.1] * 768,
            limit=1,
            with_payload=True,
        )
        assert len(results.points) >= 1
        payload = results.points[0].payload
        # Original string doc_id stored in payload["_doc_id"] (not the uint64 point ID)
        assert "_doc_id" in payload
        assert payload.get("talk_id") == 9999
